"""Billetera de flota + ledger idempotente en aegisvolt-billing-<env>.

PK fleet_id; SK:
  WALLET                      -> saldo actual
  TXN#<saga_id>#HOLD          -> retención (cobro estimado) del paso 2
  TXN#<saga_id>#REFUND        -> reembolso (compensación)
  TXN#<request_id>#TOPUP      -> recarga

Cada movimiento es una TransactWriteItems: Put del asiento con attribute_not_exists(sk) +
Update del saldo. Si llega dos veces la misma petición, el Put falla por condición y la
transacción entera se cancela => el dinero nunca se mueve dos veces (idempotencia).
"""

from __future__ import annotations

from decimal import Decimal

from aegis_common.aws import client, dynamodb_table
from aegis_common.config import get_settings
from aegis_common.time_utils import now_iso
from aegis_common.web import BusinessError
from botocore.exceptions import ClientError


def _name() -> str:
    return get_settings().table("billing")


def _table():
    return dynamodb_table(_name())


def _ddb():
    return client("dynamodb")


def get_wallet(fleet_id: str) -> dict:
    item = _table().get_item(Key={"fleet_id": fleet_id, "sk": "WALLET"}).get("Item")
    if not item:
        raise BusinessError("WALLET_NOT_FOUND", f"La flota {fleet_id} no tiene billetera", 404)
    return item


def list_wallets() -> list[dict]:
    items = _table().scan(FilterExpression="sk = :w", ExpressionAttributeValues={":w": "WALLET"}).get("Items", [])
    return sorted(items, key=lambda i: i["fleet_id"])


def list_transactions(fleet_id: str, limit: int = 50) -> list[dict]:
    resp = _table().query(
        KeyConditionExpression="fleet_id = :f AND begins_with(sk, :t)",
        ExpressionAttributeValues={":f": fleet_id, ":t": "TXN#"},
    )
    return sorted(resp.get("Items", []), key=lambda i: i.get("created_at", ""), reverse=True)[:limit]


def get_txn(fleet_id: str, ref: str, kind: str) -> dict | None:
    return _table().get_item(Key={"fleet_id": fleet_id, "sk": f"TXN#{ref}#{kind}"}).get("Item")


def _reasons(exc: ClientError) -> list[str]:
    return [r.get("Code", "None") for r in exc.response.get("CancellationReasons", [])]


def _txn_put(fleet_id: str, ref: str, kind: str, amount: Decimal, extra: dict) -> dict:
    item = {
        "fleet_id": {"S": fleet_id},
        "sk": {"S": f"TXN#{ref}#{kind}"},
        "type": {"S": kind},
        "ref": {"S": ref},
        "amount": {"N": str(amount)},
        "created_at": {"S": now_iso()},
    }
    for k, v in extra.items():
        if isinstance(v, bool):
            item[k] = {"BOOL": v}
        elif isinstance(v, int | float | Decimal):
            item[k] = {"N": str(v)}
        elif v is not None:
            item[k] = {"S": str(v)}
    return {
        "Put": {
            "TableName": _name(),
            "Item": item,
            "ConditionExpression": "attribute_not_exists(sk)",
        }
    }


def hold(fleet_id: str, saga_id: str, amount: Decimal, details: dict) -> dict:
    """Paso 2 SAGA: descuenta el saldo estimado. 402 si no hay fondos."""
    get_wallet(fleet_id)
    try:
        _ddb().transact_write_items(
            TransactItems=[
                _txn_put(fleet_id, saga_id, "HOLD", amount, details),
                {
                    "Update": {
                        "TableName": _name(),
                        "Key": {"fleet_id": {"S": fleet_id}, "sk": {"S": "WALLET"}},
                        "UpdateExpression": "SET balance = balance - :a, updated_at = :now",
                        "ConditionExpression": "balance >= :a",
                        "ExpressionAttributeValues": {":a": {"N": str(amount)}, ":now": {"S": now_iso()}},
                    }
                },
            ]
        )
        return {"idempotent_replay": False, "txn": get_txn(fleet_id, saga_id, "HOLD"), "wallet": get_wallet(fleet_id)}
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        reasons = _reasons(exc)
        if reasons and reasons[0] == "ConditionalCheckFailed":  # el HOLD ya existe => reintento
            return {
                "idempotent_replay": True,
                "txn": get_txn(fleet_id, saga_id, "HOLD"),
                "wallet": get_wallet(fleet_id),
            }
        wallet = get_wallet(fleet_id)
        raise BusinessError(
            "INSUFFICIENT_FUNDS",
            f"Fondos insuficientes: saldo {wallet['balance']} < cobro estimado {amount}",
            402,
        ) from exc


def refund(fleet_id: str, saga_id: str, reason: str) -> dict:
    """Compensación del paso 2: devuelve exactamente lo retenido. Idempotente."""
    held = get_txn(fleet_id, saga_id, "HOLD")
    if not held:
        return {"refunded": False, "idempotent_replay": False, "reason": "NO_HOLD", "wallet": get_wallet(fleet_id)}
    amount = Decimal(str(held["amount"]))
    try:
        _ddb().transact_write_items(
            TransactItems=[
                _txn_put(fleet_id, saga_id, "REFUND", amount, {"reason": reason}),
                {
                    "Update": {
                        "TableName": _name(),
                        "Key": {"fleet_id": {"S": fleet_id}, "sk": {"S": "WALLET"}},
                        "UpdateExpression": "SET balance = balance + :a, updated_at = :now",
                        "ExpressionAttributeValues": {":a": {"N": str(amount)}, ":now": {"S": now_iso()}},
                    }
                },
            ]
        )
        return {"refunded": True, "idempotent_replay": False, "amount": amount, "wallet": get_wallet(fleet_id)}
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        return {"refunded": False, "idempotent_replay": True, "amount": amount, "wallet": get_wallet(fleet_id)}


def topup(fleet_id: str, request_id: str, amount: Decimal) -> dict:
    get_wallet(fleet_id)
    try:
        _ddb().transact_write_items(
            TransactItems=[
                _txn_put(fleet_id, request_id, "TOPUP", amount, {}),
                {
                    "Update": {
                        "TableName": _name(),
                        "Key": {"fleet_id": {"S": fleet_id}, "sk": {"S": "WALLET"}},
                        "UpdateExpression": "SET balance = balance + :a, updated_at = :now",
                        "ExpressionAttributeValues": {":a": {"N": str(amount)}, ":now": {"S": now_iso()}},
                    }
                },
            ]
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "TransactionCanceledException":
            raise
    return get_wallet(fleet_id)
