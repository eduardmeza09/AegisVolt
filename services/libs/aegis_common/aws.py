"""Clientes boto3 apuntando a Floci (AWS_ENDPOINT_URL) o a AWS real si no se define."""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from .config import get_settings

_CFG = Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=3, read_timeout=10)


@lru_cache
def client(service: str):
    s = get_settings()
    return boto3.client(service, region_name=s.aws_region, endpoint_url=s.aws_endpoint_url, config=_CFG)


@lru_cache
def dynamodb_table(name: str):
    s = get_settings()
    res = boto3.resource("dynamodb", region_name=s.aws_region, endpoint_url=s.aws_endpoint_url, config=_CFG)
    return res.Table(name)


def reset_clients() -> None:
    """Usado por los tests para recrear clientes tras cambiar variables de entorno."""
    client.cache_clear()
    dynamodb_table.cache_clear()
