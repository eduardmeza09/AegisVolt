"""Persistencia del log de la SAGA (tabla aegisvolt-sagas-<env>, propiedad del orquestador)."""

from __future__ import annotations

from decimal import Decimal

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.time_utils import now_iso
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TERMINAL = {"COMPLETED", "FINISHED", "COMPENSATED", "FAILED", "COMPENSATION_FAILED"}


def _table():
    return dynamodb_table(get_settings().table("sagas"))


def _clean(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def claim_request(client_request_id: str, saga_id: str) -> str | None:
    """Deduplicación atómica de la mutación. Devuelve el saga_id existente si ya se procesó."""
    try:
        _table().put_item(
            Item={"saga_id": f"REQ#{client_request_id}", "target_saga_id": saga_id, "created_at": now_iso()},
            ConditionExpression="attribute_not_exists(saga_id)",
        )
        return None
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        item = _table().get_item(Key={"saga_id": f"REQ#{client_request_id}"}).get("Item")
        return item["target_saga_id"] if item else None


def create(saga: dict) -> dict:
    _table().put_item(Item=_clean(saga), ConditionExpression="attribute_not_exists(saga_id)")
    return saga


def get(saga_id: str) -> dict | None:
    return _table().get_item(Key={"saga_id": saga_id}, ConsistentRead=True).get("Item")


def transition(saga_id: str, status: str, step: dict | None = None, **fields) -> dict:
    """Persiste el nuevo estado ANTES de invocar el siguiente paso (log auditable)."""
    now = now_iso()
    names, values = {"#s": "status"}, {":s": status, ":now": now}
    expr = ["#s = :s", "updated_at = :now"]
    for i, (k, v) in enumerate(fields.items()):
        names[f"#f{i}"], values[f":f{i}"] = k, _clean(v)
        expr.append(f"#f{i} = :f{i}")
    if step:
        values[":step"] = [_clean({**step, "at": now})]
        values[":empty"] = []
        expr.append("steps = list_append(if_not_exists(steps, :empty), :step)")
    resp = _table().update_item(
        Key={"saga_id": saga_id},
        UpdateExpression="SET " + ", ".join(expr),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return resp["Attributes"]


def list_sagas(status: str | None = None, limit: int = 50) -> list[dict]:
    table = _table()
    if status:
        resp = table.query(
            IndexName="by_status", KeyConditionExpression=Key("status").eq(status), ScanIndexForward=False, Limit=limit
        )
        items = resp.get("Items", [])
    else:
        items, kwargs = [], {}
        while True:
            resp = table.scan(**kwargs)
            items.extend(i for i in resp.get("Items", []) if not i["saga_id"].startswith("REQ#"))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)[:limit]
