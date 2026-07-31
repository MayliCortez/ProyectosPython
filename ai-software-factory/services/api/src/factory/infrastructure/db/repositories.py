"""Repositorios SQLAlchemy: implementación de los puertos de persistencia."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from factory.domain.entities import (
    Build,
    Conversation,
    Deployment,
    ModuleInstallation,
    Organization,
    Project,
    User,
)
from factory.domain.entities.specification import RequirementsDocument, Specification
from factory.infrastructure.db import mappers
from factory.infrastructure.db.models import (
    BuildRow,
    ConversationRow,
    DeploymentRow,
    MessageRow,
    ModuleInstallationRow,
    OrganizationRow,
    ProjectRow,
    RequirementsRow,
    SpecificationRow,
    UserRow,
)


class _Repository:
    """Base común: todos los repositorios comparten la sesión de la unidad de trabajo."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session


class SqlOrganizationRepository(_Repository):
    async def add(self, organization: Organization) -> None:
        self._session.add(mappers.organization_to_row(organization))

    async def get(self, organization_id: str) -> Organization | None:
        row = await self._session.get(OrganizationRow, organization_id)
        return mappers.organization_from_row(row) if row else None

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(
            select(OrganizationRow).where(OrganizationRow.slug == slug)
        )
        row = result.scalar_one_or_none()
        return mappers.organization_from_row(row) if row else None


class SqlUserRepository(_Repository):
    async def add(self, user: User) -> None:
        self._session.add(mappers.user_to_row(user))

    async def get(self, user_id: str) -> User | None:
        row = await self._session.get(UserRow, user_id)
        return mappers.user_from_row(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(UserRow).where(UserRow.email == email.strip().lower())
        )
        row = result.scalar_one_or_none()
        return mappers.user_from_row(row) if row else None

    async def list_for_organization(self, organization_id: str) -> list[User]:
        result = await self._session.execute(
            select(UserRow)
            .where(UserRow.organization_id == organization_id)
            .order_by(UserRow.created_at)
        )
        return [mappers.user_from_row(row) for row in result.scalars()]


