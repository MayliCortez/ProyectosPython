"""Unidad de trabajo: agrupa los repositorios bajo una transacción común."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable

from factory.application.ports.repositories import (
    BuildRepository,
    ConversationRepository,
    DeploymentRepository,
    ModuleRepository,
    OrganizationRepository,
    ProjectRepository,
    SpecificationRepository,
    UserRepository,
)


@runtime_checkable
class UnitOfWork(Protocol):
    """Contexto transaccional.

    Al salir sin excepción se confirma; con excepción se revierte. Los servicios de
    aplicación son la única capa que la abre, de modo que un caso de uso siempre es
    atómico de principio a fin.

    Los repositorios se declaran como propiedades de solo lectura a propósito: así el
    protocolo es covariante y una implementación puede exponer sus repositorios
    concretos sin dejar de satisfacerlo.
    """

    @property
    def organizations(self) -> OrganizationRepository: ...

    @property
    def users(self) -> UserRepository: ...

    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def conversations(self) -> ConversationRepository: ...

    @property
    def specifications(self) -> SpecificationRepository: ...

    @property
    def builds(self) -> BuildRepository: ...

    @property
    def deployments(self) -> DeploymentRepository: ...

    @property
    def modules(self) -> ModuleRepository: ...

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
