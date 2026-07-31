"""Alta, consulta y ciclo de vida de los proyectos."""

from __future__ import annotations

from collections.abc import Callable

from factory.application.dto import ProjectView, RequirementsView, SpecificationView
from factory.application.ports.event_bus import EventBus
from factory.application.ports.uow import UnitOfWork
from factory.domain.entities import Conversation, MessageRole, Project, ProjectStatus, User
from factory.domain.errors import ConflictError, NotFoundError
from factory.domain.events import ProjectCreated

UnitOfWorkFactory = Callable[[], UnitOfWork]


class ProjectService:
    """Gestiona los proyectos de una organización.

    Toda lectura pasa por `_load_owned`, que comprueba la pertenencia del proyecto a
    la organización del solicitante: la autorización no queda al criterio de cada
    router.
    """

    def __init__(self, uow_factory: UnitOfWorkFactory, events: EventBus) -> None:
        self._uow_factory = uow_factory
        self._events = events

    async def create(self, *, user: User, name: str, prompt: str = "") -> tuple[ProjectView, str]:
        """Crea el proyecto y su conversación. Devuelve la vista y el id de conversación."""
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(user.organization_id)
            if organization is None:
                raise NotFoundError("La organización del usuario no existe")

            used = await uow.projects.count_for_organization(user.organization_id)
            if used >= organization.max_projects:
                raise ConflictError(
                    f"La organización ha alcanzado su límite de {organization.max_projects} "
                    "proyectos",
                    details={"limit": organization.max_projects},
                )

            project = Project.create(
                organization_id=user.organization_id,
                name=name,
                prompt=prompt,
                created_by=user.id,
            )
            await uow.projects.add(project)

            conversation = Conversation(project_id=project.id)
            if prompt.strip():
                conversation.add_message(MessageRole.USER, prompt)
            await uow.conversations.add(conversation)

            view = ProjectView.of(project)
            conversation_id = conversation.id

        await self._events.publish(ProjectCreated(project_id=view.id, payload={"name": view.name}))
        return view, conversation_id

    async def get(self, *, user: User, project_id: str) -> ProjectView:
        async with self._uow_factory() as uow:
            return ProjectView.of(await self._load_owned(uow, user, project_id))

    async def list(self, *, user: User, limit: int = 50, offset: int = 0) -> list[ProjectView]:
        async with self._uow_factory() as uow:
            projects = await uow.projects.list_for_organization(
                user.organization_id, limit=limit, offset=offset
            )
            return [ProjectView.of(project) for project in projects]

    async def rename(self, *, user: User, project_id: str, name: str) -> ProjectView:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            if not project.is_editable:
                raise ConflictError("El proyecto no admite cambios en su estado actual")
            project.name = name.strip()
            project.touch()
            await uow.projects.update(project)
            return ProjectView.of(project)

    async def archive(self, *, user: User, project_id: str) -> ProjectView:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            project.transition_to(ProjectStatus.ARCHIVED)
            await uow.projects.update(project)
            return ProjectView.of(project)

    async def delete(self, *, user: User, project_id: str) -> None:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            await uow.projects.delete(project.id)

    async def requirements(self, *, user: User, project_id: str) -> RequirementsView | None:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            requirements = await uow.specifications.latest_requirements(project_id)
            return RequirementsView.of(requirements) if requirements else None

    async def specification(self, *, user: User, project_id: str) -> SpecificationView | None:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            specification = await uow.specifications.latest_for_project(project_id)
            return SpecificationView.of(specification) if specification else None

    async def _load_owned(self, uow: UnitOfWork, user: User, project_id: str) -> Project:
        project = await uow.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"El proyecto {project_id!r} no existe")
        user.require_same_organization(project.organization_id)
        return project
