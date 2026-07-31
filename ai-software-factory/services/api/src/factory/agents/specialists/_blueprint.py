"""Construcción del blueprint compartido por los agentes generadores."""

from __future__ import annotations

from factory.agents.base import AgentContext
from factory.codegen.blueprint import Blueprint
from factory.domain.entities.specification import Specification


def blueprint_from(context: AgentContext) -> Blueprint:
    """Reúne proyecto, especificación y manifiestos en la entrada de los renderizadores."""
    specification: Specification = context.get("specification")
    modules = tuple(
        manifest
        for manifest in (context.catalog.try_get(key) for key in specification.modules)
        if manifest is not None
    )
    return Blueprint(
        project=context.project,
        specification=specification,
        modules=modules,
    )
