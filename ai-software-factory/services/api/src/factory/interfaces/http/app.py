"""Construcción de la aplicación FastAPI."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from factory import __version__
from factory.config import Settings, get_settings
from factory.container import Container, build_container
from factory.interfaces.http.errors import register_error_handlers
from factory.interfaces.http.routers import (
    auth,
    builds,
    conversations,
    deployments,
    health,
    modules,
    projects,
)
from factory.interfaces.ws import progress

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def create_app(*, settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Crea la aplicación.

    `container` permite inyectar dependencias ya construidas —lo que hacen las pruebas
    de integración— sin tocar el arranque normal, que las construye en el `lifespan`.
    """
    resolved = settings or get_settings()
    logging.basicConfig(
        level=resolved.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        own_container = container is None
        application.state.container = container or await build_container(resolved)
        logger.info(
            "AI Software Factory %s lista (entorno=%s, IA=%s)",
            __version__,
            resolved.env,
            resolved.llm_provider,
        )
        try:
            yield
        finally:
            if own_container:
                await application.state.container.close()

    application = FastAPI(
        title="AI Software Factory",
        description=(
            "Plataforma que convierte una conversación en lenguaje natural en una "
            "aplicación completa: requisitos, especificación, código, pruebas y despliegue."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(application)

    application.include_router(health.router)
    application.include_router(auth.router, prefix=API_PREFIX)
    application.include_router(projects.router, prefix=API_PREFIX)
    application.include_router(conversations.router, prefix=API_PREFIX)
    application.include_router(modules.catalog_router, prefix=API_PREFIX)
    application.include_router(modules.project_router, prefix=API_PREFIX)
    application.include_router(builds.router, prefix=API_PREFIX)
    application.include_router(deployments.router, prefix=API_PREFIX)
    application.include_router(progress.router)

    return application
