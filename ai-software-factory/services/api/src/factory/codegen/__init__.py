"""Motor de generación de código: convierte una especificación en un proyecto real."""

from factory.codegen.blueprint import Blueprint
from factory.codegen.bundler import bundle_artifacts
from factory.codegen.renderers import (
    render_backend,
    render_ci,
    render_database,
    render_deployment,
    render_docs,
    render_frontend,
    render_tests,
)

__all__ = [
    "Blueprint",
    "bundle_artifacts",
    "render_backend",
    "render_ci",
    "render_database",
    "render_deployment",
    "render_docs",
    "render_frontend",
    "render_tests",
]
