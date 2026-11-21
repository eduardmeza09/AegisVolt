"""station-reservation-service: disponibilidad y bloqueo temporal de bahías de carga."""

from __future__ import annotations

import logging
from collections import defaultdict

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.flags import get_flags
from aegis_common.web import BusinessError, create_app
from pydantic import BaseModel

from . import repository as repo

SERVICE = "station-reservation"
log = logging.getLogger(f"aegisvolt.{SERVICE}")
app = create_app(SERVICE, readiness=lambda: dynamodb_table(get_settings().table("reservations")).table_status)


class ReserveRequest(BaseModel):
    saga_id: str
    station_id: str
    connector_id: str
    fleet_id: str


class ConnectorRef(BaseModel):
    station_id: str
    connector_id: str


def _group(items: list[dict]) -> list[dict]:
    stations: dict[str, dict] = {}
    connectors: dict[str, list] = defaultdict(list)
    for it in items:
        sid = it["station_id"]
        stations.setdefault(
            sid,
            {
                "station_id": sid,
                "name": it.get("station_name", sid),
                "city": it.get("city", ""),
                "lat": float(it.get("lat", 0)),
                "lng": float(it.get("lng", 0)),
            },
        )
        connectors[sid].append(_connector(it))
    out = []
    for sid, st in sorted(stations.items()):
        st["connectors"] = sorted(connectors[sid], key=lambda c: c["connector_id"])
        out.append(st)
    return out


def _connector(it: dict) -> dict:
    return {
        "station_id": it["station_id"],
        "connector_id": it["connector_id"],
        "connector_type": it.get("connector_type", "CCS2"),
        "power_kw": float(it.get("power_kw", 50)),
        "status": it.get("status", "AVAILABLE"),
        "saga_id": it.get("saga_id"),
        "fleet_id": it.get("fleet_id"),
        "updated_at": it.get("updated_at"),
    }


@app.get("/stations")
def list_stations():
    return _group(repo.list_connectors())


@app.get("/stations/{station_id}/connectors/{connector_id}")
def get_connector(station_id: str, connector_id: str):
    return _connector(repo.get_connector(station_id, connector_id))


@app.post("/reservations")
def reserve(req: ReserveRequest):
    current = repo.get_connector(req.station_id, req.connector_id)
    if current.get("connector_type") == "ULTRA" and not get_flags().is_enabled("ENABLE_FAST_CHARGE_BOOST"):
        raise BusinessError(
            "FAST_CHARGE_DISABLED",
            "La reserva prioritaria de ultra-carga está deshabilitada (ENABLE_FAST_CHARGE_BOOST=false)",
            403,
        )
    item = repo.reserve(req.station_id, req.connector_id, req.saga_id, req.fleet_id)
    log.info("conector reservado", extra={"station_id": req.station_id, "connector_id": req.connector_id})
    return _connector(item)


@app.post("/reservations/{saga_id}/charging")
def mark_charging(saga_id: str, ref: ConnectorRef):
    return _connector(repo.mark_charging(ref.station_id, ref.connector_id, saga_id))


@app.post("/reservations/{saga_id}/release")
def release(saga_id: str, ref: ConnectorRef):
    result = repo.release(ref.station_id, ref.connector_id, saga_id)
    log.info(
        "compensación: liberar conector" if result["released"] else "liberación repetida (idempotente, sin cambios)",
        extra={"station_id": ref.station_id, "connector_id": ref.connector_id, **{"released": result["released"]}},
    )
    result["connector"] = _connector(result["connector"])
    return result
