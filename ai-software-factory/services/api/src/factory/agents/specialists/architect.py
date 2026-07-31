"""Agente arquitecto: decide pila, módulos definitivos y pantallas."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.products import ArchitectureDecision
from factory.agents.prompts import ARCHITECTURE_SCHEMA, SOFTWARE_ARCHITECT
from factory.catalog.installer import ModuleInstaller
from factory.domain.entities.specification import RequirementsDocument
from factory.domain.value_objects import Artifact, TechStack


class SoftwareArchitect(Agent):
    """Traduce requisitos en decisiones técnicas y en un conjunto de módulos coherente.

    La elección de módulos del modelo se pasa siempre por el instalador: aunque el LLM
    proponga un conjunto incompleto, las dependencias se arrastran y el resultado queda
    ordenado topológicamente.
    """

    key = "software_architect"
    name = "Arquitecto de software"
    requires = ("requirements",)
    produces = ("architecture",)

    async def run(self, context: AgentContext) -> AgentResult:
        requirements: RequirementsDocument = context.get("requirements")
        await context.log("Decidiendo arquitectura y módulos")

        catalog = "\n".join(
            f"- {manifest.key} ({manifest.category}): {manifest.description}"
            for manifest in context.catalog.all()
        )
        response = await context.llm.complete_json(
            system=SOFTWARE_ARCHITECT,
            prompt=(
                f"<requisitos>\n{requirements.to_markdown()}\n</requisitos>\n\n"
                f"<catalogo_modulos>\n{catalog}\n</catalogo_modulos>\n\n"
                f"Módulos propuestos por el analista: {requirements.suggested_modules}"
            ),
            schema=ARCHITECTURE_SCHEMA,
            schema_name="architecture",
        )
        data = response.data

        requested = [
            key
            for key in [*data.get("modules", []), *requirements.suggested_modules]
            if context.catalog.has(key)
        ]
        # El núcleo siempre está presente: sin usuarios y login no hay aplicación.
        requested = list(dict.fromkeys(["users", "login", "dashboard", *requested]))

        installer = ModuleInstaller(context.catalog)
        plan = installer.plan_install([], requested)
        modules = list(plan.resulting)

        stack_data = data.get("tech_stack") or {}
        tech_stack = TechStack(
            backend=str(stack_data.get("backend") or "fastapi"),
            frontend=str(stack_data.get("frontend") or "nextjs"),
            database=str(stack_data.get("database") or "postgresql"),
            cache=str(stack_data.get("cache") or "redis"),
        )

        pages = tuple(dict.fromkeys(str(page) for page in data.get("pages", [])))
        architecture = ArchitectureDecision(
            tech_stack=tech_stack,
            modules=tuple(modules),
            pages=pages,
            rationale=str(data.get("rationale", "")),
        )

        context.project.tech_stack = tech_stack
        context.project.set_modules(modules)

        await context.log(f"Módulos resueltos ({len(modules)}): {', '.join(modules)}")

        return AgentResult(
            produced={"architecture": architecture},
            artifacts=[Artifact("docs/ARQUITECTURA.md", self._document(architecture), "markdown")],
            logs=list(plan.warnings),
        )

    def _document(self, architecture: ArchitectureDecision) -> str:
        stack = architecture.tech_stack
        rows = "\n".join(f"| {layer} | {value} |" for layer, value in stack.as_dict().items())
        modules = "\n".join(f"- `{key}`" for key in architecture.modules)
        pages = "\n".join(f"- `{page}`" for page in architecture.pages)
        return (
            "# Decisiones de arquitectura\n\n"
            f"{architecture.rationale}\n\n"
            "## Pila tecnológica\n\n"
            "| Capa | Tecnología |\n|------|------------|\n"
            f"{rows}\n\n"
            "## Módulos instalados\n\n"
            f"{modules or '- ninguno'}\n\n"
            "## Pantallas\n\n"
            f"{pages or '- ninguna adicional'}\n"
        )
