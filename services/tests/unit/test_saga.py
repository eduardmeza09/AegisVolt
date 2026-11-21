"""SAGA de punta a punta en memoria: GraphQL -> orquestador -> 3 servicios -> DynamoDB (moto)."""

from tests.conftest import set_flag
from tests.queries import FLAGS, RESERVE, RETRY, SAGA, SET_FLAG, STATIONS, STOP, WALLET, connector_status


def _input(fleet="fleet-rapido", station="st-bog-01", connector="c1", kwh=40.0, crid=None):
    return {
        "input": {
            "fleetId": fleet,
            "stationId": station,
            "connectorId": connector,
            "estimatedKwh": kwh,
            "clientRequestId": crid,
        }
    }


async def _balance(gql, fleet="fleet-rapido"):
    return (await gql(WALLET, {"id": fleet}))["data"]["wallet"]["balance"]


async def test_happy_path_completes(gql):
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "COMPLETED"
    assert [s["name"] for s in saga["steps"]] == ["RESERVE_CONNECTOR", "HOLD_FUNDS", "START_CHARGING"]
    assert connector_status(await gql(STATIONS), "st-bog-01", "c1") == "CHARGING"
    assert await _balance(gql) == 500 - saga["amount"]
    done = (await gql(STOP, {"id": saga["sagaId"]}))["data"]["stopCharging"]
    assert done["status"] == "FINISHED"
    assert connector_status(await gql(STATIONS), "st-bog-01", "c1") == "AVAILABLE"


async def test_hardware_fault_compensates_billing_then_reservation(gql):
    set_flag("SIMULATE_CHARGER_HARDWARE_FAULT", True)
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "COMPENSATED"
    assert saga["errorCode"] == "HARDWARE_FAULT" and saga["failedStep"] == "START_CHARGING"
    names = [s["name"] for s in saga["steps"]]
    assert names == ["RESERVE_CONNECTOR", "HOLD_FUNDS", "START_CHARGING", "COMPENSATE_REFUND", "COMPENSATE_RELEASE"]
    assert names.index("COMPENSATE_REFUND") < names.index("COMPENSATE_RELEASE")  # orden inverso
    assert await _balance(gql) == 500.0
    assert connector_status(await gql(STATIONS), "st-bog-01", "c1") == "AVAILABLE"


async def test_insufficient_funds_releases_connector_immediately(gql):
    saga = (await gql(RESERVE, _input(fleet="fleet-pobre")))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "COMPENSATED" and saga["errorCode"] == "INSUFFICIENT_FUNDS"
    assert [s["name"] for s in saga["steps"]] == ["RESERVE_CONNECTOR", "HOLD_FUNDS", "COMPENSATE_RELEASE"]
    assert connector_status(await gql(STATIONS), "st-bog-01", "c1") == "AVAILABLE"
    assert await _balance(gql, "fleet-pobre") == 1.0


async def test_compensation_replay_is_idempotent(gql):
    set_flag("SIMULATE_CHARGER_HARDWARE_FAULT", True)
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    replay = (await gql(RETRY, {"id": saga["sagaId"]}))["data"]["retryCompensation"]
    assert replay["status"] == "COMPENSATED"
    replayed = [s for s in replay["steps"] if s["name"].endswith("_REPLAY")]
    assert len(replayed) == 2 and all(s["idempotentReplay"] for s in replayed)
    assert await _balance(gql) == 500.0  # el reembolso no se aplicó dos veces


async def test_duplicate_mutation_returns_same_saga(gql):
    first = (await gql(RESERVE, _input(crid="req-123")))["data"]["reserveAndStartCharging"]
    second = (await gql(RESERVE, _input(crid="req-123")))["data"]["reserveAndStartCharging"]
    assert first["sagaId"] == second["sagaId"]
    assert await _balance(gql) == 500 - first["amount"]  # cobrado una sola vez


async def test_connector_taken_fails_without_side_effects(gql):
    await gql(RESERVE, _input())
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "FAILED" and saga["errorCode"] == "CONNECTOR_UNAVAILABLE"


async def test_ultra_requires_fast_charge_flag(gql):
    set_flag("ENABLE_FAST_CHARGE_BOOST", False)
    saga = (await gql(RESERVE, _input(connector="c2")))["data"]["reserveAndStartCharging"]
    assert saga["status"] == "FAILED" and saga["errorCode"] == "FAST_CHARGE_DISABLED"
    set_flag("ENABLE_FAST_CHARGE_BOOST", True)
    ok = (await gql(RESERVE, _input(connector="c2")))["data"]["reserveAndStartCharging"]
    assert ok["status"] == "COMPLETED"


async def test_feature_flags_admin_mutation(gql):
    denied = await gql(SET_FLAG, {"n": "SIMULATE_CHARGER_HARDWARE_FAULT", "e": True})
    assert denied["errors"]
    ok = await gql(SET_FLAG, {"n": "SIMULATE_CHARGER_HARDWARE_FAULT", "e": True}, {"x-admin-token": "test-admin"})
    assert ok["data"]["setFeatureFlag"]["enabled"] is True
    flags = {f["name"]: f["enabled"] for f in (await gql(FLAGS))["data"]["featureFlags"]}
    assert flags["SIMULATE_CHARGER_HARDWARE_FAULT"] is True


async def test_saga_log_is_persisted(gql):
    saga = (await gql(RESERVE, _input()))["data"]["reserveAndStartCharging"]
    stored = (await gql(SAGA, {"id": saga["sagaId"]}))["data"]["saga"]
    assert stored["status"] == "COMPLETED" and len(stored["steps"]) == 3
