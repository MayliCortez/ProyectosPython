"""Construcción de proyectos: encolado desde la API y ejecución en el worker."""

from __future__ import annotations

import logging
from collections.abc import Callable

from factory.agents.base import AgentContext, ProgressSink
from factory.agents.orchestrator import Orchestrator, PipelineReport
from factory.agents.pipeline import default_pipeline
from factory.agents.registry import default_registry
from factory.application.dto import BuildView
from factory.application.ports.event_bus import EventBus
from factory.application.ports.llm import LLMClient
from factory.application.ports.queue import Job, JobQueue
from factory.application.ports.storage import ObjectStorage
from factory.application.ports.uow import UnitOfWork
from factory.catalog.catalog import ModuleCatalog
from factory.codegen.bundler import bundle_artifacts
from factory.domain.entities import Build, Conversation, Project, ProjectStatus, User
from factory.domain.errors import ConflictError, NotFoundError
from factory.domain.events import BuildProgressed, BuildQueued
from factory.domain.value_objects import Artifact

logger = logging.getLogger(__name__)

UnitOfWorkFactory = Callable[[], UnitOfWork]

#: Tipo de trabajo que el worker reconoce para una construcción.
BUILD_JOB = "build_project"


class BuildService:
    """Orquesta el ciclo de construcción de un proyecto.

    La API solo encola: `request_build` deja el `Build` en estado `queued` y devuelve
    de inmediato. El worker llama a `execute_build`, que es donde corre el pipeline de
    agentes, se empaqueta el resultado y se actualiza el estado del proyecto.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: JobQueue,
        events: EventBus,
        llm: LLMClient,
        storage: ObjectStorage,
        catalog: ModuleCatalog,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._events = events
        self._llm = llm
        self._storage = storage
        self._catalog = catalog

    # ── API ───────────────────────────────────────────────────────────────────

    async def request_build(self, *, user: User, project_id: str) -> BuildView:
        """Valida el estado, crea el build y lo encola."""
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            if project.status in {ProjectStatus.BUILDING, ProjectStatus.DEPLOYING}:
                raise ConflictError("Ya hay una construcción o despliegue en curso")
            if project.status is ProjectStatus.ARCHIVED:
                raise ConflictError("El proyecto está archivado")

            conversation = await uow.conversations.get_for_project(project_id)
            if conversation is not None and conversation.has_blocking_questions:
                raise ConflictError(
                    "Quedan preguntas de aclaración sin responder",
                    details={"pending": len(conversation.pending_questions)},
                )

            build = Build(project_id=project_id)
            await uow.builds.add(build)
            project.transition_to(ProjectStatus.BUILDING)
            await uow.projects.update(project)
            view = BuildView.of(build)

        await self._queue.enqueue(
            Job(kind=BUILD_JOB, payload={"project_id": project_id, "build_id": view.id})
        )
        await self._events.publish(
            BuildQueued(project_id=project_id, payload={"build_id": view.id})
        )
        return view

    async def get(self, *, user: User, project_id: str, build_id: str) -> BuildView:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            build = await uow.builds.get(build_id)
            if build is None or build.project_id != project_id:
                raise NotFoundError(f"La construcción {build_id!r} no existe")
            return BuildView.of(build)

    async def list(self, *, user: User, project_id: str, limit: int = 20) -> list[BuildView]:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            builds = await uow.builds.list_for_project(project_id, limit=limit)
            return [BuildView.of(build) for build in builds]

    async def download_url(self, *, user: User, project_id: str, build_id: str) -> str:
        """URL temporal de descarga del bundle generado."""
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            build = await uow.builds.get(build_id)
            if build is None or build.project_id != project_id:
                raise NotFoundError(f"La construcción {build_id!r} no existe")
            if not build.bundle_key:
                raise ConflictError("La construcción todavía no ha producido un paquete")
            return await self._storage.presigned_url(build.bundle_key)

    # ── Worker ────────────────────────────────────────────────────────────────

    async def execute_build(self, *, project_id: str, build_id: str) -> PipelineReport:
        """Ejecuta el pipeline completo. Es el punto de entrada del worker."""
        async with self._uow_factory() as uow:
            project = await uow.projects.get(project_id)
            build = await uow.builds.get(build_id)
            if project is None or build is None:
                raise NotFoundError("El proyecto o la construcción no existen")
            conversation = await uow.conversations.get_for_project(project_id) or Conversation(
                project_id=project_id
            )

        context = AgentContext(
            project=project,
            conversation=conversation,
            llm=self._llm,
            catalog=self._catalog,
            progress=self._progress_sink(project_id, build_id),
        )
        orchestrator = Orchestrator(
            default_registry(), default_pipeline(), emit=self._events.publish
        )
        report = await orchestrator.run(
            project=project, conversation=conversation, build=build, context=context
        )

        if report.succeeded:
            await self._persist_success(project, conversation, build, context)
        elif report.awaiting_clarification:
            await self._persist_clarification(project, conversation, build)
        else:
            await self._persist_failure(project, conversation, build)

        return report

    # ── Persistencia de los resultados ────────────────────────────────────────

    async def _persist_success(
        self,
        project: Project,
        conversation: Conversation,
        build: Build,
        context: AgentContext,
    ) -> None:
        artifacts: list[Artifact] = list(context.artifacts.values())
        specification = context.blackboard.get("specification")

        bundle = bundle_artifacts(artifacts, root=str(project.slug))
        bundle_key = f"projects/{project.id}/builds/{build.id}/bundle.zip"
        await self._storage.put(bundle_key, bundle)

        build.artifacts = artifacts
        build.bundle_key = bundle_key
        if specification is not None:
            build.specification_id = specification.id

        project.transition_to(ProjectStatus.BUILT)

        async with self._uow_factory() as uow:
            if specification is not None:
                await uow.specifications.add(specification)
            await uow.builds.update(build)
            await uow.projects.update(project)
            await uow.conversations.update(conversation)

        logger.info(
            "Construcción %s completada: %s ficheros, %s bytes empaquetados",
            build.id,
            len(artifacts),
            len(bundle),
        )

    async def _persist_clarification(
        self, project: Project, conversation: Conversation, build: Build
    ) -> None:
        """Devuelve el proyecto a la espera del usuario: no es un fallo del sistema."""
        project.transition_to(ProjectStatus.FAILED)
        project.transition_to(ProjectStatus.GATHERING_REQUIREMENTS)
        async with self._uow_factory() as uow:
            await uow.builds.update(build)
            await uow.projects.update(project)
            await uow.conversations.update(conversation)

    async def _persist_failure(
        self, project: Project, conversation: Conversation, build: Build
    ) -> None:
        if project.can_transition_to(ProjectStatus.FAILED):
            project.transition_to(ProjectStatus.FAILED)
        async with self._uow_factory() as uow:
            await uow.builds.update(build)
            await uow.projects.update(project)
            await uow.conversations.update(conversation)

    def _progress_sink(self, project_id: str, build_id: str) -> ProgressSink:
        async def emit(line: str) -> None:
            await self._events.publish(
                BuildProgressed(
                    project_id=project_id, payload={"build_id": build_id, "message": line}
                )
            )

        return emit

    async def _load_owned(self, uow: UnitOfWork, user: User, project_id: str) -> Project:
        project = await uow.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"El proyecto {project_id!r} no existe")
        user.require_same_organization(project.organization_id)
        return project
