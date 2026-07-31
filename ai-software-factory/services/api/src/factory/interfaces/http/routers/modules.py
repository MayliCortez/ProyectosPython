"""Catálogo de módulos y su instalación por proyecto."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query

from factory.interfaces.http.deps import CurrentUser, ModuleServiceDep
from factory.interfaces.http.schemas import (
    InstallModulesRequest,
    ModuleInstallationResponse,
    ModuleOperationResponse,
    RemoveModulesRequest,
    UpgradeModuleRequest,
)

catalog_router = APIRouter(prefix="/modules", tags=["módulos"])
project_router = APIRouter(prefix="/projects/{project_id}/modules", tags=["módulos"])


@catalog_router.get("")
async def list_catalog(
    modules: ModuleServiceDep,
    q: str = Query("", description="Filtro por clave, nombre o descripción"),
) -> list[dict[str, Any]]:
    """Catálogo completo de módulos instalables."""
    return modules.catalog(query=q)


@catalog_router.get("/{module_key}")
async def describe_module(module_key: str, modules: ModuleServiceDep) -> dict[str, Any]:
    """Ficha de un módulo: dependencias, tablas, endpoints y permisos."""
    return modules.describe(module_key)


@project_router.get("", response_model=list[ModuleInstallationResponse])
async def installed_modules(
    project_id: str, user: CurrentUser, modules: ModuleServiceDep
) -> list[ModuleInstallationResponse]:
    views = await modules.installed(user=user, project_id=project_id)
    return [ModuleInstallationResponse(**asdict(view)) for view in views]


@project_router.post("", response_model=ModuleOperationResponse)
async def install_modules(
    project_id: str,
    payload: InstallModulesRequest,
    user: CurrentUser,
    modules: ModuleServiceDep,
) -> ModuleOperationResponse:
    """Instala módulos arrastrando sus dependencias."""
    views, plan = await modules.install(user=user, project_id=project_id, keys=payload.modules)
    return ModuleOperationResponse(
        installed=[ModuleInstallationResponse(**asdict(view)) for view in views],
        added=list(plan.added),
        warnings=list(plan.warnings),
    )


@project_router.post("/remove", response_model=ModuleOperationResponse)
async def remove_modules(
    project_id: str,
    payload: RemoveModulesRequest,
    user: CurrentUser,
    modules: ModuleServiceDep,
) -> ModuleOperationResponse:
    """Elimina módulos. Sin `cascade`, rechaza quitar algo del que otros dependen."""
    views, plan = await modules.remove(
        user=user, project_id=project_id, keys=payload.modules, cascade=payload.cascade
    )
    return ModuleOperationResponse(
        installed=[ModuleInstallationResponse(**asdict(view)) for view in views],
        removed=list(plan.removed),
        warnings=list(plan.warnings),
    )


@project_router.post("/{module_key}/upgrade", response_model=ModuleInstallationResponse)
async def upgrade_module(
    project_id: str,
    module_key: str,
    payload: UpgradeModuleRequest,
    user: CurrentUser,
    modules: ModuleServiceDep,
) -> ModuleInstallationResponse:
    """Sube la versión de un módulo si no rompe a sus dependientes."""
    view = await modules.upgrade(
        user=user, project_id=project_id, key=module_key, version=payload.version
    )
    return ModuleInstallationResponse(**asdict(view))
