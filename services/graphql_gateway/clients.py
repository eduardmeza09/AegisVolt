"""Clientes HTTP hacia los microservicios. Propagan correlation_id, saga_id, paso e Idempotency-Key."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from aegis_common.logging import correlation_id_var


@dataclass
class StepError(Exception):
    """Fallo de un paso de la SAGA. retriable=True para errores transitorios (red / 5xx no de negocio)."""

    code: str
    message: str
    status_code: int = 0
    retriable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


BUSINESS_5XX = {"HARDWARE_FAULT"}


class ServiceClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=8.0, transport=transport)

    async def call(
        self,
        method: str,
        path: str,
        *,
        saga_id: str | None = None,
        step: str | None = None,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        headers = {"x-correlation-id": correlation_id_var.get() or saga_id or ""}
        if saga_id:
            headers |= {"x-saga-id": saga_id, "idempotency-key": f"{saga_id}:{step}"}
        if step:
            headers["x-saga-step"] = step
        try:
            r = await self._client.request(method, path, json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise StepError("SERVICE_UNREACHABLE", f"{self.base_url}{path}: {exc}", 0, True) from exc
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {"error": "HTTP_ERROR", "message": r.text[:200]}
            code = body.get("error", "HTTP_ERROR")
            retriable = r.status_code >= 500 and code not in BUSINESS_5XX
            raise StepError(code, body.get("message", ""), r.status_code, retriable)
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()


class Services:
    """Agrupa los 3 clientes. Los tests inyectan transportes ASGI en memoria."""

    def __init__(self, station: ServiceClient, billing: ServiceClient, dispatch: ServiceClient):
        self.station, self.billing, self.dispatch = station, billing, dispatch

    @classmethod
    def from_env(cls) -> Services:
        return cls(
            ServiceClient(os.getenv("STATION_URL", "http://station-reservation:8080")),
            ServiceClient(os.getenv("BILLING_URL", "http://billing-wallet:8080")),
            ServiceClient(os.getenv("DISPATCH_URL", "http://energy-dispatch:8080")),
        )
