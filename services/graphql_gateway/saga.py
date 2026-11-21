"""Orquestador de la SAGA "Reservar y Activar Carga".

Paso 1  station-reservation : conector AVAILABLE -> RESERVED
Paso 2  billing-wallet      : retención del saldo estimado
Paso 3  energy-dispatch     : activación física del cargador
Final   station-reservation : RESERVED -> CHARGING  => saga COMPLETED

Compensaciones (orden inverso, con reintentos exponenciales):
  falla paso 2 -> liberar conector                                  => COMPENSATED
  falla paso 3 -> reembolsar saldo -> liberar conector             => COMPENSATED
  si una compensación agota reintentos                              => COMPENSATION_FAILED
    (Prefect la detecta como huérfana; retryCompensation la reintenta de forma idempotente)
"""

from __future__ import annotations

import logging
import uuid

from aegis_common.config import get_settings
from aegis_common.logging import correlation_id_var, saga_id_var, step_var
from aegis_common.metrics import metrics
from aegis_common.time_utils import now_iso
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from . import saga_store as store
from .clients import Services, StepError

log = logging.getLogger("aegisvolt.saga")

COMPENSATION_ATTEMPTS = 4


def _retriable(exc: BaseException) -> bool:
    return isinstance(exc, StepError) and exc.retriable


