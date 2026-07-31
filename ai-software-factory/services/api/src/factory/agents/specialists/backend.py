"""Agente generador de backend: modelos, esquemas, routers y migraciones."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.specialists._blueprint import blueprint_from
from factory.codegen.renderers import render_backend, render_database


class BackendGenerator(Agent):
    """Materializa el backend a partir de la especificación.

    La generación es determinista: dos ejecuciones con la misma especificación
    producen exactamente los mismos ficheros. La creatividad del modelo se ha aplicado
    ya en las etapas de análisis y diseño; a partir de aquí interesa la
    reproducibilidad, que es lo que permite regenerar un proyecto sin sorpresas.
    """

    key = "backend_generator"
    name = "Generador de backend"
    requires = ("specification",)
    produces = ("backend_files",)

    async def run(self, context: AgentContext) -> AgentResult:
        blueprint = blueprint_from(context)
        await context.log("Generando el backend")

        artifacts = [*render_backend(blueprint), *render_database(blueprint)]
        paths = [artifact.path for artifact in artifacts]

        await context.log(f"{len(artifacts)} fichero(s) de backend generados")
        return AgentResult(
            produced={"backend_files": paths},
            artifacts=artifacts,
            logs=[f"Entidades materializadas: {len(blueprint.entities)}"],
        )
