"""Carga datos iniciales (estaciones, conectores y billeteras) en un ambiente. Idempotente.

Uso:
  python scripts/seed.py --env dev                     # tablas ya creadas por Terraform
  python scripts/seed.py --env local --create-tables   # stack docker-compose (sin Terraform)
  python scripts/seed.py --env dev --reset             # vuelve conectores a AVAILABLE y saldos iniciales
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "libs"))

STATIONS = [
    ("st-bog-01", "Electrolinera Calle 80", "Bogotá", 4.6936, -74.0868, [("c1", "CCS2", 50), ("c2", "CCS2", 150),
                                                                         ("c3", "ULTRA", 350)]),
    ("st-bog-02", "Hub Logístico Fontibón", "Bogotá", 4.6782, -74.1407, [("c1", "CCS2", 50), ("c2", "CHADEMO", 50)]),
    ("st-med-01", "Hub El Poblado", "Medellín", 6.2087, -75.5673, [("c1", "CCS2", 150), ("c2", "ULTRA", 350)]),
    ("st-cdmx-01", "Centro de Carga Vallejo", "CDMX", 19.4978, -99.1490, [("c1", "CCS2", 150), ("c2", "CCS2", 150)]),
    ("st-lim-01", "Electrolinera Callao", "Lima", -12.0464, -77.1255, [("c1", "CCS2", 50), ("c2", "ULTRA", 350)]),
]
FLEETS = [
    ("fleet-rapido", "Rápido Express Logística", "1500.00"),
    ("fleet-andina", "Andina Last-Mile", "800.00"),
    ("fleet-sinfondos", "Flota Sin Fondos (demo)", "2.00"),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env", required=True)
    p.add_argument("--endpoint", default=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"))
    p.add_argument("--create-tables", action="store_true")
    p.add_argument("--reset", action="store_true")
    a = p.parse_args()
    kw = {"region_name": os.getenv("AWS_REGION", "us-east-1"), "endpoint_url": a.endpoint}
    if a.create_tables:
        from aegis_common.flags import KNOWN_FLAGS
        from aegis_common.tables import create_all_tables

        create_all_tables(boto3.client("dynamodb", **kw), a.env)
        flags = boto3.resource("dynamodb", **kw).Table(f"aegisvolt-feature-flags-{a.env}")
        for name, desc in KNOWN_FLAGS.items():
            try:
                flags.put_item(Item={"flag_name": name, "enabled": name == "ENABLE_FAST_CHARGE_BOOST",
                                     "description": desc, "updated_by": "seed"},
                               ConditionExpression="attribute_not_exists(flag_name)")
            except ClientError:
                pass

    ddb = boto3.resource("dynamodb", **kw)
    res, bil = ddb.Table(f"aegisvolt-reservations-{a.env}"), ddb.Table(f"aegisvolt-billing-{a.env}")
    cond = {} if a.reset else {"ConditionExpression": "attribute_not_exists(station_id)"}
    n = 0
    for sid, name, city, lat, lng, connectors in STATIONS:
        for cid, ctype, kw_ in connectors:
            try:
                res.put_item(Item={"station_id": sid, "connector_id": cid, "station_name": name, "city": city,
                                   "lat": Decimal(str(lat)), "lng": Decimal(str(lng)), "connector_type": ctype,
                                   "power_kw": kw_, "status": "AVAILABLE", "version": 0}, **cond)
                n += 1
            except ClientError:
                pass
    wcond = {} if a.reset else {"ConditionExpression": "attribute_not_exists(fleet_id)"}
    for fid, fname, bal in FLEETS:
        try:
            bil.put_item(Item={"fleet_id": fid, "sk": "WALLET", "fleet_name": fname, "balance": Decimal(bal),
                               "currency": "USD"}, **wcond)
        except ClientError:
            pass
    print(f"seed {a.env}: {n} conectores nuevos/reseteados; {len(FLEETS)} billeteras verificadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
