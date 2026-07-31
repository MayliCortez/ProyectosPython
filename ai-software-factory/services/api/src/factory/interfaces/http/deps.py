"""Dependencias compartidas por los routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from factory.application.services import (
    AuthService,
    BuildService,
    ConversationService,
    DeploymentService,
    ModuleService,
    ProjectService,
)
from factory.container import Container
from factory.domain.entities import User
from factory.domain.errors import PermissionDeniedError

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    """El contenedor se guarda en el estado de la aplicación al arrancar."""
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_current_user(
    container: ContainerDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resuelve el usuario autenticado a partir del encabezado `Authorization`."""
    if credentials is None or not credentials.credentials:
        raise PermissionDeniedError("Falta el token de autenticación")
    return await container.auth.user_from_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_auth_service(container: ContainerDep) -> AuthService:
    return container.auth


def get_project_service(container: ContainerDep) -> ProjectService:
    return container.projects


def get_conversation_service(container: ContainerDep) -> ConversationService:
    return container.conversations


def get_module_service(container: ContainerDep) -> ModuleService:
    return container.modules


def get_build_service(container: ContainerDep) -> BuildService:
    return container.builds


def get_deployment_service(container: ContainerDep) -> DeploymentService:
    return container.deployments


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
ModuleServiceDep = Annotated[ModuleService, Depends(get_module_service)]
BuildServiceDep = Annotated[BuildService, Depends(get_build_service)]
DeploymentServiceDep = Annotated[DeploymentService, Depends(get_deployment_service)]
