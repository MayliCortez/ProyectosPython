"""Agente de documentación: README, referencia de API y guía de arranque."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.prompts import DOCUMENTATION_WRITER
from factory.agents.specialists._blueprint import blueprint_from
from factory.codegen.renderers import render_docs
from factory.domain.value_objects import Artifact


class DocumentationGenerator(Agent):
    """Escribe la documentación de entrega del proyecto generado."""

    key = "documentation_generator"
    name = "Generador de documentación"
    requires = ("specification", "review")
    produces = ("docs_files",)

    async def run(self, context: AgentContext) -> AgentResult:
        blueprint = blueprint_from(context)
        await context.log("Redactando la documentación")

        artifacts = list(render_docs(blueprint))

        response = await context.llm.complete(
            system=DOCUMENTATION_WRITER,
            prompt=(
                f"Proyecto: {blueprint.name}\n"
                f"Petición original: {blueprint.project.prompt}\n"
                f"Módulos: {', '.join(blueprint.module_keys)}\n"
                f"Entidades: {', '.join(entity.name for entity in blueprint.entities)}\n\n"
                "Escribe una guía de puesta en marcha en Markdown, de menos de 400 "
                "palabras, para quien recibe este proyecto por primera vez."
            ),
        )
        if response.text.strip():
            artifacts.append(
                Artifact("docs/GUIA_INICIO.md", response.text.strip() + "\n", "markdown")
            )

        paths = [artifact.path for artifact in artifacts]
        await context.log(f"{len(artifacts)} documento(s) generados")
        return AgentResult(produced={"docs_files": paths}, artifacts=artifacts)
