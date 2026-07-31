"""Agente analista de requisitos: convierte lenguaje natural en requisitos."""

from __future__ import annotations

from typing import Any

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.prompts import REQUIREMENTS_ANALYST, REQUIREMENTS_SCHEMA
from factory.domain.entities.specification import RequirementsDocument, UserStory
from factory.domain.value_objects import Artifact, BusinessDomain, ClarifyingQuestion


class RequirementsAnalyst(Agent):
    """Detecta el dominio, redacta el documento de requisitos y pregunta lo que falta.

    Es el único agente que puede terminar *sin* producto final: si quedan preguntas
    obligatorias sin responder, deja las preguntas en la conversación y el orquestador
    detiene el pipeline hasta que el usuario conteste.
    """

    key = "requirements_analyst"
    name = "Analista de requisitos"
    requires = ()
    produces = ("requirements",)

    async def run(self, context: AgentContext) -> AgentResult:
        await context.log("Analizando la petición del usuario")

        response = await context.llm.complete_json(
            system=REQUIREMENTS_ANALYST,
            prompt=self._build_prompt(context),
            schema=REQUIREMENTS_SCHEMA,
            schema_name="requirements",
        )
        data = response.data

        questions = [
            ClarifyingQuestion(
                id=str(item["id"]),
                text=str(item["text"]),
                rationale=str(item.get("rationale", "")),
                options=tuple(item.get("options", ())),
                required=bool(item.get("required", True)),
            )
            for item in data.get("questions", [])
            # No se vuelve a preguntar lo que el usuario ya respondió.
            if str(item["id"]) not in context.conversation.answers
        ]
        if questions:
            context.conversation.ask(questions)
            await context.log(f"{len(questions)} pregunta(s) de aclaración pendientes")

        requirements = self._build_document(context, data)
        catalog_keys = context.catalog.keys()
        requirements.suggested_modules = [
            key for key in requirements.suggested_modules if key in catalog_keys
        ]

        await context.log(
            f"Dominio detectado: {requirements.business_domain} — "
            f"{len(requirements.stories)} historia(s) de usuario"
        )

        return AgentResult(
            produced={"requirements": requirements},
            artifacts=[
                Artifact("docs/REQUISITOS.md", requirements.to_markdown(), "markdown"),
            ],
            logs=[f"Historias: {len(requirements.stories)}"],
        )

    def _build_prompt(self, context: AgentContext) -> str:
        answers = context.conversation.answers_summary()
        catalog = "\n".join(
            f"- {manifest.key}: {manifest.description}" for manifest in context.catalog.all()
        )
        request = context.conversation.user_prompt or context.project.prompt
        sections = [
            f"<peticion_usuario>\n{request}\n</peticion_usuario>",
            f"<catalogo_modulos>\n{catalog}\n</catalogo_modulos>",
        ]
        if answers:
            sections.append(f"<respuestas_usuario>\n{answers}\n</respuestas_usuario>")
        return "\n\n".join(sections)

    def _build_document(self, context: AgentContext, data: dict[str, Any]) -> RequirementsDocument:
        stories = [
            UserStory(
                id=str(item["id"]),
                role=str(item["role"]),
                goal=str(item["goal"]),
                benefit=str(item.get("benefit", "")),
                acceptance_criteria=tuple(item.get("acceptance_criteria", ())),
                priority=int(item.get("priority", 2)),
            )
            for item in data.get("stories", [])
        ]
        return RequirementsDocument(
            project_id=context.project.id,
            summary=str(data.get("summary", "")).strip(),
            business_domain=BusinessDomain(data.get("business_domain", "generic")),
            stories=stories,
            constraints=list(data.get("constraints", [])),
            out_of_scope=list(data.get("out_of_scope", [])),
            suggested_modules=list(data.get("suggested_modules", [])),
        )
