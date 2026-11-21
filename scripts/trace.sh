#!/usr/bin/env bash
# Traza una SAGA por correlation_id en todos los log groups CloudWatch del ambiente.
#   ./scripts/trace.sh <env> <correlation_id>
#   ./scripts/trace.sh <env> last-compensated     # usa la última saga COMPENSATED del ambiente
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/services/.venv/Scripts/python"; [[ -x "$PY" ]] || PY="$ROOT/services/.venv/bin/python"; [[ -x "$PY" ]] || PY=python
export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-test} AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-test}
exec "$PY" - "${1:?uso: trace.sh <env> <correlation_id|last-compensated>}" "${2:?falta correlation_id}" <<'PY'
import json, os, sys
import boto3
from boto3.dynamodb.conditions import Key

env, cid = sys.argv[1], sys.argv[2]
kw = {"region_name": "us-east-1", "endpoint_url": os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")}
if cid == "last-compensated":
    items = boto3.resource("dynamodb", **kw).Table(f"aegisvolt-sagas-{env}").query(
        IndexName="by_status", KeyConditionExpression=Key("status").eq("COMPENSATED"),
        ScanIndexForward=False, Limit=1)["Items"]
    if not items:
        sys.exit("no hay sagas COMPENSATED en " + env)
    cid = items[0]["saga_id"]
print(f"correlation_id = {cid}   (ambiente {env})\n")
logs = boto3.client("logs", **kw)
rows = []
for g in logs.describe_log_groups(logGroupNamePrefix=f"/aegisvolt/{env}/")["logGroups"]:
    for e in logs.filter_log_events(logGroupName=g["logGroupName"], filterPattern=f'"{cid}"').get("events", []):
        try:
            rows.append((g["logGroupName"], json.loads(e["message"])))
        except ValueError:
            pass
for group, r in sorted(rows, key=lambda x: x[1]["timestamp"]):
    print(f"{r['timestamp'][11:23]}  {r['level']:<7} {r['service']:<20} {str(r.get('step') or '-'):<20} {r['message']}")
print(f"\n--- {len(rows)} eventos en {len({g for g, _ in rows})} log groups (/aegisvolt/{env}/*)")
PY
