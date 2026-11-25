"""Flow: reconstruye en Prefect la traza CloudWatch de una SAGA a partir de su correlation_id."""

from __future__ import annotations

import json

from prefect import artifacts, flow

from .common import client


@flow(name="aegisvolt-trace-saga", log_prints=True)
def trace_saga(env: str, correlation_id: str) -> int:
    logs, rows = client("logs"), []
    for g in logs.describe_log_groups(logGroupNamePrefix=f"/aegisvolt/{env}/")["logGroups"]:
        for e in logs.filter_log_events(logGroupName=g["logGroupName"],
                                        filterPattern=f'"{correlation_id}"').get("events", []):
            try:
                rows.append(json.loads(e["message"]))
            except ValueError:
                pass
    rows.sort(key=lambda r: r["timestamp"])
    md = [f"# Traza `{correlation_id}` ({env})\n", "| hora | nivel | servicio | paso | mensaje |", "|---|---|---|---|---|"]
    md += [f"| {r['timestamp'][11:23]} | {r['level']} | {r['service']} | {r.get('step') or '-'} | {r['message']} |"
           for r in rows]
    artifacts.create_markdown_artifact(key="aegisvolt-saga-trace", markdown="\n".join(md))
    print(f"{len(rows)} eventos encontrados en /aegisvolt/{env}/*")
    return len(rows)
