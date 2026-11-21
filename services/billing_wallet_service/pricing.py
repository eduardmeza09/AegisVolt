"""Cálculo de tarifa estimada. ENABLE_DYNAMIC_SURGE_PRICING aplica x1.5 dentro de PEAK_HOURS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

BASE_PRICE_PER_KWH = {"CCS2": Decimal("0.35"), "CHADEMO": Decimal("0.35"), "ULTRA": Decimal("0.55")}
SURGE_MULTIPLIER = Decimal("1.5")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Quote:
    connector_type: str
    kwh: Decimal
    price_per_kwh: Decimal
    surge_applied: bool
    surge_multiplier: Decimal
    total: Decimal

    def as_dict(self) -> dict:
        return {
            "connector_type": self.connector_type,
            "kwh": float(self.kwh),
            "price_per_kwh": float(self.price_per_kwh),
            "surge_applied": self.surge_applied,
            "surge_multiplier": float(self.surge_multiplier),
            "total": float(self.total),
        }


def parse_peak_hours(raw: str) -> tuple[int, int]:
    start, end = (int(x) for x in raw.split("-"))
    if not (0 <= start <= 24 and 0 <= end <= 24 and start < end):
        raise ValueError(f"PEAK_HOURS inválido: {raw}")
    return start, end


def is_peak(now: datetime | None = None) -> bool:
    start, end = parse_peak_hours(os.getenv("PEAK_HOURS", "17-21"))
    offset = int(os.getenv("PEAK_TZ_OFFSET_HOURS", "-5"))  # hora local Bogotá/Lima
    local = (now or datetime.now(UTC)) + timedelta(hours=offset)
    return start <= local.hour < end


def quote(connector_type: str, kwh: float, surge_enabled: bool, now: datetime | None = None) -> Quote:
    ctype = connector_type.upper()
    base = BASE_PRICE_PER_KWH.get(ctype, BASE_PRICE_PER_KWH["CCS2"])
    kwh_d = Decimal(str(kwh)).quantize(Decimal("0.001"))
    surge = surge_enabled and is_peak(now)
    multiplier = SURGE_MULTIPLIER if surge else Decimal("1")
    price = (base * multiplier).quantize(Decimal("0.0001"))
    total = (price * kwh_d).quantize(CENT, rounding=ROUND_HALF_UP)
    return Quote(ctype, kwh_d, price, surge, multiplier, total)