class SagaOrchestrator:
    def __init__(self, services: Services, compensation_wait_max: float = 4.0):
        self.svc = services
        self.wait_max = compensation_wait_max

    # ------------------------------------------------------------------ helpers
    def _ctx(self, saga_id: str, step: str) -> None:
        correlation_id_var.set(saga_id)
        saga_id_var.set(saga_id)
        step_var.set(step)

    async def _retry(self, fn, attempts: int):
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.3, max=self.wait_max),
            retry=retry_if_exception(_retriable),
            reraise=True,
        ):
            with attempt:
                return await fn()

    # ------------------------------------------------------------------ forward
    async def start(
        self,
        *,
        fleet_id: str,
        station_id: str,
        connector_id: str,
        estimated_kwh: float,
        client_request_id: str | None = None,
    ) -> dict:
        saga_id = str(uuid.uuid4())
        if client_request_id:
            existing = store.claim_request(client_request_id, saga_id)
            if existing:
                log.info("mutación repetida: se devuelve la saga existente", extra={"existing_saga": existing})
                return store.get(existing) or {}
        now = now_iso()
        store.create(
            {
                "saga_id": saga_id,
                "correlation_id": saga_id,
                "status": "STARTED",
                "env": get_settings().env,
                "fleet_id": fleet_id,
                "station_id": station_id,
                "connector_id": connector_id,
                "estimated_kwh": estimated_kwh,
                "client_request_id": client_request_id,
                "steps": [],
                "created_at": now,
                "updated_at": now,
            }
        )
        self._ctx(saga_id, "START")
        log.info("SAGA iniciada", extra={"fleet_id": fleet_id, "station_id": station_id, "connector_id": connector_id})

        # Paso 1 - reserva
        self._ctx(saga_id, "RESERVE_CONNECTOR")
        try:
            conn = await self._retry(
                lambda: self.svc.station.call(
                    "POST",
                    "/reservations",
                    saga_id=saga_id,
                    step="RESERVE_CONNECTOR",
                    json={
                        "saga_id": saga_id,
                        "station_id": station_id,
                        "connector_id": connector_id,
                        "fleet_id": fleet_id,
                    },
                ),
                attempts=2,
            )
        except StepError as e:
            return self._fail(saga_id, "RESERVE_CONNECTOR", e)
        store.transition(
            saga_id,
            "STATION_RESERVED",
            {
                "name": "RESERVE_CONNECTOR",
                "service": "station-reservation",
                "status": "SUCCEEDED",
                "detail": f"conector {connector_id} RESERVED",
            },
            connector_type=conn["connector_type"],
            power_kw=conn["power_kw"],
        )

        # Paso 2 - cobro
        self._ctx(saga_id, "HOLD_FUNDS")
        try:
            held = await self._retry(
                lambda: self.svc.billing.call(
                    "POST",
                    "/holds",
                    saga_id=saga_id,
                    step="HOLD_FUNDS",
                    json={
                        "saga_id": saga_id,
                        "fleet_id": fleet_id,
                        "estimated_kwh": estimated_kwh,
                        "connector_type": conn["connector_type"],
                    },
                ),
                attempts=2,
            )
        except StepError as e:
            store.transition(
                saga_id,
                "COMPENSATING",
                self._failed_step("HOLD_FUNDS", "billing-wallet", e),
                error_code=e.code,
                error_message=e.message,
                failed_step="HOLD_FUNDS",
            )
            return await self.compensate(saga_id, refund=False)
        store.transition(
            saga_id,
            "FUNDS_HELD",
            {
                "name": "HOLD_FUNDS",
                "service": "billing-wallet",
                "status": "SUCCEEDED",
                "detail": f"retenido {held['amount']} (surge={held['quote']['surge_applied']})",
            },
            amount=held["amount"],
            surge_applied=held["quote"]["surge_applied"],
        )

        # Paso 3 - activación física
        self._ctx(saga_id, "START_CHARGING")
        try:
            await self._retry(
                lambda: self.svc.dispatch.call(
                    "POST",
                    "/sessions",
                    saga_id=saga_id,
                    step="START_CHARGING",
                    json={
                        "saga_id": saga_id,
                        "station_id": station_id,
                        "connector_id": connector_id,
                        "fleet_id": fleet_id,
                        "estimated_kwh": estimated_kwh,
                        "power_kw": conn["power_kw"],
                    },
                ),
                attempts=2,
            )
            await self._retry(
                lambda: self.svc.station.call(
                    "POST",
                    f"/reservations/{saga_id}/charging",
                    saga_id=saga_id,
                    step="MARK_CHARGING",
                    json={"station_id": station_id, "connector_id": connector_id},
                ),
                attempts=3,
            )
        except StepError as e:
            store.transition(
                saga_id,
                "COMPENSATING",
                self._failed_step("START_CHARGING", "energy-dispatch", e),
                error_code=e.code,
                error_message=e.message,
                failed_step="START_CHARGING",
            )
            return await self.compensate(saga_id, refund=True)

        saga = store.transition(
            saga_id,
            "COMPLETED",
            {
                "name": "START_CHARGING",
                "service": "energy-dispatch",
                "status": "SUCCEEDED",
                "detail": "flujo eléctrico activo; conector CHARGING",
            },
            session_id=saga_id,
        )
        metrics.incr("SagaCompleted")
        log.info("SAGA completada")
        return saga

    @staticmethod
    def _failed_step(name: str, service: str, e: StepError) -> dict:
        return {"name": name, "service": service, "status": "FAILED", "detail": str(e)}

    def _fail(self, saga_id: str, step: str, e: StepError) -> dict:
        log.warning("SAGA fallida en el paso 1 (sin nada que compensar)", extra={"error_code": e.code})
        metrics.incr("SagaFailed")
        return store.transition(
            saga_id,
            "FAILED",
            self._failed_step(step, "station-reservation", e),
            error_code=e.code,
            error_message=e.message,
            failed_step=step,
        )

    # ------------------------------------------------------------- compensation
    async def compensate(self, saga_id: str, refund: bool, replay: bool = False) -> dict:
        saga = store.get(saga_id) or {}
        fleet_id, station_id, connector_id = saga["fleet_id"], saga["station_id"], saga["connector_id"]
        suffix = "_REPLAY" if replay else ""
        try:
            if refund:
                self._ctx(saga_id, "COMPENSATE_REFUND")
                r = await self._retry(
                    lambda: self.svc.billing.call(
                        "POST",
                        f"/holds/{saga_id}/refund",
                        saga_id=saga_id,
                        step="COMPENSATE_REFUND",
                        json={"fleet_id": fleet_id, "reason": saga.get("error_code", "SAGA_COMPENSATION")},
                    ),
                    attempts=COMPENSATION_ATTEMPTS,
                )
                store.transition(
                    saga_id,
                    "FUNDS_REFUNDED" if not replay else saga["status"],
                    {
                        "name": "COMPENSATE_REFUND" + suffix,
                        "service": "billing-wallet",
                        "status": "COMPENSATED",
                        "detail": f"reembolsado {r['amount']}"
                        if r["refunded"]
                        else f"sin cambios (idempotente: {r.get('reason') or 'ya reembolsado'})",
                        "idempotent_replay": r["idempotent_replay"],
                    },
                )
                log.info("compensación de billing ejecutada", extra={"refunded": r["refunded"]})
            self._ctx(saga_id, "COMPENSATE_RELEASE")
            rel = await self._retry(
                lambda: self.svc.station.call(
                    "POST",
                    f"/reservations/{saga_id}/release",
                    saga_id=saga_id,
                    step="COMPENSATE_RELEASE",
                    json={"station_id": station_id, "connector_id": connector_id},
                ),
                attempts=COMPENSATION_ATTEMPTS,
            )
            store.transition(
                saga_id,
                "RESERVATION_RELEASED" if not replay else saga["status"],
                {
                    "name": "COMPENSATE_RELEASE" + suffix,
                    "service": "station-reservation",
                    "status": "COMPENSATED",
                    "detail": "conector AVAILABLE" if rel["released"] else "sin cambios (ya liberado)",
                    "idempotent_replay": rel["idempotent_replay"],
                },
            )
        except StepError as e:
            log.error("compensación agotó los reintentos", extra={"error_code": e.code})
            metrics.incr("SagaCompensationFailed")
            return store.transition(
                saga_id,
                "COMPENSATION_FAILED",
                {"name": "COMPENSATION", "service": "orchestrator", "status": "FAILED", "detail": str(e)},
            )
        metrics.incr("SagaCompensated")
        log.warning("SAGA compensada (rollback distribuido completo)")
        return store.transition(saga_id, "COMPENSATED")

    async def retry_compensation(self, saga_id: str) -> dict:
        """Re-ejecuta las compensaciones. Gracias a la idempotencia no mueve dinero dos veces."""
        saga = store.get(saga_id)
        if not saga:
            raise StepError("SAGA_NOT_FOUND", saga_id, 404)
        if saga["status"] not in {"COMPENSATED", "COMPENSATION_FAILED", "COMPENSATING"}:
            raise StepError("NOT_COMPENSABLE", f"estado {saga['status']} no admite compensación", 409)
        refund = saga.get("failed_step") == "START_CHARGING"
        return await self.compensate(saga_id, refund=refund, replay=saga["status"] == "COMPENSATED")

    # --------------------------------------------------------------------- stop
    async def stop(self, saga_id: str) -> dict:
        saga = store.get(saga_id)
        if not saga:
            raise StepError("SAGA_NOT_FOUND", saga_id, 404)
        if saga["status"] == "FINISHED":
            return saga
        if saga["status"] != "COMPLETED":
            raise StepError("NOT_CHARGING", f"estado {saga['status']}", 409)
        self._ctx(saga_id, "STOP_CHARGING")
        await self.svc.dispatch.call("POST", f"/sessions/{saga_id}/stop", saga_id=saga_id, step="STOP_CHARGING")
        await self.svc.station.call(
            "POST",
            f"/reservations/{saga_id}/release",
            saga_id=saga_id,
            step="RELEASE_CONNECTOR",
            json={"station_id": saga["station_id"], "connector_id": saga["connector_id"]},
        )
        log.info("sesión de carga finalizada por el usuario")
        return store.transition(
            saga_id,
            "FINISHED",
            {
                "name": "STOP_CHARGING",
                "service": "energy-dispatch",
                "status": "SUCCEEDED",
                "detail": "sesión detenida y conector liberado",
            },
        )
