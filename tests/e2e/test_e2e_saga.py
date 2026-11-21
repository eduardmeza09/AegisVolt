"""E2E: flujo completo por HTTP contra un stack desplegado (docker compose o Kubernetes vía API Gateway).

Variables:
  GATEWAY_URL       p.ej. http://localhost:8080/graphql  ó  http://localhost:4566/restapis/<id>/dev/_user_request_/graphql
  E2E_ENV           ambiente cuyas tablas verificar (local | dev | test | prod)
  ADMIN_TOKEN       token para setFeatureFlag
  AWS_ENDPOINT_URL  Floci, para verificar los efectos en DynamoDB
"""

from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal

import boto3
import httpx
import pytest

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080/graphql")
ENV = os.getenv("E2E_ENV", "local")
ADMIN = os.getenv("ADMIN_TOKEN", "local-admin")
DDB = boto3.resource("dynamodb", endpoint_url=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
                     region_name="us-east-1")

RESERVE = """mutation($input: ReserveAndStartChargingInput!) { reserveAndStartCharging(input: $input) {
  sagaId status errorCode amount steps { name status } } }"""
SET_FLAG = "mutation($n: String!, $e: Boolean!) { setFeatureFlag(name: $n, enabled: $e) { enabled } }"
STOP = "mutation($id: String!) { stopCharging(sagaId: $id) { status } }"


def gql(query: str, variables: dict | None = None, admin: bool = False) -> dict:
    headers = {"x-admin-token": ADMIN} if admin else {}
    r = httpx.post(GATEWAY, json={"query": query, "variables": variables or {}}, headers=headers, timeout=30)
    r.raise_for_status()
    body = r.json()
    assert not body.get("errors"), body
    return body["data"]


def connector(station: str, cid: str) -> dict:
    return DDB.Table(f"aegisvolt-reservations-{ENV}").get_item(
        Key={"station_id": station, "connector_id": cid})["Item"]


def balance(fleet: str) -> Decimal:
    return DDB.Table(f"aegisvolt-billing-{ENV}").get_item(Key={"fleet_id": fleet, "sk": "WALLET"})["Item"]["balance"]


def set_fault(enabled: bool) -> None:
    gql(SET_FLAG, {"n": "SIMULATE_CHARGER_HARDWARE_FAULT", "e": enabled}, admin=True)
    time.sleep(6)  # TTL de caché de flags en los servicios (5 s): sin redespliegue


def reserve(fleet: str, station: str = "st-bog-02", cid: str = "c1") -> dict:
    return gql(RESERVE, {"input": {"fleetId": fleet, "stationId": station, "connectorId": cid, "estimatedKwh": 20,
                                   "clientRequestId": str(uuid.uuid4())}})["reserveAndStartCharging"]


@pytest.fixture(autouse=True)
def _no_fault():
    set_fault(False)
    yield
    set_fault(False)


def test_happy_path():
    before = balance("fleet-rapido")
    saga = reserve("fleet-rapido")
    assert saga["status"] == "COMPLETED", saga
    assert connector("st-bog-02", "c1")["status"] == "CHARGING"
    assert balance("fleet-rapido") == before - Decimal(str(saga["amount"]))
    assert gql(STOP, {"id": saga["sagaId"]})["stopCharging"]["status"] == "FINISHED"
    assert connector("st-bog-02", "c1")["status"] == "AVAILABLE"


def test_insufficient_funds_compensates_reservation():
    saga = reserve("fleet-sinfondos")
    assert saga["status"] == "COMPENSATED" and saga["errorCode"] == "INSUFFICIENT_FUNDS"
    assert connector("st-bog-02", "c1")["status"] == "AVAILABLE"


def test_hardware_fault_compensates_billing_and_reservation():
    before = balance("fleet-rapido")
    set_fault(True)
    saga = reserve("fleet-rapido")
    assert saga["status"] == "COMPENSATED" and saga["errorCode"] == "HARDWARE_FAULT", saga
    assert [s["name"] for s in saga["steps"]][-2:] == ["COMPENSATE_REFUND", "COMPENSATE_RELEASE"]
    assert balance("fleet-rapido") == before
    assert connector("st-bog-02", "c1")["status"] == "AVAILABLE"
    refund = DDB.Table(f"aegisvolt-billing-{ENV}").get_item(
        Key={"fleet_id": "fleet-rapido", "sk": f"TXN#{saga['sagaId']}#REFUND"}).get("Item")
    assert refund is not None
