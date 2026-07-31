"""Contrato común de los agentes.

Cada agente es una unidad independiente: declara qué necesita del contexto compartido
(`requires`) y qué deja en él (`produces`). El orquestador usa esas declaraciones para
validar el pipeline antes de ejecutarlo y para paralelizar las etapas sin dependencias
entre sí; ningún agente conoce a otro.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from factory.application.ports.llm import LLMClient
from factory.catalog.catalog import ModuleCatalog
from factory.domain.entities import Conversation, Project
from factory.domain.errors import AgentExecutionError
from factory.domain.value_objects import Artifact

#: Función que un agente usa para emitir una línea de progreso hacia el WebSocket.
ProgressSink = Callable[[str], Awaitable[None]]


async def _noop(_: str) -> None:
    """Sumidero de progreso por defecto (usado en pruebas y ejecuciones sin UI)."""


@dataclass(slots=True)
class AgentContext:
    """Pizarra compartida entre agentes durante una construcción."""

    project: Project
    conversation: Conversation
    llm: LLMClient
    catalog: ModuleCatalog
    blackboard: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    progress: ProgressSink = _noop

    def get(self, key: str) -> Any:
        """Lee un producto de la pizarra; falla si el pipeline está mal ordenado."""
        if key not in self.blackboard:
            raise AgentExecutionError("orchestrator", f"Falta el producto {key!r} en el contexto")
        return self.blackboard[key]

    def put(self, key: str, value: Any) -> None:
        self.blackboard[key] = value

    def add_artifact(self, artifact: Artifact) -> None:
        self.artifacts[artifact.path] = artifact

    async def log(self, line: str) -> None:
        await self.progress(line)

    @property
    def module_keys(self) -> list[str]:
        return list(self.project.module_keys)


@dataclass(slots=True)
class AgentResult:
    """Salida de un agente: productos para la pizarra, ficheros y trazas."""

    produced: dict[str, Any] = field(default_factory=dict)
    artifacts: list[Artifact] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    def merge_into(self, context: AgentContext) -> None:
        """Vuelca el resultado en el contexto compartido."""
        for key, value in self.produced.items():
            context.put(key, value)
        for artifact in self.artifacts:
            context.add_artifact(artifact)


class Agent(ABC):
    """Agente especializado del pipeline."""

    #: Identificador estable, usado en el pipeline y en los eventos de progreso.
    key: str = ""
    #: Nombre legible mostrado en el panel.
    name: str = ""
    #: Productos que el agente necesita encontrar en la pizarra.
    requires: tuple[str, ...] = ()
    #: Productos que el agente deja en la pizarra.
    produces: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Impide registrar un agente concreto sin identificador."""
        super().__init_subclass__(**kwargs)
        # `__abstractmethods__` aún no existe aquí: se comprueba el método directamente.
        is_concrete = not getattr(cls.run, "__isabstractmethod__", False)
        if is_concrete and not cls.key:
            raise TypeError(f"{cls.__name__} debe declarar un `key`")

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        """Ejecuta la etapa. Debe ser idempotente respecto a la pizarra de entrada."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Envoltura con validación de precondiciones y normalización de errores."""
        missing = [key for key in self.requires if key not in context.blackboard]
        if missing:
            raise AgentExecutionError(self.key, f"Faltan productos previos: {missing}")
        try:
            result = await self.run(context)
        except AgentExecutionError:
            raise
        except Exception as exc:
            raise AgentExecutionError(self.key, str(exc)) from exc

        unmet = [key for key in self.produces if key not in result.produced]
        if unmet:
            raise AgentExecutionError(self.key, f"No produjo lo declarado: {unmet}")
        return result

    def __repr__(self) -> str:
        return f"<Agent {self.key}>"
