"""Idempotencia de los pasos y compensaciones a nivel de repositorio (DynamoDB en moto)."""

from decimal import Decimal

import pytest
from aegis_common.web import BusinessError

from billing_wallet_service import repository as billing
from station_reservation_service import repository as station


def test_reserve_is_idempotent_for_same_saga_and_exclusive_for_others(aws_env):
    station.reserve("st-bog-01", "c1", "saga-A", "fleet-rapido")
    again = station.reserve("st-bog-01", "c1", "saga-A", "fleet-rapido")  # reintento
    assert again["status"] == "RESERVED" and again["saga_id"] == "saga-A"
    with pytest.raises(BusinessError) as e:
        station.reserve("st-bog-01", "c1", "saga-B", "fleet-rapido")  # otra saga: doble reserva bloqueada
    assert e.value.code == "CONNECTOR_UNAVAILABLE"


def test_release_twice_and_never_releases_foreign_reservation(aws_env):
    station.reserve("st-bog-01", "c1", "saga-A", "fleet-rapido")
    assert station.release("st-bog-01", "c1", "saga-X")["released"] is False  # no es dueño
    assert station.get_connector("st-bog-01", "c1")["status"] == "RESERVED"
    assert station.release("st-bog-01", "c1", "saga-A")["released"] is True
    second = station.release("st-bog-01", "c1", "saga-A")
    assert second == {**second, "released": False, "idempotent_replay": True}
    assert station.get_connector("st-bog-01", "c1")["status"] == "AVAILABLE"


def test_hold_twice_charges_once(aws_env):
    billing.hold("fleet-rapido", "saga-A", Decimal("20.00"), {})
    replay = billing.hold("fleet-rapido", "saga-A", Decimal("20.00"), {})
    assert replay["idempotent_replay"] is True
    assert billing.get_wallet("fleet-rapido")["balance"] == Decimal("480.00")


def test_refund_twice_refunds_once(aws_env):
    billing.hold("fleet-rapido", "saga-A", Decimal("20.00"), {})
    assert billing.refund("fleet-rapido", "saga-A", "TEST")["refunded"] is True
    second = billing.refund("fleet-rapido", "saga-A", "TEST")
    assert second["refunded"] is False and second["idempotent_replay"] is True
    assert billing.get_wallet("fleet-rapido")["balance"] == Decimal("500.00")
    types = sorted(t["type"] for t in billing.list_transactions("fleet-rapido"))
    assert types == ["HOLD", "REFUND"]  # un solo asiento de cada tipo


def test_refund_without_hold_is_noop(aws_env):
    r = billing.refund("fleet-rapido", "saga-sin-hold", "TEST")
    assert r["refunded"] is False and r["reason"] == "NO_HOLD"


def test_insufficient_funds(aws_env):
    with pytest.raises(BusinessError) as e:
        billing.hold("fleet-pobre", "saga-A", Decimal("20.00"), {})
    assert e.value.code == "INSUFFICIENT_FUNDS" and e.value.status_code == 402
    assert billing.get_wallet("fleet-pobre")["balance"] == Decimal("1.00")
