"""Métricas custom en CloudWatch (namespace AegisVolt/<env>).

Dimensiones: Service y PodTemplateHash. El Canary filtra por el hash de la versión nueva
para calcular su tasa de error de forma aislada de la versión estable.
"""

from __future__ import annotations

import sys
import threading
import time
from collections import defaultdict

from .config import get_settings


class MetricsRecorder:
    def __init__(self, flush_interval: float = 5.0):
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._latencies: list[float] = []
        self.flush_interval = flush_interval
        self._started = False

    def start(self) -> None:
        if not self._started and get_settings().metrics_enabled:
            self._started = True
            threading.Thread(target=self._loop, daemon=True, name="cw-metrics").start()

    def incr(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe_latency(self, ms: float) -> None:
        with self._lock:
            self._latencies.append(ms)

    def _drain(self) -> tuple[dict[str, float], list[float]]:
        with self._lock:
            counters, lat = dict(self._counters), list(self._latencies)
            self._counters.clear()
            self._latencies.clear()
        return counters, lat

    def flush(self) -> None:
        from .aws import client

        s = get_settings()
        counters, lat = self._drain()
        dims = [
            {"Name": "Service", "Value": s.service_name},
            {"Name": "PodTemplateHash", "Value": s.pod_template_hash},
        ]
        data = [{"MetricName": k, "Dimensions": dims, "Value": v, "Unit": "Count"} for k, v in counters.items()]
        if lat:
            data.append(
                {
                    "MetricName": "LatencyMs",
                    "Dimensions": dims,
                    "StatisticValues": {
                        "SampleCount": len(lat),
                        "Sum": sum(lat),
                        "Minimum": min(lat),
                        "Maximum": max(lat),
                    },
                    "Unit": "Milliseconds",
                }
            )
        if not data:
            return
        try:
            cw = client("cloudwatch")
            for i in range(0, len(data), 20):
                cw.put_metric_data(Namespace=s.metrics_namespace, MetricData=data[i : i + 20])
        except Exception as exc:
            print(f"cloudwatch-metrics error: {exc}", file=sys.stderr)

    def _loop(self) -> None:
        while True:
            time.sleep(self.flush_interval)
            self.flush()


metrics = MetricsRecorder()
