"""Sesiones de carga y telemetría en aegisvolt-dispatch-<env>.

PK session_id (= saga_id, lo que hace idempotente la activación); SK:
  META                 -> estado de la sesión (CHARGING | COMPLETED | STOPPED | FAULT)
  TELEMETRY#<iso ts>   -> lectura de telemetría (con TTL de 24 h)
"""

from __future__ import annotations

import time
from decimal import Decimal

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.time_utils import now_iso
from aegis_common.web import BusinessError
from botocore.exceptions import ClientError


def _table():
    return dynamodb_table(get_settings().table("dispatch"))


def get_session(session_id: str) -> dict | None:
    return _table().get_item(Key={"session_id": session_id, "sk": "META"}).get("Item")


def require_session(session_id: str) -> dict:
    s = get_session(session_id)
    if not s:
        raise BusinessError("SESSION_NOT_FOUND", f"Sesión {session_id} no existe", 404)
    return s


def record_fault(saga_id: str, data: dict, error: str) -> dict:
    item = {
        "session_id": saga_id,
        "sk": "META",
        "status": "FAULT",
        "error": error,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        **data,
    }
    _table().put_item(Item=item)
    return item


def start_session(saga_id: str, data: dict) -> tuple[dict, bool]:
    """Crea la sesión CHARGING. Si ya existe (reintento) devuelve la existente. -> (item, replay)."""
    item = {
        "session_id": saga_id,
        "sk": "META",
        "status": "CHARGING",
        "kwh_delivered": Decimal("0"),
        "soc_percent": Decimal("20"),
        "started_at": now_iso(),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        **data,
    }
    try:
        _table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(session_id) OR #s = :fault",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":fault": "FAULT"},
        )
        return item, False
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return require_session(saga_id), True


def list_sessions(status: str | None = None) -> list[dict]:
    table, items, kwargs = _table(), [], {"FilterExpression": "sk = :m", "ExpressionAttributeValues": {":m": "META"}}
    if status:
        kwargs["FilterExpression"] += " AND #s = :st"
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
        kwargs["ExpressionAttributeValues"][":st"] = status
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)


def set_status(session_id: str, status: str) -> dict:
    resp = _table().update_item(
        Key={"session_id": session_id, "sk": "META"},
        UpdateExpression="SET #s = :st, updated_at = :now",
        ConditionExpression="attribute_exists(session_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":st": status, ":now": now_iso()},
        ReturnValues="ALL_NEW",
    )
    return resp["Attributes"]


def add_telemetry(session_id: str, power_kw: Decimal, kwh: Decimal, soc: Decimal) -> None:
    ts = now_iso()
    table = _table()
    table.put_item(
        Item={
            "session_id": session_id,
            "sk": f"TELEMETRY#{ts}",
            "timestamp": ts,
            "power_kw": power_kw,
            "kwh_delivered": kwh,
            "soc_percent": soc,
            "expires_at": int(time.time()) + 86_400,
        }
    )
    table.update_item(
        Key={"session_id": session_id, "sk": "META"},
        UpdateExpression="SET kwh_delivered = :k, soc_percent = :s, power_kw_now = :p, updated_at = :now",
        ExpressionAttributeValues={":k": kwh, ":s": soc, ":p": power_kw, ":now": ts},
    )


def list_telemetry(session_id: str, limit: int = 60) -> list[dict]:
    resp = _table().query(
        KeyConditionExpression="session_id = :s AND begins_with(sk, :t)",
        ExpressionAttributeValues={":s": session_id, ":t": "TELEMETRY#"},
        ScanIndexForward=False,
        Limit=limit,
    )
    return list(reversed(resp.get("Items", [])))
