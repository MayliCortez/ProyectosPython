"""Agente de despliegue: Dockerfile, compose, variables, scripts y pipeline."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.specialists._blueprint import blueprint_from
from factory.codegen.renderers import render_ci, render_deployment


class DeploymentAgent(Agent):
    """Prepara todo lo necesario para que el proyecto se pueda desplegar sin tocar nada.

    Solo produce artefactos: el despliegue efectivo lo realiza el servicio de
    despliegue con el bundle resultante, fuera del proceso de la fábrica.
    """

    key = "deployment_agent"
    name = "Agente de despliegue"
    requires = ("specification",)
    produces = ("deploy_files",)

    async def run(self, context: AgentContext) -> AgentResult:
        blueprint = blueprint_from(context)
        await context.log("Preparando los artefactos de despliegue")

        artifacts = [*render_deployment(blueprint), *render_ci(blueprint)]
        paths = [artifact.path for artifact in artifacts]

        await context.log(
            f"{len(artifacts)} artefacto(s) de despliegue; "
            f"{len(blueprint.env_vars)} variable(s) de entorno declaradas"
        )
        return AgentResult(produced={"deploy_files": paths}, artifacts=artifacts)
