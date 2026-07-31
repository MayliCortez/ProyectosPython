"""Construcciones de un proyecto."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query, status

from factory.interfaces.http.deps import BuildServiceDep, CurrentUser
from factory.interfaces.http.schemas import BuildResponse, DownloadResponse

router = APIRouter(prefix="/projects/{project_id}/builds", tags=["construcciones"])


@router.post("", response_model=BuildResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_build(project_id: str, user: CurrentUser, builds: BuildServiceDep) -> BuildResponse:
    """Encola la construcción. El progreso llega por `/ws/projects/{project_id}`."""
    view = await builds.request_build(user=user, project_id=project_id)
    return BuildResponse(**asdict(view))


@router.get("", response_model=list[BuildResponse])
async def list_builds(
    project_id: str,
    user: CurrentUser,
    builds: BuildServiceDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[BuildResponse]:
    views = await builds.list(user=user, project_id=project_id, limit=limit)
    return [BuildResponse(**asdict(view)) for view in views]


@router.get("/{build_id}", response_model=BuildResponse)
async def get_build(
    project_id: str, build_id: str, user: CurrentUser, builds: BuildServiceDep
) -> BuildResponse:
    """Estado de una construcción, con el detalle de cada etapa."""
    view = await builds.get(user=user, project_id=project_id, build_id=build_id)
    return BuildResponse(**asdict(view))


@router.get("/{build_id}/download", response_model=DownloadResponse)
async def download_build(
    project_id: str, build_id: str, user: CurrentUser, builds: BuildServiceDep
) -> DownloadResponse:
    """URL temporal para descargar el proyecto generado."""
    url = await builds.download_url(user=user, project_id=project_id, build_id=build_id)
    return DownloadResponse(url=url)
