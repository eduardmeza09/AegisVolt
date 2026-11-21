"""Registra los deployments programados en el servidor Prefect y los ejecuta (proceso long-running).

    cd observability/prefect && PREFECT_API_URL=http://localhost:4200/api uv run python serve.py

- aegisvolt-environment-health       cada 5 min
- aegisvolt-saga-consistency-audit   cada 10 min
- aegisvolt-trace-saga               bajo demanda (parámetros env + correlation_id)
"""

from prefect import serve

from flows.health import environment_health
from flows.saga_audit import saga_consistency_audit
from flows.trace import trace_saga

if __name__ == "__main__":
    serve(
        environment_health.to_deployment(name="every-5-min", interval=300, tags=["aegisvolt", "health"]),
        saga_consistency_audit.to_deployment(name="every-10-min", interval=600, tags=["aegisvolt", "saga"]),
        trace_saga.to_deployment(name="on-demand", tags=["aegisvolt", "trace"]),
    )
