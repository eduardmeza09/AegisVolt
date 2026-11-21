"""Utilidades compartidas por los flujos: clientes AWS (Floci), descubrimiento de endpoints y métricas."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime

import boto3
import httpx

ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
REGION = os.getenv("AWS_REGION", "us-east-1")
ENVS = ["dev", "test", "prod"]
TABLE_KINDS = ["reservations", "billing", "dispatch", "sagas", "feature-flags"]
SERVICE = "prefect-observability"

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


def client(name: str):
    return boto3.client(name, region_name=REGION, endpoint_url=ENDPOINT)


def table(name: str):
    return boto3.resource("dynamodb", region_name=REGION, endpoint_url=ENDPOINT).Table(name)


def graphql_url(env: str) -> str | None:
    """Descubre el endpoint del ambiente a partir del API Gateway aegisvolt-<env>-api."""
    for api in client("apigatewayv2").get_apis().get("Items", []):
        if api["Name"] == f"aegisvolt-{env}-api":
            return f"{ENDPOINT}/restapis/{api['ApiId']}/{env}/_user_request_/graphql"
    return None


def graphql(env: str, query: str, variables: dict | None = None) -> dict:
    url = graphql_url(env)
    if not url:
        raise RuntimeError(f"no hay API Gateway para {env}")
    r = httpx.post(url, json={"query": query, "variables": variables or {}}, timeout=15)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def put_metrics(env: str, values: dict[str, float]) -> None:
    client("cloudwatch").put_metric_data(
        Namespace=f"AegisVolt/{env}",
        MetricData=[
            {"MetricName": k, "Dimensions": [{"Name": "Service", "Value": SERVICE}], "Value": float(v), "Unit": "Count"}
            for k, v in values.items()
        ],
    )


def cw_log(env: str, message: str, **fields) -> None:
    """Escribe un evento JSON en /aegisvolt/<env>/prefect-observability (trazabilidad del propio monitor)."""
    logs, group, stream = client("logs"), f"/aegisvolt/{env}/{SERVICE}", "flows"
    for fn, kw in ((logs.create_log_group, {"logGroupName": group}),
                   (logs.create_log_stream, {"logGroupName": group, "logStreamName": stream})):
        try:
            fn(**kw)
        except logs.exceptions.ResourceAlreadyExistsException:
            pass
    event = {"timestamp": datetime.now(UTC).isoformat(), "level": "INFO", "service": SERVICE, "env": env,
             "message": message, **fields}
    logs.put_log_events(logGroupName=group, logStreamName=stream,
                        logEvents=[{"timestamp": int(time.time() * 1000), "message": json.dumps(event, default=str)}])
