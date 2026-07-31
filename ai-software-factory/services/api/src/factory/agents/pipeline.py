"""Definición y validación del pipeline de construcción.

El pipeline es declarativo: una lista de etapas, cada una asociada a un agente. Las
dependencias no se escriben a mano, se derivan de los `requires`/`produces` de los
agentes, de modo que es imposible declarar un orden incoherente sin que la validación
lo detecte antes de ejecutar nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from factory.agents.registry import AgentRegistry
from factory.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class PipelineStage:
    """Etapa del pipeline: un agente y su carácter obligatorio."""

    name: str
    agent_key: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class Pipeline:
    """Secuencia de etapas con su plan de ejecución por niveles."""

    stages: tuple[PipelineStage, ...] = field(default_factory=tuple)

    def stage(self, name: str) -> PipelineStage:
        found = next((s for s in self.stages if s.name == name), None)
        if found is None:
            raise ValidationError(f"El pipeline no tiene la etapa {name!r}")
        return found

    def validate(self, registry: AgentRegistry) -> None:
        """Comprueba que cada etapa existe y que sus dependencias se producen antes."""
        seen_names: set[str] = set()
        available: set[str] = set()

        for stage in self.stages:
            if stage.name in seen_names:
                raise ValidationError(f"Etapa duplicada en el pipeline: {stage.name!r}")
            seen_names.add(stage.name)

            agent = registry.get(stage.agent_key)
            missing = set(agent.requires) - available
            if missing:
                raise ValidationError(
                    f"La etapa {stage.name!r} requiere {sorted(missing)}, que ninguna "
                    "etapa anterior produce",
                    details={"stage": stage.name, "missing": sorted(missing)},
                )
            available.update(agent.produces)

    def execution_levels(self, registry: AgentRegistry) -> list[list[PipelineStage]]:
        """Agrupa las etapas en niveles ejecutables en paralelo.

        Una etapa entra en el nivel *n* cuando todo lo que necesita lo producen etapas
        de niveles anteriores. Backend y frontend, por ejemplo, caen en el mismo nivel.
        """
        pending = list(self.stages)
        produced: set[str] = set()
        levels: list[list[PipelineStage]] = []

        while pending:
            ready = [
                stage
                for stage in pending
                if set(registry.get(stage.agent_key).requires) <= produced
            ]
            if not ready:
                blocked = [stage.name for stage in pending]
                raise ValidationError(
                    f"Dependencias irresolubles en el pipeline: {blocked}",
                    details={"blocked": blocked},
                )
            levels.append(ready)
            for stage in ready:
                produced.update(registry.get(stage.agent_key).produces)
                pending.remove(stage)
        return levels


def default_pipeline() -> Pipeline:
    """Pipeline estándar de la fábrica, del requisito a la entrega."""
    return Pipeline(
        stages=(
            PipelineStage("analisis", "requirements_analyst"),
            PipelineStage("arquitectura", "software_architect"),
            PipelineStage("modelo_datos", "database_designer"),
            PipelineStage("contrato_api", "api_designer"),
            PipelineStage("backend", "backend_generator"),
            PipelineStage("frontend", "frontend_generator"),
            PipelineStage("despliegue", "deployment_agent"),
            PipelineStage("pruebas", "test_generator"),
            PipelineStage("revision", "code_reviewer"),
            PipelineStage("documentacion", "documentation_generator"),
            PipelineStage("mantenimiento", "maintenance_agent", optional=True),
        )
    )
