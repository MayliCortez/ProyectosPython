"""Unidad de trabajo sobre una sesión de SQLAlchemy."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from factory.domain.errors import ConflictError
from factory.infrastructure.db.repositories import (
    SqlBuildRepository,
    SqlConversationRepository,
    SqlDeploymentRepository,
    SqlModuleRepository,
    SqlOrganizationRepository,
    SqlProjectRepository,
    SqlSpecificationRepository,
    SqlUserRepository,
)
from factory.infrastructure.db.session import Database


class SqlAlchemyUnitOfWork:
    """Abre una sesión por caso de uso y confirma o revierte al salir.

    Los repositorios se crean sobre la misma sesión, de modo que todo lo que ocurre
    dentro del bloque `async with` forma una única transacción.
    """

    def __init__(self, database: Database) -> None:
        self._database = database
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        session = self._database.session()
        self._session = session
        self.organizations = SqlOrganizationRepository(session)
        self.users = SqlUserRepository(session)
        self.projects = SqlProjectRepository(session)
        self.conversations = SqlConversationRepository(session)
        self.specifications = SqlSpecificationRepository(session)
        self.builds = SqlBuildRepository(session)
        self.deployments = SqlDeploymentRepository(session)
        self.modules = SqlModuleRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        """Confirma sin cerrar: útil para publicar progreso a mitad de un trabajo largo."""
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise ConflictError("La unidad de trabajo se usa fuera de su bloque `async with`")
        return self._session
