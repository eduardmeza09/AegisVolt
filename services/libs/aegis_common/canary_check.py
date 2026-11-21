"""Análisis del Canary (lo ejecuta un Job del AnalysisTemplate de Argo Rollouts).

1. Genera tráfico sintético contra la ruta del servicio (Traefik reparte 20 % al canary).
2. Espera el flush de métricas y consulta CloudWatch: RequestCount y ErrorCount con la
   dimensión PodTemplateHash = hash de la versión canary.
3. Sale con código 0 (promover) si error_rate < umbral y hay muestras suficientes; 1 (abortar) si no.

Uso: python -m aegis_common.canary_check --service billing-wallet --hash <hash> --url <url>
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

from .aws import client
from .config import get_settings


def generate_load(url: str, requests: int) -> tuple[int, int]:
    ok = err = 0
    with httpx.Client(timeout=5) as http:
        for _ in range(requests):
            try:
                r = http.get(url)
                ok += r.status_code < 500
                err += r.status_code >= 500
            except httpx.HTTPError:
                err += 1
            time.sleep(0.05)
    return ok, err


def metric_sum(cw, namespace: str, name: str, service: str, pod_hash: str, minutes: int) -> float:
    end = datetime.now(UTC)
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=name,
        Dimensions=[{"Name": "Service", "Value": service}, {"Name": "PodTemplateHash", "Value": pod_hash}],
        StartTime=end - timedelta(minutes=minutes),
        EndTime=end + timedelta(minutes=1),
        Period=60,
        Statistics=["Sum"],
    )
    return sum(p["Sum"] for p in resp.get("Datapoints", []))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--service", required=True)
    p.add_argument("--hash", required=True, dest="pod_hash")
    p.add_argument("--url", required=True)
    p.add_argument("--requests", type=int, default=150)
    p.add_argument("--max-error-rate", type=float, default=0.02)
    p.add_argument("--min-requests", type=int, default=10)
    p.add_argument("--window-minutes", type=int, default=5)
    a = p.parse_args()

    s = get_settings()
    print(f"[canary] servicio={a.service} hash={a.pod_hash} env={s.env} url={a.url}")
    ok, err = generate_load(a.url, a.requests)
    print(f"[canary] tráfico sintético enviado: ok={ok} err={err}")
    time.sleep(12)  # el MetricsRecorder hace flush cada 5 s

    cw = client("cloudwatch")
    total = metric_sum(cw, s.metrics_namespace, "RequestCount", a.service, a.pod_hash, a.window_minutes)
    errors = metric_sum(cw, s.metrics_namespace, "ErrorCount", a.service, a.pod_hash, a.window_minutes)
    rate = errors / total if total else 1.0
    print(f"[canary] CloudWatch {s.metrics_namespace}: RequestCount={total} ErrorCount={errors} rate={rate:.3f}")

    if total < a.min_requests:
        print(f"[canary] FALLO: muestras insuficientes ({total} < {a.min_requests})")
        return 1
    if rate >= a.max_error_rate:
        print(f"[canary] FALLO: error_rate {rate:.3f} >= umbral {a.max_error_rate}")
        return 1
    print(f"[canary] OK: error_rate {rate:.3f} < {a.max_error_rate} -> promover")
    return 0


if __name__ == "__main__":
    sys.exit(main())
