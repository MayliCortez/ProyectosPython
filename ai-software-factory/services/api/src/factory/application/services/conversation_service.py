"""Chat con la IA: captura de requisitos y respuesta a preguntas de aclaración."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from factory.agents.base import AgentContext
from factory.agents.specialists import RequirementsAnalyst
from factory.application.dto import ConversationView
from factory.application.ports.event_bus import EventBus
from factory.application.ports.llm import LLMClient
from factory.application.ports.uow import UnitOfWork
from factory.catalog.catalog import ModuleCatalog
from factory.domain.entities import Conversation, MessageRole, Project, ProjectStatus, User
from factory.domain.entities.specification import RequirementsDocument
from factory.domain.errors import ConflictError, NotFoundError
from factory.domain.events import ClarificationRequested, RequirementsCaptured

UnitOfWorkFactory = Callable[[], UnitOfWork]


class ConversationService:
    """Turno interactivo del chat.

    El análisis de requisitos se ejecuta **en línea**: es una sola llamada al modelo y
    el usuario espera su respuesta. Todo lo demás —arquitectura, generación, pruebas—
    va a la cola, porque dura minutos y no puede bloquear una petición HTTP.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        events: EventBus,
        llm: LLMClient,
        catalog: ModuleCatalog,
    ) -> None:
        self._uow_factory = uow_factory
        self._events = events
        self._llm = llm
        self._catalog = catalog
        self._analyst = RequirementsAnalyst()

    async def get(self, *, user: User, project_id: str) -> ConversationView:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            conversation = await uow.conversations.get_for_project(project_id)
            if conversation is None:
                raise NotFoundError("El proyecto no tiene conversación asociada")
            return ConversationView.of(conversation)

    async def send_message(self, *, user: User, project_id: str, content: str) -> ConversationView:
        """Añade el mensaje del usuario y vuelve a analizar los requisitos."""
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            if project.status is ProjectStatus.ARCHIVED:
                raise ConflictError("El proyecto está archivado")

            conversation = await self._require_conversation(uow, project_id)
            conversation.add_message(MessageRole.USER, content)
            if not project.prompt:
                project.prompt = content.strip()

            requirements = await self._analyze(project, conversation)
            await uow.specifications.add_requirements(requirements)
            self._advance(project, conversation)

            await uow.conversations.update(conversation)
            await uow.projects.update(project)
            view = ConversationView.of(conversation)
            pending = list(conversation.pending_questions)

        await self._publish(project_id, requirements, pending)
        return view

    async def answer(
        self, *, user: User, project_id: str, question_id: str, answer: str
    ) -> ConversationView:
        """Registra la respuesta a una pregunta y vuelve a evaluar los requisitos."""
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            conversation = await self._require_conversation(uow, project_id)

            conversation.answer(question_id, answer)
            conversation.add_message(MessageRole.USER, answer, metadata={"answers": question_id})

            requirements = await self._analyze(project, conversation)
            await uow.specifications.add_requirements(requirements)
            self._advance(project, conversation)

            await uow.conversations.update(conversation)
            await uow.projects.update(project)
            view = ConversationView.of(conversation)
            pending = list(conversation.pending_questions)

        await self._publish(project_id, requirements, pending)
        return view

    # ── Interno ───────────────────────────────────────────────────────────────

    async def _analyze(self, project: Project, conversation: Conversation) -> RequirementsDocument:
        """Ejecuta el analista y deja la respuesta del asistente en la conversación."""
        context = AgentContext(
            project=project,
            conversation=conversation,
            llm=self._llm,
            catalog=self._catalog,
        )
        result = await self._analyst.execute(context)
        requirements: RequirementsDocument = result.produced["requirements"]

        project.business_domain = requirements.business_domain
        conversation.add_message(
            MessageRole.ASSISTANT,
            self._assistant_reply(requirements, conversation),
            metadata={
                "requirements_id": requirements.id,
                "pending_questions": len(conversation.pending_questions),
            },
        )
        return requirements

    def _assistant_reply(
        self, requirements: RequirementsDocument, conversation: Conversation
    ) -> str:
        lines = [requirements.summary]
        if requirements.suggested_modules:
            lines.append(
                "Módulos propuestos: " + ", ".join(f"`{m}`" for m in requirements.suggested_modules)
            )
        if conversation.pending_questions:
            lines.append("Para poder especificar el sistema necesito saber:")
            lines.extend(
                f"{index}. {question.text}"
                for index, question in enumerate(conversation.pending_questions, start=1)
            )
        else:
            lines.append("Con esto tengo lo necesario. Puedes lanzar la construcción del proyecto.")
        return "\n\n".join(lines)

    def _advance(self, project: Project, conversation: Conversation) -> None:
        """Mueve el proyecto según queden o no preguntas obligatorias."""
        if project.status is ProjectStatus.DRAFT:
            project.transition_to(ProjectStatus.GATHERING_REQUIREMENTS)
        if not conversation.has_blocking_questions and project.can_transition_to(
            ProjectStatus.SPECIFIED
        ):
            project.transition_to(ProjectStatus.SPECIFIED)

    async def _publish(
        self,
        project_id: str,
        requirements: RequirementsDocument,
        pending: Sequence[object],
    ) -> None:
        await self._events.publish(
            RequirementsCaptured(
                project_id=project_id,
                payload={
                    "requirements_id": requirements.id,
                    "domain": str(requirements.business_domain),
                    "stories": len(requirements.stories),
                },
            )
        )
        if pending:
            await self._events.publish(
                ClarificationRequested(project_id=project_id, payload={"pending": len(pending)})
            )

    async def _require_conversation(self, uow: UnitOfWork, project_id: str) -> Conversation:
        conversation = await uow.conversations.get_for_project(project_id)
        if conversation is None:
            conversation = Conversation(project_id=project_id)
            await uow.conversations.add(conversation)
        return conversation

    async def _load_owned(self, uow: UnitOfWork, user: User, project_id: str) -> Project:
        project = await uow.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"El proyecto {project_id!r} no existe")
        user.require_same_organization(project.organization_id)
        return project
