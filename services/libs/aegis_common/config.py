"""Configuración por variables de entorno (inyectadas por el ConfigMap de cada ambiente)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: os.getenv("ENV", "local"))
    service_name: str = field(default_factory=lambda: os.getenv("SERVICE_NAME", "unknown"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "dev"))
    pod_template_hash: str = field(default_factory=lambda: os.getenv("POD_TEMPLATE_HASH", "local"))
    pod_name: str = field(default_factory=lambda: os.getenv("POD_NAME", os.getenv("HOSTNAME", "local")))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    aws_endpoint_url: str | None = field(default_factory=lambda: os.getenv("AWS_ENDPOINT_URL") or None)
    log_to_cloudwatch: bool = field(default_factory=lambda: _bool("LOG_TO_CLOUDWATCH", False))
    metrics_enabled: bool = field(default_factory=lambda: _bool("METRICS_ENABLED", False))
    fault_injection_rate: float = field(default_factory=lambda: float(os.getenv("FAULT_INJECTION_RATE", "0")))
    flags_cache_ttl: float = field(default_factory=lambda: float(os.getenv("FLAGS_CACHE_TTL", "5")))

    def table(self, kind: str) -> str:
        """Nombre de tabla DynamoDB del ambiente: aegisvolt-<kind>-<env> (sobrescribible por env var)."""
        return os.getenv(f"TABLE_{kind.upper().replace('-', '_')}", f"aegisvolt-{kind}-{self.env}")

    @property
    def log_group(self) -> str:
        return f"/aegisvolt/{self.env}/{self.service_name}"

    @property
    def metrics_namespace(self) -> str:
        return f"AegisVolt/{self.env}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
