"""Flow: auditoría de consistencia de las transacciones SAGA en DynamoDB.

Para cada saga del ambiente cruza el log del orquestador (aegisvolt-sagas-<env>) con las tablas
de los servicios (reservations, billing, dispatch) y clasifica:
  - HUÉRFANA: estado no terminal sin avanzar por más de `orphan_minutes`, o COMPENSATION_FAILED
  - INCONSISTENTE: p.ej. COMPENSATED sin asiento REFUND, o conector aún retenido por la saga
  - OK
Publica métricas (OrphanSagas, InconsistentSagas, SagasCompensated...) en CloudWatch y artefactos en Prefect.
Con auto_heal=True reintenta las compensaciones (idempotentes) de las sagas huérfanas vía GraphQL.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from prefect import flow, get_run_logger, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact

from .common import ENVS, cw_log, graphql, put_metrics, table

TERMINAL = {"COMPLETED", "FINISHED", "COMPENSATED", "FAILED"}
RETRY = "mutation($id: String!) { retryCompensation(sagaId: $id) { status } }"


@task
def load_sagas(env: str) -> list[dict]:
    t, items, kw = table(f"aegisvolt-sagas-{env}"), [], {}
    while True:
        resp = t.scan(**kw)
        items += [i for i in resp.get("Items", []) if not i["saga_id"].startswith("REQ#")]
        if "LastEvaluatedKey" not in resp:
            return items
        kw["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _connector(env: str, s: dict) -> dict:
    return table(f"aegisvolt-reservations-{env}").get_item(
        Key={"station_id": s["station_id"], "connector_id": s["connector_id"]}).get("Item", {})


def _txn(env: str, s: dict, kind: str) -> dict | None:
    return table(f"aegisvolt-billing-{env}").get_item(
        Key={"fleet_id": s["fleet_id"], "sk": f"TXN#{s['saga_id']}#{kind}"}).get("Item")


def _session(env: str, s: dict) -> dict | None:
    return table(f"aegisvolt-dispatch-{env}").get_item(Key={"session_id": s["saga_id"], "sk": "META"}).get("Item")


@task
def audit_saga(env: str, s: dict, orphan_minutes: int) -> dict:
    status, problems = s["status"], []
    updated = datetime.fromisoformat(s["updated_at"])
    held_by_saga = _connector(env, s).get("saga_id") == s["saga_id"]
    if status == "COMPENSATION_FAILED":
        problems.append("compensación agotó reintentos")
    elif status not in TERMINAL and datetime.now(UTC) - updated > timedelta(minutes=orphan_minutes):
        problems.append(f"sin avanzar desde hace >{orphan_minutes} min (estado {status})")
    elif status == "COMPENSATED":
        if _txn(env, s, "HOLD") and not _txn(env, s, "REFUND"):
            problems.append("tiene HOLD pero no REFUND")
        if held_by_saga:
            problems.append("el conector sigue retenido por la saga")
    elif status == "COMPLETED":
        if not _session(env, s):
            problems.append("COMPLETED sin sesión en energy-dispatch")
        if not held_by_saga:
            problems.append("COMPLETED pero el conector no está asignado a la saga")
    elif status in ("FINISHED", "FAILED") and held_by_saga:
        problems.append("el conector sigue retenido tras finalizar")
    orphan = status == "COMPENSATION_FAILED" or (status not in TERMINAL and bool(problems))
    return {"saga_id": s["saga_id"], "status": status, "orphan": orphan,
            "inconsistent": bool(problems) and not orphan, "problems": problems,
            "error_code": s.get("error_code"), "updated_at": s["updated_at"]}


@flow(name="aegisvolt-saga-consistency-audit", log_prints=True)
def saga_consistency_audit(envs: list[str] = ENVS, orphan_minutes: int = 5, auto_heal: bool = False) -> dict:
    log = get_run_logger()
    summary_rows, md, result = [], ["# Auditoría SAGA\n"], {}
    for env in envs:
        try:
            sagas = load_sagas(env)
        except Exception as exc:
            log.warning(f"[{env}] no se pudo leer la tabla de sagas: {exc}")
            continue
        audits = [audit_saga(env, s, orphan_minutes) for s in sagas]
        counts = Counter(a["status"] for a in audits)
        orphans = [a for a in audits if a["orphan"]]
        inconsistent = [a for a in audits if a["inconsistent"]]
        healed = 0
        if auto_heal:
            for a in orphans:
                try:
                    graphql(env, RETRY, {"id": a["saga_id"]})
                    healed += 1
                except Exception as exc:
                    log.warning(f"[{env}] no se pudo re-compensar {a['saga_id']}: {exc}")
        metrics = {"OrphanSagas": len(orphans), "InconsistentSagas": len(inconsistent),
                   "SagasCompensatedTotal": counts.get("COMPENSATED", 0),
                   "SagasCompletedTotal": counts.get("COMPLETED", 0) + counts.get("FINISHED", 0),
                   "SagasAudited": len(audits)}
        put_metrics(env, metrics)
        cw_log(env, "saga-audit", **metrics)
        result[env] = {"counts": dict(counts), "orphans": orphans, "inconsistent": inconsistent, "healed": healed}
        summary_rows.append({"ambiente": env, "auditadas": len(audits),
                             "completadas": metrics["SagasCompletedTotal"],
                             "compensadas": counts.get("COMPENSATED", 0), "fallidas": counts.get("FAILED", 0),
                             "huérfanas": len(orphans), "inconsistentes": len(inconsistent), "re-compensadas": healed})
        md.append(f"## {env}\n\nEstados: {dict(counts)}\n")
        for a in orphans + inconsistent:
            md.append(f"- `{a['saga_id']}` **{a['status']}** {a['error_code'] or ''}: {'; '.join(a['problems'])}")
        recent = sorted((a for a in audits if a["status"] == "COMPENSATED"), key=lambda a: a["updated_at"])[-5:]
        if recent:
            md.append("\nÚltimas compensadas (rastreables en CloudWatch con `scripts/trace.sh "
                      f"{env} <correlation_id>`):")
            md += [f"- `{a['saga_id']}` ({a['error_code']})" for a in recent]
        md.append("")
        (log.warning if orphans or inconsistent else log.info)(
            f"[{env}] auditadas={len(audits)} huérfanas={len(orphans)} inconsistentes={len(inconsistent)}")
    create_table_artifact(key="aegisvolt-saga-audit", table=summary_rows, description="Consistencia SAGA por ambiente")
    create_markdown_artifact(key="aegisvolt-saga-audit-detail", markdown="\n".join(md))
    return result


if __name__ == "__main__":
    saga_consistency_audit()
