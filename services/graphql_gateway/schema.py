"""Esquema GraphQL unificado de AegisVolt (capa de agregación sobre los 3 microservicios)."""

from __future__ import annotations

import os
from enum import Enum

import strawberry
from aegis_common.config import get_settings
from aegis_common.flags import KNOWN_FLAGS, get_flags
from strawberry.types import Info

from . import saga_store as store
from .clients import StepError


# ----------------------------------------------------------------------------- enums
@strawberry.enum(description="Estado de un conector de carga")
class ConnectorStatus(Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    CHARGING = "CHARGING"
    FAULT = "FAULT"


@strawberry.enum(description="Estado de la transacción distribuida SAGA")
class SagaStatus(Enum):
    STARTED = "STARTED"
    STATION_RESERVED = "STATION_RESERVED"
    FUNDS_HELD = "FUNDS_HELD"
    COMPENSATING = "COMPENSATING"
    FUNDS_REFUNDED = "FUNDS_REFUNDED"
    RESERVATION_RELEASED = "RESERVATION_RELEASED"
    COMPLETED = "COMPLETED"
    FINISHED = "FINISHED"
    COMPENSATED = "COMPENSATED"
    FAILED = "FAILED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


# ----------------------------------------------------------------------------- types
@strawberry.type
class Environment:
    name: str
    version: str
    pod_template_hash: str
    region: str


@strawberry.type
class FeatureFlag:
    name: str
    enabled: bool
    description: str
    updated_at: str | None
    updated_by: str | None


@strawberry.type
class Connector:
    connector_id: str
    station_id: str
    connector_type: str
    power_kw: float
    status: ConnectorStatus
    saga_id: str | None
    fleet_id: str | None
    updated_at: str | None


@strawberry.type
class Station:
    station_id: str
    name: str
    city: str
    lat: float
    lng: float
    connectors: list[Connector]

    @strawberry.field
    def available_connectors(self) -> int:
        return sum(1 for c in self.connectors if c.status == ConnectorStatus.AVAILABLE)


@strawberry.type
class WalletTransaction:
    id: str
    type: str
    ref: str | None
    amount: float
    surge_applied: bool
    reason: str | None
    created_at: str | None


@strawberry.type
class Wallet:
    fleet_id: str
    fleet_name: str
    balance: float
    currency: str
    updated_at: str | None
    transactions: list[WalletTransaction]


@strawberry.type
class PriceQuote:
    connector_type: str
    kwh: float
    price_per_kwh: float
    surge_applied: bool
    surge_multiplier: float
    total: float


@strawberry.type
class SagaStep:
    name: str
    service: str
    status: str
    detail: str | None
    at: str | None
    idempotent_replay: bool | None


@strawberry.type
class SagaTransaction:
    saga_id: str
    correlation_id: str
    status: SagaStatus
    env: str
    fleet_id: str
    station_id: str
    connector_id: str
    estimated_kwh: float
    amount: float | None
    surge_applied: bool | None
    error_code: str | None
    error_message: str | None
    failed_step: str | None
    session_id: str | None
    steps: list[SagaStep]
    created_at: str
    updated_at: str


@strawberry.type
class ChargingSession:
    session_id: str
    status: str
    station_id: str | None
    connector_id: str | None
    fleet_id: str | None
    estimated_kwh: float
    power_kw: float
    power_kw_now: float
    kwh_delivered: float
    soc_percent: float
    error: str | None
    started_at: str | None
    updated_at: str | None


@strawberry.type
class TelemetryReading:
    timestamp: str
    power_kw: float
    kwh_delivered: float
    soc_percent: float


@strawberry.input
class ReserveAndStartChargingInput:
    fleet_id: str
    station_id: str
    connector_id: str
    estimated_kwh: float
    client_request_id: str | None = strawberry.field(
        default=None, description="Clave de idempotencia de la mutación: reenviarla devuelve la misma saga"
    )


# ----------------------------------------------------------------------------- mappers
def to_connector(c: dict) -> Connector:
    return Connector(
        connector_id=c["connector_id"],
        station_id=c["station_id"],
        connector_type=c["connector_type"],
        power_kw=c["power_kw"],
        status=ConnectorStatus(c["status"]),
        saga_id=c.get("saga_id"),
        fleet_id=c.get("fleet_id"),
        updated_at=c.get("updated_at"),
    )


def to_saga(s: dict) -> SagaTransaction:
    return SagaTransaction(
        saga_id=s["saga_id"],
        correlation_id=s.get("correlation_id", s["saga_id"]),
        status=SagaStatus(s["status"]),
        env=s.get("env", ""),
        fleet_id=s["fleet_id"],
        station_id=s["station_id"],
        connector_id=s["connector_id"],
        estimated_kwh=float(s.get("estimated_kwh", 0)),
        amount=float(s["amount"]) if s.get("amount") is not None else None,
        surge_applied=s.get("surge_applied"),
        error_code=s.get("error_code"),
        error_message=s.get("error_message"),
        failed_step=s.get("failed_step"),
        session_id=s.get("session_id"),
        steps=[
            SagaStep(
                name=st["name"],
                service=st.get("service", ""),
                status=st["status"],
                detail=st.get("detail"),
                at=st.get("at"),
                idempotent_replay=st.get("idempotent_replay"),
            )
            for st in s.get("steps", [])
        ],
        created_at=s["created_at"],
        updated_at=s["updated_at"],
    )


def to_flag(name: str, item: dict | None) -> FeatureFlag:
    item = item or {}
    return FeatureFlag(
        name=name,
        enabled=bool(item.get("enabled", False)),
        description=item.get("description") or KNOWN_FLAGS.get(name, ""),
        updated_at=item.get("updated_at"),
        updated_by=item.get("updated_by"),
    )


def to_session(s: dict) -> ChargingSession:
    return ChargingSession(**{k: s.get(k) for k in ChargingSession.__annotations__})


def to_wallet(w: dict) -> Wallet:
    return Wallet(
        fleet_id=w["fleet_id"],
        fleet_name=w["fleet_name"],
        balance=w["balance"],
        currency=w["currency"],
        updated_at=w.get("updated_at"),
        transactions=[WalletTransaction(**t) for t in w.get("transactions", [])],
    )


def _svc(info: Info):
    return info.context["services"]


def _orch(info: Info):
    return info.context["orchestrator"]


# ----------------------------------------------------------------------------- query
@strawberry.type
class Query:
    @strawberry.field(description="Ambiente estático al que está conectado este endpoint (dev/test/prod)")
    def environment(self) -> Environment:
        s = get_settings()
        return Environment(
            name=s.env, version=s.app_version, pod_template_hash=s.pod_template_hash, region=s.aws_region
        )

    @strawberry.field(description="Estado de las Feature Flags del ambiente actual")
    def feature_flags(self) -> list[FeatureFlag]:
        current = get_flags().all(force=True)
        names = sorted(set(KNOWN_FLAGS) | set(current))
        return [to_flag(n, current.get(n)) for n in names]

    @strawberry.field(description="Electrolineras y disponibilidad de conectores en tiempo real")
    async def stations(self, info: Info) -> list[Station]:
        data = await _svc(info).station.call("GET", "/stations")
        return [
            Station(
                station_id=s["station_id"],
                name=s["name"],
                city=s["city"],
                lat=s["lat"],
                lng=s["lng"],
                connectors=[to_connector(c) for c in s["connectors"]],
            )
            for s in data
        ]

    @strawberry.field
    async def station(self, info: Info, station_id: str) -> Station | None:
        for s in await Query.stations(self, info):
            if s.station_id == station_id:
                return s
        return None

    @strawberry.field(description="Billeteras de las flotas")
    async def fleets(self, info: Info) -> list[Wallet]:
        data = await _svc(info).billing.call("GET", "/wallets")
        return [to_wallet({**w, "transactions": []}) for w in data]

    @strawberry.field
    async def wallet(self, info: Info, fleet_id: str) -> Wallet:
        return to_wallet(await _svc(info).billing.call("GET", f"/wallets/{fleet_id}"))

    @strawberry.field(description="Cotización con tarifa dinámica si ENABLE_DYNAMIC_SURGE_PRICING está activa")
    async def price_quote(self, info: Info, connector_type: str = "CCS2", kwh: float = 30) -> PriceQuote:
        q = await _svc(info).billing.call("GET", "/quote", params={"connector_type": connector_type, "kwh": kwh})
        return PriceQuote(**q)

    @strawberry.field(description="Historial de transacciones SAGA (opcionalmente filtrado por estado)")
    def sagas(self, status: SagaStatus | None = None, limit: int = 50) -> list[SagaTransaction]:
        return [to_saga(s) for s in store.list_sagas(status.value if status else None, limit)]

    @strawberry.field
    def saga(self, saga_id: str) -> SagaTransaction | None:
        s = store.get(saga_id)
        return to_saga(s) if s and not saga_id.startswith("REQ#") else None

    @strawberry.field
    async def charging_sessions(self, info: Info, status: str | None = None, limit: int = 50) -> list[ChargingSession]:
        params = {"limit": limit} | ({"status": status} if status else {})
        return [to_session(s) for s in await _svc(info).dispatch.call("GET", "/sessions", params=params)]

    @strawberry.field(description="Telemetría de consumo energético de una sesión")
    async def telemetry(self, info: Info, session_id: str, limit: int = 60) -> list[TelemetryReading]:
        data = await _svc(info).dispatch.call("GET", f"/sessions/{session_id}/telemetry", params={"limit": limit})
        return [TelemetryReading(**t) for t in data]


# -------------------------------------------------------------------------- mutation
def _raise(e: StepError):
    raise ValueError(f"{e.code}: {e.message}") from e


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Dispara la SAGA: reserva conector -> retiene saldo -> activa el cargador")
    async def reserve_and_start_charging(self, info: Info, input: ReserveAndStartChargingInput) -> SagaTransaction:
        saga = await _orch(info).start(
            fleet_id=input.fleet_id,
            station_id=input.station_id,
            connector_id=input.connector_id,
            estimated_kwh=input.estimated_kwh,
            client_request_id=input.client_request_id,
        )
        return to_saga(saga)

    @strawberry.mutation(description="Detiene la carga y libera el conector")
    async def stop_charging(self, info: Info, saga_id: str) -> SagaTransaction:
        try:
            return to_saga(await _orch(info).stop(saga_id))
        except StepError as e:
            _raise(e)

    @strawberry.mutation(description="Re-ejecuta las compensaciones de una saga (demuestra idempotencia)")
    async def retry_compensation(self, info: Info, saga_id: str) -> SagaTransaction:
        try:
            return to_saga(await _orch(info).retry_compensation(saga_id))
        except StepError as e:
            _raise(e)

    @strawberry.mutation
    async def top_up_wallet(self, info: Info, fleet_id: str, amount: float) -> Wallet:
        await _svc(info).billing.call("POST", f"/wallets/{fleet_id}/topup", json={"amount": amount})
        return to_wallet(await _svc(info).billing.call("GET", f"/wallets/{fleet_id}"))

    @strawberry.mutation(description="Cambia una Feature Flag SOLO en este ambiente (requiere header x-admin-token)")
    def set_feature_flag(self, info: Info, name: str, enabled: bool) -> FeatureFlag:
        token = info.context["request"].headers.get("x-admin-token")
        expected = os.getenv("ADMIN_TOKEN")
        if not expected or token != expected:
            raise PermissionError("x-admin-token inválido")
        if name not in KNOWN_FLAGS:
            raise ValueError(f"flag desconocida: {name}")
        return to_flag(name, get_flags().set(name, enabled, updated_by="graphql"))


schema = strawberry.Schema(query=Query, mutation=Mutation)
