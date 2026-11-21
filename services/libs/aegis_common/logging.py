"""Logging estructurado JSON con correlation_id de la SAGA, enviado a stdout y a CloudWatch Logs.

Cada línea incluye: timestamp, level, service, env, version, pod_template_hash, correlation_id,
saga_id, step y message. El log group es /aegisvolt/<env>/<service>.
"""

from __future__ import annotations

import contextvars
import json
import logging
import queue
import sys
import threading
import time
from datetime import UTC, datetime

from .config import get_settings

correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)
saga_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("saga_id", default=None)
step_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("step", default=None)

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        s = get_settings()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": s.service_name,
            "env": s.env,
            "version": s.app_version,
            "pod_template_hash": s.pod_template_hash,
            "correlation_id": correlation_id_var.get(),
            "saga_id": saga_id_var.get(),
            "step": step_var.get(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class CloudWatchHandler(logging.Handler):
    """Handler asíncrono: encola eventos y los envía en lotes con PutLogEvents."""

    def __init__(self, log_group: str, stream: str, flush_interval: float = 2.0):
        super().__init__()
        self.log_group, self.stream, self.flush_interval = log_group, stream, flush_interval
        self._q: queue.Queue[dict] = queue.Queue(maxsize=10_000)
        self._ready = False
        threading.Thread(target=self._worker, daemon=True, name="cw-logs").start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put_nowait({"timestamp": int(record.created * 1000), "message": self.format(record)})
        except queue.Full:
            pass

    def _ensure(self, logs) -> None:
        if self._ready:
            return
        for call, kwargs in (
            (logs.create_log_group, {"logGroupName": self.log_group}),
            (logs.create_log_stream, {"logGroupName": self.log_group, "logStreamName": self.stream}),
        ):
            try:
                call(**kwargs)
            except logs.exceptions.ResourceAlreadyExistsException:
                pass
        self._ready = True

    def _worker(self) -> None:
        from .aws import client

        while True:
            time.sleep(self.flush_interval)
            batch: list[dict] = []
            while not self._q.empty() and len(batch) < 500:
                batch.append(self._q.get_nowait())
            if not batch:
                continue
            try:
                logs = client("logs")
                self._ensure(logs)
                logs.put_log_events(logGroupName=self.log_group, logStreamName=self.stream, logEvents=batch)
            except Exception as exc:  # nunca romper el servicio por fallos de logging
                print(f"cloudwatch-logs error: {exc}", file=sys.stderr)


def setup_logging() -> logging.Logger:
    s = get_settings()
    root = logging.getLogger()
    if getattr(root, "_aegis_configured", False):
        return logging.getLogger("aegisvolt")
    root.handlers.clear()
    root.setLevel(logging.INFO)
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(JsonFormatter())
    root.addHandler(stdout)
    if s.log_to_cloudwatch:
        cw = CloudWatchHandler(s.log_group, f"{s.pod_name}-{s.pod_template_hash}")
        cw.setFormatter(JsonFormatter())
        root.addHandler(cw)
    for noisy in ("botocore", "boto3", "urllib3", "httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._aegis_configured = True  # type: ignore[attr-defined]
    return logging.getLogger("aegisvolt")
