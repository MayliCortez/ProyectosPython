"""Agente generador de frontend: aplicación Next.js con panel y páginas CRUD."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.specialists._blueprint import blueprint_from
from factory.codegen.renderers import render_frontend


class FrontendGenerator(Agent):
    """Materializa el panel administrativo y las pantallas de cada entidad."""

    key = "frontend_generator"
    name = "Generador de frontend"
    requires = ("specification",)
    produces = ("frontend_files",)

    async def run(self, context: AgentContext) -> AgentResult:
        blueprint = blueprint_from(context)
        await context.log("Generando el frontend")

        artifacts = render_frontend(blueprint)
        paths = [artifact.path for artifact in artifacts]

        await context.log(f"{len(artifacts)} fichero(s) de frontend generados")
        return AgentResult(
            produced={"frontend_files": paths},
            artifacts=artifacts,
            logs=[f"Pantallas: {len(blueprint.pages) + len(blueprint.entities)}"],
        )
