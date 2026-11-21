"""Cliente de Feature Flags propio sobre DynamoDB (tabla aegisvolt-feature-flags-<env>).

Cada ambiente tiene su propia tabla, por lo que el estado es independiente. Los servicios
releen cada FLAGS_CACHE_TTL segundos (5 s por defecto): cambiar un flag NO requiere redespliegue.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

from .aws import dynamodb_table
from .config import get_settings

log = logging.getLogger("aegisvolt.flags")

KNOWN_FLAGS = {
    "ENABLE_DYNAMIC_SURGE_PRICING": "Activa tarifas dinámicas (x1.5) en horas pico",
    "ENABLE_FAST_CHARGE_BOOST": "Habilita la reserva prioritaria de conectores de ultra-carga (ULTRA 350 kW)",
    "SIMULATE_CHARGER_HARDWARE_FAULT": "Inyección de fallos: el cargador reporta error físico (dispara rollback SAGA)",
}


class FeatureFlags:
    def __init__(self, table_name: str | None = None, ttl: float | None = None):
        s = get_settings()
        self.table_name = table_name or s.table("feature-flags")
        self.ttl = s.flags_cache_ttl if ttl is None else ttl
        self._cache: dict[str, dict] = {}
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        items = dynamodb_table(self.table_name).scan().get("Items", [])
        self._cache = {i["flag_name"]: i for i in items}
        self._loaded_at = time.monotonic()

    def all(self, force: bool = False) -> dict[str, dict]:
        with self._lock:
            if force or time.monotonic() - self._loaded_at > self.ttl:
                try:
                    self._refresh()
                except Exception:
                    log.exception("no se pudieron leer los feature flags; se usa la última copia")
            return dict(self._cache)

    def is_enabled(self, name: str) -> bool:
        item = self.all().get(name)
        return bool(item and item.get("enabled"))

    def set(self, name: str, enabled: bool, updated_by: str = "api") -> dict:
        item = {
            "flag_name": name,
            "enabled": enabled,
            "description": KNOWN_FLAGS.get(name, ""),
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": updated_by,
        }
        dynamodb_table(self.table_name).put_item(Item=item)
        with self._lock:
            self._loaded_at = 0.0
        return item


_flags: FeatureFlags | None = None


def get_flags() -> FeatureFlags:
    global _flags
    if _flags is None:
        _flags = FeatureFlags()
    return _flags


def reset_flags() -> None:
    global _flags
    _flags = None
