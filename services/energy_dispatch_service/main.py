"""energy-dispatch-service: orden de activación física del cargador y registro de telemetría."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from decimal import Decimal

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.flags import get_flags
from aegis_common.web import BusinessError, create_app
from pydantic import BaseModel, Field

from . import repository as repo

SERVICE = "energy-dispatch"
log = logging.getLogger(f"aegisvolt.{SERVICE}")
app = create_app(SERVICE, readiness=lambda: dynamodb_table(get_settings().table("dispatch")).table_status)

TICK_SECONDS = float(os.getenv("TELEMETRY_TICK_SECONDS", "5"))
TIME_SPEEDUP = float(os.getenv("TELEMETRY_SPEEDUP", "60"))  # 1 tick = 5 min de carga simulada


class StartRequest(BaseModel):
    saga_id: str
    station_id: str
    connector_id: str
    fleet_id: str
    estimated_kwh: float = Field(gt=0)
    power_kw: float = 50


def _session(item: dict) -> dict:
    return {
        "session_id": item["session_id"],
        "status": item.get("status"),
        "station_id": item.get("station_id"),
        "connector_id": item.get("connector_id"),
        "fleet_id": item.get("fleet_id"),
        "estimated_kwh": float(item.get("estimated_kwh", 0)),
        "power_kw": float(item.get("power_kw", 0)),
        "power_kw_now": float(item.get("power_kw_now", 0)),
        "kwh_delivered": float(item.get("kwh_delivered", 0)),
        "soc_percent": float(item.get("soc_percent", 0)),
        "error": item.get("error"),
        "started_at": item.get("started_at"),
        "updated_at": item.get("updated_at"),
    }


@app.post("/sessions")
def start(req: StartRequest):
    data = {
        "station_id": req.station_id,
        "connector_id": req.connector_id,
        "fleet_id": req.fleet_id,
        "estimated_kwh": Decimal(str(req.estimated_kwh)),
        "power_kw": Decimal(str(req.power_kw)),
    }
    if get_flags().is_enabled("SIMULATE_CHARGER_HARDWARE_FAULT"):
        repo.record_fault(req.saga_id, data, "CHARGER_HARDWARE_FAULT")
        log.error(
            "el cargador reportó error físico (SIMULATE_CHARGER_HARDWARE_FAULT)",
            extra={"station_id": req.station_id, "connector_id": req.connector_id},
        )
        raise BusinessError("HARDWARE_FAULT", "El cargador reportó un error físico al iniciar el flujo eléctrico", 503)
    item, replay = repo.start_session(req.saga_id, data)
    log.info(
        "sesión repetida (idempotente)" if replay else "flujo eléctrico iniciado",
        extra={"station_id": req.station_id, "connector_id": req.connector_id},
    )
    return {**_session(item), "idempotent_replay": replay}


@app.get("/sessions")
def sessions(status: str | None = None, limit: int = 50):
    return [_session(s) for s in repo.list_sessions(status)[:limit]]


@app.get("/sessions/{session_id}")
def session(session_id: str):
    return _session(repo.require_session(session_id))


@app.post("/sessions/{session_id}/stop")
def stop(session_id: str):
    current = repo.require_session(session_id)
    if current.get("status") in ("STOPPED", "FAULT"):
        return _session(current)
    return _session(repo.set_status(session_id, "STOPPED"))


@app.get("/sessions/{session_id}/telemetry")
def telemetry(session_id: str, limit: int = 60):
    return [
        {
            "timestamp": t["timestamp"],
            "power_kw": float(t["power_kw"]),
            "kwh_delivered": float(t["kwh_delivered"]),
            "soc_percent": float(t["soc_percent"]),
        }
        for t in repo.list_telemetry(session_id, limit)
    ]


def simulate_tick() -> int:
    """Genera una lectura por cada sesión activa; marca COMPLETED al llegar a los kWh estimados."""
    count = 0
    for s in repo.list_sessions("CHARGING"):
        target = Decimal(str(s.get("estimated_kwh", 0)))
        delivered = Decimal(str(s.get("kwh_delivered", 0)))
        rated = float(s.get("power_kw", 50))
        power = Decimal(str(round(rated * random.uniform(0.85, 1.0), 2)))
        delta = power * Decimal(str(TICK_SECONDS * TIME_SPEEDUP / 3600))
        kwh = min(target, (delivered + delta).quantize(Decimal("0.001")))
        soc = min(
            Decimal("100"), (Decimal("20") + kwh / max(target, Decimal("1")) * Decimal("75")).quantize(Decimal("0.1"))
        )
        repo.add_telemetry(s["session_id"], power if kwh < target else Decimal("0"), kwh, soc)
        if kwh >= target:
            repo.set_status(s["session_id"], "COMPLETED")
        count += 1
    return count


@app.on_event("startup")
async def start_simulator():
    if os.getenv("TELEMETRY_SIMULATOR", "true").lower() != "true":
        return

    async def loop():
        while True:
            await asyncio.sleep(TICK_SECONDS)
            try:
                await asyncio.to_thread(simulate_tick)
            except Exception:
                log.exception("fallo en el simulador de telemetría")

    asyncio.create_task(loop())
