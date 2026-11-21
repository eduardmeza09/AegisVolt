"""Esquemas de las tablas DynamoDB (espejo de infra/modules/dynamodb) usados por tests y seed local."""

from __future__ import annotations

TABLE_SCHEMAS: dict[str, dict] = {
    "reservations": {
        "KeySchema": [
            {"AttributeName": "station_id", "KeyType": "HASH"},
            {"AttributeName": "connector_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "station_id", "AttributeType": "S"},
            {"AttributeName": "connector_id", "AttributeType": "S"},
        ],
    },
    "billing": {
        "KeySchema": [
            {"AttributeName": "fleet_id", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "fleet_id", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
    },
    "dispatch": {
        "KeySchema": [
            {"AttributeName": "session_id", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "session_id", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
    },
    "sagas": {
        "KeySchema": [{"AttributeName": "saga_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "saga_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "updated_at", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "by_status",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "updated_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    "feature-flags": {
        "KeySchema": [{"AttributeName": "flag_name", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "flag_name", "AttributeType": "S"}],
    },
}


def create_all_tables(dynamodb_client, env: str) -> list[str]:
    """Crea las 5 tablas del ambiente si no existen. Devuelve los nombres."""
    names = []
    existing = set(dynamodb_client.list_tables().get("TableNames", []))
    for kind, schema in TABLE_SCHEMAS.items():
        name = f"aegisvolt-{kind}-{env}"
        names.append(name)
        if name in existing:
            continue
        dynamodb_client.create_table(TableName=name, BillingMode="PAY_PER_REQUEST", **schema)
    return names
