"""Renderizadores: funciones puras `Blueprint -> list[Artifact]`."""

from factory.codegen.renderers.backend import render_backend
from factory.codegen.renderers.ci import render_ci
from factory.codegen.renderers.database import render_database
from factory.codegen.renderers.deployment import render_deployment
from factory.codegen.renderers.docs import render_docs
from factory.codegen.renderers.frontend import render_frontend
from factory.codegen.renderers.tests import render_tests

__all__ = [
    "render_backend",
    "render_ci",
    "render_database",
    "render_deployment",
    "render_docs",
    "render_frontend",
    "render_tests",
]
