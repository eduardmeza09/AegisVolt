"""Flow: salud de los 3 ambientes (GraphQL vía API Gateway, DynamoDB, EKS, Rollouts y log groups)."""

from __future__ import annotations

import json
import subprocess

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_table_artifact

from .common import ENVS, TABLE_KINDS, client, cw_log, graphql, put_metrics


@task(retries=2, retry_delay_seconds=3)
def check_graphql(env: str) -> dict:
    data = graphql(env, "{ environment { name version } featureFlags { name enabled } }")
    flags = {f["name"]: f["enabled"] for f in data["featureFlags"]}
    return {"ok": data["environment"]["name"] == env, "version": data["environment"]["version"], "flags": flags}


@task
def check_tables(env: str) -> dict:
    ddb, status = client("dynamodb"), {}
    for kind in TABLE_KINDS:
        name = f"aegisvolt-{kind}-{env}"
        try:
            status[name] = ddb.describe_table(TableName=name)["Table"]["TableStatus"]
        except ddb.exceptions.ResourceNotFoundException:
            status[name] = "MISSING"
    return {"ok": all(s == "ACTIVE" for s in status.values()), "tables": status}


@task
def check_log_groups(env: str) -> dict:
    groups = client("logs").describe_log_groups(logGroupNamePrefix=f"/aegisvolt/{env}/")["logGroups"]
    return {"ok": len(groups) >= 4, "count": len(groups)}


@task
def check_eks() -> dict:
    cluster = client("eks").describe_cluster(name="aegisvolt-eks")["cluster"]
    return {"ok": cluster["status"] == "ACTIVE", "status": cluster["status"], "version": cluster["version"]}


@task
def check_rollouts(env: str) -> dict:
    try:
        out = subprocess.run(["kubectl", "get", "rollouts", "-n", f"aegisvolt-{env}", "-o", "json"],
                             capture_output=True, text=True, timeout=20, check=True).stdout
    except Exception as exc:  # kubectl no disponible o namespace inexistente
        return {"ok": False, "error": str(exc)[:120], "rollouts": {}}
    phases = {i["metadata"]["name"]: i.get("status", {}).get("phase", "?") for i in json.loads(out)["items"]}
    return {"ok": bool(phases) and all(p == "Healthy" for p in phases.values()), "rollouts": phases}


@flow(name="aegisvolt-environment-health", log_prints=True)
def environment_health(envs: list[str] = ENVS) -> dict:
    log = get_run_logger()
    eks = check_eks()
    rows, report = [], {}
    for env in envs:
        res = {"graphql": None, "tables": None, "logs": None, "rollouts": None}
        for key, fn in (("graphql", check_graphql), ("tables", check_tables), ("logs", check_log_groups),
                        ("rollouts", check_rollouts)):
            try:
                res[key] = fn(env)
            except Exception as exc:
                res[key] = {"ok": False, "error": str(exc)[:160]}
        healthy = all(v and v.get("ok") for v in res.values()) and eks["ok"]
        report[env] = {"healthy": healthy, **res}
        flags = (res["graphql"] or {}).get("flags", {})
        rows.append({
            "ambiente": env, "saludable": "✅" if healthy else "❌",
            "graphql": (res["graphql"] or {}).get("version", "ERROR"),
            "tablas": "5/5" if res["tables"]["ok"] else str(res["tables"]),
            "rollouts": ", ".join(f"{k}:{v}" for k, v in (res["rollouts"] or {}).get("rollouts", {}).items()) or "-",
            "flags_on": ", ".join(k for k, v in flags.items() if v) or "-",
        })
        put_metrics(env, {"EnvHealthy": 1 if healthy else 0})
        cw_log(env, "health-check", healthy=healthy)
        (log.info if healthy else log.warning)(f"[{env}] saludable={healthy}")
    create_table_artifact(key="aegisvolt-env-health", table=rows,
                          description=f"Salud de ambientes. EKS={eks['status']} (k8s {eks['version']})")
    return report


if __name__ == "__main__":
    environment_health()
