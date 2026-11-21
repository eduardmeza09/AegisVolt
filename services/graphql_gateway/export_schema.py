"""Exporta / verifica el SDL del esquema GraphQL (contrato con el frontend).

    python -m graphql_gateway.export_schema          # escribe graphql_gateway/schema.graphql
    python -m graphql_gateway.export_schema --check  # CI: falla si el SDL versionado está desactualizado
"""

import pathlib
import sys

from graphql_gateway.schema import schema

PATH = pathlib.Path(__file__).with_name("schema.graphql")

if __name__ == "__main__":
    sdl = schema.as_str() + "\n"
    if "--check" in sys.argv:
        current = PATH.read_text(encoding="utf-8") if PATH.exists() else ""
        if current.replace("\r\n", "\n") != sdl:
            sys.exit("schema.graphql desactualizado: ejecuta `python -m graphql_gateway.export_schema`")
        print("schema.graphql al día")
    else:
        PATH.write_text(sdl, encoding="utf-8", newline="\n")
        print(f"escrito {PATH}")