class SqlProjectRepository(_Repository):
    async def add(self, project: Project) -> None:
        self._session.add(mappers.project_to_row(project))

    async def get(self, project_id: str) -> Project | None:
        row = await self._session.get(ProjectRow, project_id)
        return mappers.project_from_row(row) if row else None

    async def update(self, project: Project) -> None:
        row = await self._session.get(ProjectRow, project.id)
        if row is None:
            self._session.add(mappers.project_to_row(project))
            return
        mappers.apply_project(row, project)

    async def delete(self, project_id: str) -> None:
        await self._session.execute(delete(ProjectRow).where(ProjectRow.id == project_id))

    async def list_for_organization(
        self, organization_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Project]:
        result = await self._session.execute(
            select(ProjectRow)
            .where(ProjectRow.organization_id == organization_id)
            .order_by(ProjectRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [mappers.project_from_row(row) for row in result.scalars()]

    async def count_for_organization(self, organization_id: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ProjectRow)
            .where(ProjectRow.organization_id == organization_id)
        )
        return int(result.scalar_one())


class SqlConversationRepository(_Repository):
    async def add(self, conversation: Conversation) -> None:
        self._session.add(mappers.conversation_to_row(conversation))
        for message in conversation.messages:
            self._session.add(mappers.message_to_row(message))

    async def get(self, conversation_id: str) -> Conversation | None:
        row = await self._session.get(ConversationRow, conversation_id)
        return await self._hydrate(row)

    async def get_for_project(self, project_id: str) -> Conversation | None:
        result = await self._session.execute(
            select(ConversationRow).where(ConversationRow.project_id == project_id)
        )
        return await self._hydrate(result.scalar_one_or_none())

    async def update(self, conversation: Conversation) -> None:
        row = await self._session.get(ConversationRow, conversation.id)
        if row is None:
            await self.add(conversation)
            return
        mappers.apply_conversation(row, conversation)

        stored = await self._session.execute(
            select(MessageRow.id).where(MessageRow.conversation_id == conversation.id)
        )
        known = set(stored.scalars())
        # Los mensajes son inmutables: solo se insertan los nuevos.
        for message in conversation.messages:
            if message.id not in known:
                self._session.add(mappers.message_to_row(message))

    async def _hydrate(self, row: ConversationRow | None) -> Conversation | None:
        if row is None:
            return None
        result = await self._session.execute(
            select(MessageRow)
            .where(MessageRow.conversation_id == row.id)
            .order_by(MessageRow.created_at, MessageRow.id)
        )
        return mappers.conversation_from_row(row, list(result.scalars()))


class SqlSpecificationRepository(_Repository):
    async def add_requirements(self, requirements: RequirementsDocument) -> None:
        self._session.add(mappers.requirements_to_row(requirements))

    async def get_requirements(self, requirements_id: str) -> RequirementsDocument | None:
        row = await self._session.get(RequirementsRow, requirements_id)
        return mappers.requirements_from_row(row) if row else None

    async def latest_requirements(self, project_id: str) -> RequirementsDocument | None:
        result = await self._session.execute(
            select(RequirementsRow)
            .where(RequirementsRow.project_id == project_id)
            .order_by(RequirementsRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return mappers.requirements_from_row(row) if row else None

    async def add(self, specification: Specification) -> None:
        self._session.add(mappers.specification_to_row(specification))

    async def get(self, specification_id: str) -> Specification | None:
        row = await self._session.get(SpecificationRow, specification_id)
        return mappers.specification_from_row(row) if row else None

    async def latest_for_project(self, project_id: str) -> Specification | None:
        result = await self._session.execute(
            select(SpecificationRow)
            .where(SpecificationRow.project_id == project_id)
            .order_by(SpecificationRow.version.desc(), SpecificationRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return mappers.specification_from_row(row) if row else None


class SqlBuildRepository(_Repository):
    async def add(self, build: Build) -> None:
        self._session.add(mappers.build_to_row(build))

    async def get(self, build_id: str) -> Build | None:
        row = await self._session.get(BuildRow, build_id)
        return mappers.build_from_row(row) if row else None

    async def update(self, build: Build) -> None:
        row = await self._session.get(BuildRow, build.id)
        if row is None:
            self._session.add(mappers.build_to_row(build))
            return
        mappers.apply_build(row, build)

    async def list_for_project(self, project_id: str, *, limit: int = 20) -> list[Build]:
        result = await self._session.execute(
            select(BuildRow)
            .where(BuildRow.project_id == project_id)
            .order_by(BuildRow.created_at.desc())
            .limit(limit)
        )
        return [mappers.build_from_row(row) for row in result.scalars()]

    async def latest_for_project(self, project_id: str) -> Build | None:
        builds = await self.list_for_project(project_id, limit=1)
        return builds[0] if builds else None


class SqlDeploymentRepository(_Repository):
    async def add(self, deployment: Deployment) -> None:
        self._session.add(mappers.deployment_to_row(deployment))

    async def get(self, deployment_id: str) -> Deployment | None:
        row = await self._session.get(DeploymentRow, deployment_id)
        return mappers.deployment_from_row(row) if row else None

    async def update(self, deployment: Deployment) -> None:
        row = await self._session.get(DeploymentRow, deployment.id)
        if row is None:
            self._session.add(mappers.deployment_to_row(deployment))
            return
        mappers.apply_deployment(row, deployment)

    async def list_for_project(self, project_id: str, *, limit: int = 20) -> list[Deployment]:
        result = await self._session.execute(
            select(DeploymentRow)
            .where(DeploymentRow.project_id == project_id)
            .order_by(DeploymentRow.created_at.desc())
            .limit(limit)
        )
        return [mappers.deployment_from_row(row) for row in result.scalars()]

    async def active_for_project(self, project_id: str) -> Deployment | None:
        result = await self._session.execute(
            select(DeploymentRow)
            .where(DeploymentRow.project_id == project_id, DeploymentRow.status == "running")
            .order_by(DeploymentRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return mappers.deployment_from_row(row) if row else None


class SqlModuleRepository(_Repository):
    async def add(self, installation: ModuleInstallation) -> None:
        self._session.add(mappers.module_to_row(installation))

    async def update(self, installation: ModuleInstallation) -> None:
        row = await self._session.get(ModuleInstallationRow, installation.id)
        if row is None:
            self._session.add(mappers.module_to_row(installation))
            return
        mappers.apply_module(row, installation)

    async def get(self, project_id: str, module_key: str) -> ModuleInstallation | None:
        result = await self._session.execute(
            select(ModuleInstallationRow).where(
                ModuleInstallationRow.project_id == project_id,
                ModuleInstallationRow.module_key == module_key,
            )
        )
        row = result.scalar_one_or_none()
        return mappers.module_from_row(row) if row else None

    async def list_for_project(self, project_id: str) -> list[ModuleInstallation]:
        result = await self._session.execute(
            select(ModuleInstallationRow)
            .where(ModuleInstallationRow.project_id == project_id)
            .order_by(ModuleInstallationRow.installed_at)
        )
        return [mappers.module_from_row(row) for row in result.scalars()]

    async def remove(self, project_id: str, module_key: str) -> None:
        await self._session.execute(
            delete(ModuleInstallationRow).where(
                ModuleInstallationRow.project_id == project_id,
                ModuleInstallationRow.module_key == module_key,
            )
        )
