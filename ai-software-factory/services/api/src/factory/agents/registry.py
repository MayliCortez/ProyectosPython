"""Registro de agentes disponibles."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from factory.agents.base import Agent
from factory.agents.specialists import (
    ApiDesigner,
    BackendGenerator,
    CodeReviewer,
    DatabaseDesigner,
    DeploymentAgent,
    DocumentationGenerator,
    FrontendGenerator,
    MaintenanceAgent,
    RequirementsAnalyst,
    SoftwareArchitect,
    TestGenerator,
)
from factory.domain.errors import NotFoundError, ValidationError


class AgentRegistry:
    """Índice de agentes por clave.

    Sustituir un agente por otra implementación (por ejemplo, un generador de backend
    para otro lenguaje) es registrar otra instancia bajo la misma clave: el pipeline y
    el orquestador no cambian.
    """

    def __init__(self, agents: Iterable[Agent]) -> None:
        self._agents: dict[str, Agent] = {}
        for agent in agents:
            self.register(agent)

    def register(self, agent: Agent, *, replace: bool = False) -> None:
        if agent.key in self._agents and not replace:
            raise ValidationError(f"Ya hay un agente registrado con la clave {agent.key!r}")
        self._agents[agent.key] = agent

    def get(self, key: str) -> Agent:
        agent = self._agents.get(key)
        if agent is None:
            raise NotFoundError(f"No hay ningún agente con la clave {key!r}")
        return agent

    def has(self, key: str) -> bool:
        return key in self._agents

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def keys(self) -> set[str]:
        return set(self._agents)


@lru_cache(maxsize=1)
def default_registry() -> AgentRegistry:
    """Los once agentes estándar de la fábrica, en orden conceptual."""
    return AgentRegistry(
        [
            RequirementsAnalyst(),
            SoftwareArchitect(),
            DatabaseDesigner(),
            ApiDesigner(),
            BackendGenerator(),
            FrontendGenerator(),
            TestGenerator(),
            CodeReviewer(),
            DocumentationGenerator(),
            DeploymentAgent(),
            MaintenanceAgent(),
        ]
    )
