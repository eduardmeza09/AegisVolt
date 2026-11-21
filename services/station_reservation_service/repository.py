"""Acceso a la tabla aegisvolt-reservations-<env> (Database-per-Service: solo este servicio la escribe).

Item = un conector de una estación: PK station_id, SK connector_id.
Estados: AVAILABLE -> RESERVED -> CHARGING -> AVAILABLE (o FAULT).
Todas las transiciones usan ConditionExpression => son atómicas e idempotentes por saga_id.
"""

from __future__ import annotations

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.time_utils import now_iso
from aegis_common.web import BusinessError
from botocore.exceptions import ClientError


def _table():
    return dynamodb_table(get_settings().table("reservations"))


def _is_conditional(exc: ClientError) -> bool:
    return exc.response["Error"]["Code"] == "ConditionalCheckFailedException"


def list_connectors() -> list[dict]:
    table, items, kwargs = _table(), [], {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def get_connector(station_id: str, connector_id: str) -> dict:
    item = _table().get_item(Key={"station_id": station_id, "connector_id": connector_id}).get("Item")
    if not item:
        raise BusinessError("CONNECTOR_NOT_FOUND", f"Conector {station_id}/{connector_id} no existe", 404)
    return item


def reserve(station_id: str, connector_id: str, saga_id: str, fleet_id: str) -> dict:
    """Paso 1 SAGA. AVAILABLE -> RESERVED. Si ya lo reservó esta misma saga, responde igual (idempotente)."""
    try:
        resp = _table().update_item(
            Key={"station_id": station_id, "connector_id": connector_id},
            UpdateExpression="SET #s = :reserved, saga_id = :saga, fleet_id = :fleet, updated_at = :now "
            "ADD version :one",
            ConditionExpression="attribute_exists(station_id) AND (#s = :available OR saga_id = :saga)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":reserved": "RESERVED",
                ":available": "AVAILABLE",
                ":saga": saga_id,
                ":fleet": fleet_id,
                ":now": now_iso(),
                ":one": 1,
            },
            ReturnValues="ALL_NEW",
        )
        return resp["Attributes"]
    except ClientError as exc:
        if not _is_conditional(exc):
            raise
        current = get_connector(station_id, connector_id)
        raise BusinessError(
            "CONNECTOR_UNAVAILABLE",
            f"Conector {station_id}/{connector_id} no disponible (estado {current.get('status')})",
            409,
        ) from exc


def mark_charging(station_id: str, connector_id: str, saga_id: str) -> dict:
    """Tras activar el cargador: RESERVED -> CHARGING (solo el dueño de la reserva)."""
    try:
        resp = _table().update_item(
            Key={"station_id": station_id, "connector_id": connector_id},
            UpdateExpression="SET #s = :charging, updated_at = :now ADD version :one",
            ConditionExpression="saga_id = :saga AND #s IN (:reserved, :charging)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":charging": "CHARGING",
                ":reserved": "RESERVED",
                ":saga": saga_id,
                ":now": now_iso(),
                ":one": 1,
            },
            ReturnValues="ALL_NEW",
        )
        return resp["Attributes"]
    except ClientError as exc:
        if not _is_conditional(exc):
            raise
        raise BusinessError("RESERVATION_NOT_OWNED", "La reserva no pertenece a esta saga", 409) from exc


def release(station_id: str, connector_id: str, saga_id: str) -> dict:
    """Compensación (o fin de carga): libera el conector SOLO si pertenece a esta saga.

    Si ya fue liberado (mensaje duplicado) la condición falla y se responde éxito sin cambios:
    la compensación es idempotente y nunca libera una reserva de otra saga.
    """
    try:
        resp = _table().update_item(
            Key={"station_id": station_id, "connector_id": connector_id},
            UpdateExpression="SET #s = :available, updated_at = :now, last_saga_id = :saga "
            "REMOVE saga_id, fleet_id ADD version :one",
            ConditionExpression="saga_id = :saga",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":available": "AVAILABLE", ":saga": saga_id, ":now": now_iso(), ":one": 1},
            ReturnValues="ALL_NEW",
        )
        return {"released": True, "idempotent_replay": False, "connector": resp["Attributes"]}
    except ClientError as exc:
        if not _is_conditional(exc):
            raise
        return {"released": False, "idempotent_replay": True, "connector": get_connector(station_id, connector_id)}
