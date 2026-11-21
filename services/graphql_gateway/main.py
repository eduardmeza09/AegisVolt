"""graphql-gateway: capa de agregación GraphQL + orquestador SAGA."""

from __future__ import annotations

import os

from aegis_common.aws import dynamodb_table
from aegis_common.config import get_settings
from aegis_common.web import create_app
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from .clients import Services
from .saga import SagaOrchestrator
from .schema import schema

SERVICE = "graphql-gateway"


def build_app(services: Services | None = None):
    app = create_app(SERVICE, readiness=lambda: dynamodb_table(get_settings().table("sagas")).table_status)
    svc = services or Services.from_env()
    orchestrator = SagaOrchestrator(svc)

    async def context_getter(request: Request, response: Response):
        return {"request": request, "response": response, "services": svc, "orchestrator": orchestrator}

    app.include_router(GraphQLRouter(schema, context_getter=context_getter), prefix="/graphql")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-correlation-id", "x-app-version", "x-pod-template-hash"],
    )
    return app


app = build_app() if os.getenv("AEGIS_SKIP_APP") != "1" else None
