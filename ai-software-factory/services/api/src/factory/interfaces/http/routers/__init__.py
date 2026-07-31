"""Routers REST de la plataforma."""

from factory.interfaces.http.routers import (
    auth,
    builds,
    conversations,
    deployments,
    health,
    modules,
    projects,
)

__all__ = [
    "auth",
    "builds",
    "conversations",
    "deployments",
    "health",
    "modules",
    "projects",
]
