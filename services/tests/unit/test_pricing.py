from datetime import UTC, datetime
from decimal import Decimal

from billing_wallet_service import pricing

PEAK = datetime(2026, 11, 20, 23, 0, tzinfo=UTC)  # 18:00 en Bogotá (UTC-5)
OFF_PEAK = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)  # 10:00 en Bogotá


def test_base_price_without_surge(monkeypatch):
    monkeypatch.setenv("PEAK_HOURS", "17-21")
    q = pricing.quote("CCS2", 40, surge_enabled=False, now=PEAK)
    assert q.total == Decimal("14.00") and not q.surge_applied


def test_surge_only_in_peak_hours(monkeypatch):
    monkeypatch.setenv("PEAK_HOURS", "17-21")
    assert pricing.quote("CCS2", 40, True, now=PEAK).total == Decimal("21.00")
    assert pricing.quote("CCS2", 40, True, now=OFF_PEAK).total == Decimal("14.00")


def test_ultra_connector_price(monkeypatch):
    monkeypatch.setenv("PEAK_HOURS", "17-21")
    assert pricing.quote("ULTRA", 10, False, now=PEAK).total == Decimal("5.50")


def test_peak_hours_validation():
    import pytest

    with pytest.raises(ValueError):
        pricing.parse_peak_hours("21-17")
