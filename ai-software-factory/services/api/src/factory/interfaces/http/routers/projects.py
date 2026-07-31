"""Gestión de proyectos."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, status

from factory.interfaces.http.deps import CurrentUser, ProjectServiceDep
from factory.interfaces.http.schemas import (
    CreateProjectRequest,
    CreateProjectResponse,
    ProjectResponse,
    RenameProjectRequest,
    RequirementsResponse,
    SpecificationResponse,
)

router = APIRouter(prefix="/projects", tags=["proyectos"])


@router.post("", response_model=CreateProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    user: CurrentUser,
    projects: ProjectServiceDep,
) -> CreateProjectResponse:
    """Crea un proyecto y abre su conversación con la IA."""
    view, conversation_id = await projects.create(
        user=user, name=payload.name, prompt=payload.prompt
    )
    return CreateProjectResponse(
        project=ProjectResponse(**asdict(view)), conversation_id=conversation_id
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user: CurrentUser,
    projects: ProjectServiceDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ProjectResponse]:
    """Proyectos de la organización, del más reciente al más antiguo."""
    views = await projects.list(user=user, limit=limit, offset=offset)
    return [ProjectResponse(**asdict(view)) for view in views]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str, user: CurrentUser, projects: ProjectServiceDep
) -> ProjectResponse:
    return ProjectResponse(**asdict(await projects.get(user=user, project_id=project_id)))


@router.patch("/{project_id}", response_model=ProjectResponse)
async def rename_project(
    project_id: str,
    payload: RenameProjectRequest,
    user: CurrentUser,
    projects: ProjectServiceDep,
) -> ProjectResponse:
    view = await projects.rename(user=user, project_id=project_id, name=payload.name)
    return ProjectResponse(**asdict(view))


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: str, user: CurrentUser, projects: ProjectServiceDep
) -> ProjectResponse:
    """Archiva el proyecto: deja de admitir cambios pero conserva su historial."""
    view = await projects.archive(user=user, project_id=project_id)
    return ProjectResponse(**asdict(view))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, user: CurrentUser, projects: ProjectServiceDep) -> None:
    await projects.delete(user=user, project_id=project_id)


@router.get("/{project_id}/requirements", response_model=RequirementsResponse)
async def get_requirements(
    project_id: str, user: CurrentUser, projects: ProjectServiceDep
) -> RequirementsResponse:
    """Documento de requisitos vigente del proyecto."""
    view = await projects.requirements(user=user, project_id=project_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Todavía no hay requisitos capturados")
    return RequirementsResponse(**asdict(view))


@router.get("/{project_id}/specification", response_model=SpecificationResponse)
async def get_specification(
    project_id: str, user: CurrentUser, projects: ProjectServiceDep
) -> SpecificationResponse:
    """Especificación técnica generada durante la última construcción."""
    view = await projects.specification(user=user, project_id=project_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Todavía no hay especificación")
    return SpecificationResponse(**asdict(view))
