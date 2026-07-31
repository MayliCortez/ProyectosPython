"""Despliegues de un proyecto."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query, status

from factory.domain.entities import DeploymentProvider
from factory.domain.errors import ValidationError
from factory.interfaces.http.deps import CurrentUser, DeploymentServiceDep
from factory.interfaces.http.schemas import CreateDeploymentRequest, DeploymentResponse

router = APIRouter(prefix="/projects/{project_id}/deployments", tags=["despliegues"])


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_deployment(
    project_id: str,
    payload: CreateDeploymentRequest,
    user: CurrentUser,
    deployments: DeploymentServiceDep,
) -> DeploymentResponse:
    """Despliega una construcción correcta y publica su URL cuando esté lista."""
    try:
        provider = DeploymentProvider(payload.provider)
    except ValueError as exc:
        raise ValidationError(
            f"Proveedor de despliegue no soportado: {payload.provider!r}",
            details={"allowed": [item.value for item in DeploymentProvider]},
        ) from exc

    view = await deployments.request_deployment(
        user=user,
        project_id=project_id,
        build_id=payload.build_id,
        provider=provider,
        env=payload.env,
    )
    return DeploymentResponse(**asdict(view))


@router.get("", response_model=list[DeploymentResponse])
async def list_deployments(
    project_id: str,
    user: CurrentUser,
    deployments: DeploymentServiceDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[DeploymentResponse]:
    views = await deployments.list(user=user, project_id=project_id, limit=limit)
    return [DeploymentResponse(**asdict(view)) for view in views]


@router.get("/{deployment_id}", response_model=DeploymentResponse)
async def get_deployment(
    project_id: str,
    deployment_id: str,
    user: CurrentUser,
    deployments: DeploymentServiceDep,
) -> DeploymentResponse:
    view = await deployments.get(user=user, project_id=project_id, deployment_id=deployment_id)
    return DeploymentResponse(**asdict(view))


@router.post("/{deployment_id}/stop", response_model=DeploymentResponse)
async def stop_deployment(
    project_id: str,
    deployment_id: str,
    user: CurrentUser,
    deployments: DeploymentServiceDep,
) -> DeploymentResponse:
    """Detiene el despliegue y libera sus recursos."""
    view = await deployments.stop(user=user, project_id=project_id, deployment_id=deployment_id)
    return DeploymentResponse(**asdict(view))
