"""Integración: servicios + endpoint GraphQL contra tablas DynamoDB reales en Floci.

Requiere AWS_ENDPOINT_URL=http://localhost:4566 (en CI: Floci como service container).
"""

import boto3
import pytest

from tests.conftest import set_flag
from tests.queries import FLAGS, RESERVE, RETRY, STATIONS, WALLET, connector_status

pytestmark = pytest.mark.integration


def _input(fleet="fleet-rapido", connector="c1"):
    return {"input": {"fleetId": fleet, "stationId": "st-bog-01", "connectorId": connector, "estimatedKwh": 30}}


async def test_tables_exist_in_floci(aws_env):
    import os

    names = boto3.client("dynamodb", endpoint_url=os.environ["AWS_ENDPOINT_URL"]).list_tables()["TableNames"]
    for kind in ("reservations", "billing", "dispatch", "sagas", "feature-flags"):
        assert f"aegisvolt-{kind}-{aws_env}" in names


async def test_graphql_happy_path_against_floci(gql):
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "COMPLETED"
    assert connector_status(await gql(STATIONS), "st-bog-01", "c1") == "CHARGING"


async def test_graphql_compensation_against_floci(gql):
    set_flag("SIMULATE_CHARGER_HARDWARE_FAULT", True)
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "COMPENSATED"
    replay = (await gql(RETRY, {"id": saga["sagaId"]}))["data"]["retryCompensation"]
    assert replay["status"] == "COMPENSATED"
    wallet = (await gql(WALLET, {"id": "fleet-rapido"}))["data"]["wallet"]
    assert wallet["balance"] == 500.0
    assert sorted(t["type"] for t in wallet["transactions"]) == ["HOLD", "REFUND"]


async def test_flags_isolated_per_environment(gql, aws_env):
    set_flag("SIMULATE_CHARGER_HARDWARE_FAULT", True)
    flags = {f["name"]: f["enabled"] for f in (await gql(FLAGS))["data"]["featureFlags"]}
    assert flags["SIMULATE_CHARGER_HARDWARE_FAULT"] is True
    import os

    other = boto3.resource("dynamodb", endpoint_url=os.environ["AWS_ENDPOINT_URL"]).Table(
        f"aegisvolt-feature-flags-{aws_env}"
    )
    assert other.get_item(Key={"flag_name": "SIMULATE_CHARGER_HARDWARE_FAULT"})["Item"]["enabled"] is True
