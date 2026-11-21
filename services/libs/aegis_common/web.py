"""Fábrica FastAPI común: correlation_id, métricas, inyección de fallos (Canary) y health checks."""

from __future__ import annotations

import logging
import random
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .logging import correlation_id_var, saga_id_var, setup_logging, step_var
from .metrics import metrics

HEALTH_PATHS = {"/healthz", "/readyz"}


class BusinessError(Exception):
    """Error de negocio con código estable que el orquestador SAGA sabe interpretar."""

    def __init__(self, code: str, message: str, status_code: int = 409):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def create_app(service_name: str, readiness=None) -> FastAPI:
    import os

    os.environ.setdefault("SERVICE_NAME", service_name)
    setup_logging()
    log = logging.getLogger(f"aegisvolt.{service_name}")
    s = get_settings()
    app = FastAPI(title=service_name, version=s.app_version)

    @app.middleware("http")
    async def observability(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        correlation_id_var.set(cid)
        saga_id_var.set(request.headers.get("x-saga-id"))
        step_var.set(request.headers.get("x-saga-step"))
        start = time.perf_counter()
        is_health = request.url.path in HEALTH_PATHS
        if not is_health and s.fault_injection_rate > 0 and random.random() < s.fault_injection_rate:
            response = JSONResponse({"error": "INJECTED_FAULT", "message": "fallo inyectado"}, status_code=500)
            log.warning("fallo inyectado por FAULT_INJECTION_RATE", extra={"path": request.url.path})
        else:
            try:
                response = await call_next(request)
            except Exception:
                log.exception("error no controlado", extra={"path": request.url.path})
                response = JSONResponse({"error": "INTERNAL", "message": "error interno"}, status_code=500)
        elapsed = (time.perf_counter() - start) * 1000
        if not is_health:
            metrics.incr("RequestCount")
            if response.status_code >= 500:
                metrics.incr("ErrorCount")
            metrics.observe_latency(elapsed)
        response.headers["x-correlation-id"] = cid
        response.headers["x-app-version"] = s.app_version
        response.headers["x-pod-template-hash"] = s.pod_template_hash
        return response

    @app.exception_handler(BusinessError)
    async def business_error(_: Request, exc: BusinessError):
        log.warning(exc.message, extra={"error_code": exc.code})
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status_code)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": service_name}

    @app.get("/readyz")
    def readyz():
        if readiness is not None:
            try:
                readiness()
            except Exception as exc:  # dependencia caída => no listo
                return JSONResponse({"status": "not-ready", "reason": str(exc)}, status_code=503)
        return {"status": "ready", "service": service_name}

    @app.get("/v1/info")
    def info():
        return {
            "service": service_name,
            "env": s.env,
            "version": s.app_version,
            "pod_template_hash": s.pod_template_hash,
            "pod": s.pod_name,
        }

    @app.on_event("startup")
    def _start_metrics():
        metrics.start()
        log.info("servicio iniciado", extra={"fault_injection_rate": s.fault_injection_rate})

    return app
