"""Operaciones GraphQL compartidas por tests unit / integration / e2e."""

RESERVE = """
mutation Reserve($input: ReserveAndStartChargingInput!) {
  reserveAndStartCharging(input: $input) {
    sagaId correlationId status amount surgeApplied errorCode failedStep
    steps { name service status detail idempotentReplay }
  }
}
"""

WALLET = """query W($id: String!) { wallet(fleetId: $id) { balance transactions { type amount ref } } }"""

STATIONS = (
    """query { stations { stationId availableConnectors connectors { connectorId status sagaId connectorType } } }"""
)

SAGA = """query S($id: String!) { saga(sagaId: $id) { status steps { name status idempotentReplay } } }"""

RETRY = """mutation R($id: String!) { retryCompensation(sagaId: $id) { status steps { name status detail idempotentReplay } } }"""  # noqa: E501

STOP = """mutation S($id: String!) { stopCharging(sagaId: $id) { status } }"""

FLAGS = """query { environment { name } featureFlags { name enabled } }"""

SET_FLAG = """mutation F($n: String!, $e: Boolean!) { setFeatureFlag(name: $n, enabled: $e) { name enabled } }"""


def connector_status(stations_data: dict, station_id: str, connector_id: str) -> str:
    for s in stations_data["data"]["stations"]:
        if s["stationId"] == station_id:
            for c in s["connectors"]:
                if c["connectorId"] == connector_id:
                    return c["status"]
    raise KeyError(f"{station_id}/{connector_id}")
