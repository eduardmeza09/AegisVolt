"""billing-wallet-service: verificación de fondos, cobro estimado y reembolso a la billetera de la flota."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.flags import get_flags
from aegis_common.web import create_app
from pydantic import BaseModel, Field

from . import pricing
from . import repository as repo

SERVICE = "billing-wallet"
log = logging.getLogger(f"aegisvolt.{SERVICE}")
app = create_app(SERVICE, readiness=lambda: dynamodb_table(get_settings().table("billing")).table_status)


class HoldRequest(BaseModel):
    saga_id: str
    fleet_id: str
    estimated_kwh: float = Field(gt=0, le=500)
    connector_type: str = "CCS2"


class RefundRequest(BaseModel):
    fleet_id: str
    reason: str = "SAGA_COMPENSATION"


class TopUpRequest(BaseModel):
    amount: float = Field(gt=0, le=100_000)
    request_id: str | None = None


def _wallet(item: dict) -> dict:
    return {
        "fleet_id": item["fleet_id"],
        "fleet_name": item.get("fleet_name", item["fleet_id"]),
        "balance": float(item.get("balance", 0)),
        "currency": item.get("currency", "USD"),
        "updated_at": item.get("updated_at"),
    }


def _txn(item: dict) -> dict:
    return {
        "id": item["sk"],
        "type": item.get("type"),
        "ref": item.get("ref"),
        "amount": float(item.get("amount", 0)),
        "surge_applied": bool(item.get("surge_applied", False)),
        "reason": item.get("reason"),
        "created_at": item.get("created_at"),
    }


@app.get("/quote")
def quote(connector_type: str = "CCS2", kwh: float = 30):
    surge = get_flags().is_enabled("ENABLE_DYNAMIC_SURGE_PRICING")
    return pricing.quote(connector_type, kwh, surge).as_dict()


@app.get("/wallets")
def wallets():
    return [_wallet(w) for w in repo.list_wallets()]


@app.get("/wallets/{fleet_id}")
def wallet(fleet_id: str, limit: int = 50):
    w = _wallet(repo.get_wallet(fleet_id))
    w["transactions"] = [_txn(t) for t in repo.list_transactions(fleet_id, limit)]
    return w


@app.post("/holds")
def hold(req: HoldRequest):
    q = pricing.quote(req.connector_type, req.estimated_kwh, get_flags().is_enabled("ENABLE_DYNAMIC_SURGE_PRICING"))
    res = repo.hold(
        req.fleet_id,
        req.saga_id,
        q.total,
        {"surge_applied": q.surge_applied, "price_per_kwh": q.price_per_kwh, "kwh": q.kwh},
    )
    log.info(
        "retención repetida (idempotente)" if res["idempotent_replay"] else "saldo retenido",
        extra={"fleet_id": req.fleet_id, "amount": float(q.total), "surge_applied": q.surge_applied},
    )
    return {
        "idempotent_replay": res["idempotent_replay"],
        "amount": float(res["txn"]["amount"]),
        "quote": q.as_dict(),
        "wallet": _wallet(res["wallet"]),
    }


@app.post("/holds/{saga_id}/refund")
def refund(saga_id: str, req: RefundRequest):
    res = repo.refund(req.fleet_id, saga_id, req.reason)
    if res["refunded"]:
        log.info("compensación: saldo reembolsado", extra={"fleet_id": req.fleet_id, "amount": float(res["amount"])})
    else:
        log.info("reembolso no aplicado (idempotente)", extra={"fleet_id": req.fleet_id, "why": res.get("reason")})
    return {
        "refunded": res["refunded"],
        "idempotent_replay": res["idempotent_replay"],
        "reason": res.get("reason"),
        "amount": float(res.get("amount", 0)),
        "wallet": _wallet(res["wallet"]),
    }


@app.post("/wallets/{fleet_id}/topup")
def topup(fleet_id: str, req: TopUpRequest):
    amount = Decimal(str(req.amount)).quantize(Decimal("0.01"))
    w = repo.topup(fleet_id, req.request_id or str(uuid.uuid4()), amount)
    log.info("recarga de saldo", extra={"fleet_id": fleet_id, "amount": float(amount)})
    return _wallet(w)
