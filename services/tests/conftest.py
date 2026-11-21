"""Fixtures comunes.

- Unit tests: DynamoDB en memoria con moto (aislado, rápido).
- Integration tests (tests/integration, marcador `integration`): DynamoDB real de Floci
  si AWS_ENDPOINT_URL está definido.
"""

from __future__ import annotations

import os
import uuid

import boto3
import httpx
import pytest

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ["AEGIS_SKIP_APP"] = "1"
os.environ["TELEMETRY_SIMULATOR"] = "false"
os.environ["FLAGS_CACHE_TTL"] = "0"
os.environ["ADMIN_TOKEN"] = "test-admin"

from aegis_common import aws as aws_mod  # noqa: E402
from aegis_common import config as config_mod  # noqa: E402
from aegis_common import flags as flags_mod  # noqa: E402
from aegis_common.tables import create_all_tables  # noqa: E402

FLEETS = [("fleet-rapido", "Rápido Express", "500.00"), ("fleet-pobre", "Flota Sin Fondos", "1.00")]
CONNECTORS = [
    ("st-bog-01", "Electrolinera Calle 80", "Bogotá", "c1", "CCS2", 50),
    ("st-bog-01", "Electrolinera Calle 80", "Bogotá", "c2", "ULTRA", 350),
    ("st-med-01", "Hub El Poblado", "Medellín", "c1", "CCS2", 150),
]


def seed(env: str, endpoint: str | None) -> None:
    ddb = boto3.resource("dynamodb", region_name="us-east-1", endpoint_url=endpoint)
    res = ddb.Table(f"aegisvolt-reservations-{env}")
    for sid, name, city, cid, ctype, kw in CONNECTORS:
        res.put_item(
            Item={
                "station_id": sid,
                "connector_id": cid,
                "station_name": name,
                "city": city,
                "lat": "4.6",
                "lng": "-74.1",
                "connector_type": ctype,
                "power_kw": kw,
                "status": "AVAILABLE",
                "version": 0,
            }
        )
    bil = ddb.Table(f"aegisvolt-billing-{env}")
    from decimal import Decimal

    for fid, fname, bal in FLEETS:
        bil.put_item(
            Item={"fleet_id": fid, "sk": "WALLET", "fleet_name": fname, "balance": Decimal(bal), "currency": "USD"}
        )
    flags = ddb.Table(f"aegisvolt-feature-flags-{env}")
    for name in flags_mod.KNOWN_FLAGS:
        flags.put_item(
            Item={
                "flag_name": name,
                "enabled": name == "ENABLE_FAST_CHARGE_BOOST",
                "description": flags_mod.KNOWN_FLAGS[name],
            }
        )


def _reset(env: str):
    os.environ["ENV"] = env
    config_mod.get_settings.cache_clear()
    aws_mod.reset_clients()
    flags_mod.reset_flags()


@pytest.fixture
def aws_env(request):
    """Ambiente aislado por test. Usa Floci si es integración y hay endpoint; si no, moto."""
    integration = request.node.get_closest_marker("integration") is not None
    endpoint = os.getenv("AWS_ENDPOINT_URL") if integration else None
    env = f"t{uuid.uuid4().hex[:8]}"
    if integration:
        if not endpoint:
            pytest.skip("integration: definir AWS_ENDPOINT_URL (Floci)")
        _reset(env)
        create_all_tables(boto3.client("dynamodb", region_name="us-east-1", endpoint_url=endpoint), env)
        seed(env, endpoint)
        yield env
        client = boto3.client("dynamodb", region_name="us-east-1", endpoint_url=endpoint)
        for t in client.list_tables()["TableNames"]:
            if t.endswith(f"-{env}"):
                client.delete_table(TableName=t)
        return
    from moto import mock_aws

    saved = os.environ.pop("AWS_ENDPOINT_URL", None)
    with mock_aws():
        _reset(env)
        create_all_tables(boto3.client("dynamodb", region_name="us-east-1"), env)
        seed(env, None)
        yield env
    if saved:
        os.environ["AWS_ENDPOINT_URL"] = saved


def set_flag(name: str, enabled: bool) -> None:
    flags_mod.get_flags().set(name, enabled, updated_by="test")


@pytest.fixture
def apps(aws_env):
    """Las 4 apps FastAPI conectadas en memoria (ASGITransport) => GraphQL de punta a punta sin red."""
    from billing_wallet_service.main import app as billing
    from energy_dispatch_service.main import app as dispatch
    from graphql_gateway.clients import ServiceClient, Services
    from graphql_gateway.main import build_app
    from station_reservation_service.main import app as station

    services = Services(
        ServiceClient("http://station", transport=httpx.ASGITransport(app=station)),
        ServiceClient("http://billing", transport=httpx.ASGITransport(app=billing)),
        ServiceClient("http://dispatch", transport=httpx.ASGITransport(app=dispatch)),
    )
    gateway = build_app(services)
    return {"gateway": gateway, "station": station, "billing": billing, "dispatch": dispatch, "services": services}


@pytest.fixture
async def gql(apps):
    transport = httpx.ASGITransport(app=apps["gateway"])
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as client:

        async def run(query: str, variables: dict | None = None, headers: dict | None = None) -> dict:
            r = await client.post(
                "/graphql", json={"query": query, "variables": variables or {}}, headers=headers or {}
            )
            assert r.status_code == 200, r.text
            return r.json()

        yield run
