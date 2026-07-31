"""Catálogo de módulos e instalación por proyecto."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from factory.application.dto import ModuleInstallationView
from factory.application.ports.event_bus import EventBus
from factory.application.ports.uow import UnitOfWork
from factory.catalog.catalog import ModuleCatalog
from factory.catalog.installer import InstallPlan, ModuleInstaller
from factory.domain.entities import ModuleInstallation, Project, User
from factory.domain.errors import ConflictError, NotFoundError
from factory.domain.events import ModuleInstalled, ModuleRemoved
from factory.domain.value_objects import SemVer

UnitOfWorkFactory = Callable[[], UnitOfWork]


class ModuleService:
    """Instala, actualiza y elimina módulos sin dejar el proyecto inconsistente.

    Todo cambio se planifica primero con el `ModuleInstaller`; si el plan no es válido
    (dependencias rotas, conflictos, módulos del núcleo) la operación se rechaza antes
    de tocar la base de datos.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        catalog: ModuleCatalog,
        events: EventBus,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._installer = ModuleInstaller(catalog)
        self._events = events

    # ── Catálogo ──────────────────────────────────────────────────────────────

    def catalog(self, *, query: str = "") -> list[dict[str, Any]]:
        """Módulos disponibles, opcionalmente filtrados por texto."""
        manifests = self._catalog.search(query) if query else self._catalog.all()
        return [manifest.summary() for manifest in manifests]

    def describe(self, key: str) -> dict[str, Any]:
        return self._catalog.get(key).summary()

    # ── Instalación en un proyecto ────────────────────────────────────────────

    async def installed(self, *, user: User, project_id: str) -> list[ModuleInstallationView]:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            installations = await uow.modules.list_for_project(project_id)
            return [ModuleInstallationView.of(item) for item in installations]

    async def install(
        self, *, user: User, project_id: str, keys: list[str]
    ) -> tuple[list[ModuleInstallationView], InstallPlan]:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            self._assert_editable(project)

            current = [item.module_key for item in await uow.modules.list_for_project(project_id)]
            plan = self._installer.plan_install(current, keys)

            for key in plan.added:
                manifest = self._catalog.get(key)
                await uow.modules.add(
                    ModuleInstallation(
                        project_id=project_id,
                        module_key=key,
                        version=manifest.version,
                    )
                )
            project.set_modules(list(plan.resulting))
            await uow.projects.update(project)

            installations = await uow.modules.list_for_project(project_id)
            views = [ModuleInstallationView.of(item) for item in installations]

        if plan.added:
            await self._events.publish(
                ModuleInstalled(project_id=project_id, payload={"modules": list(plan.added)})
            )
        return views, plan

    async def remove(
        self, *, user: User, project_id: str, keys: list[str], cascade: bool = False
    ) -> tuple[list[ModuleInstallationView], InstallPlan]:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            self._assert_editable(project)

            current = [item.module_key for item in await uow.modules.list_for_project(project_id)]
            plan = self._installer.plan_remove(current, keys, cascade=cascade)

            for key in plan.removed:
                await uow.modules.remove(project_id, key)
            project.set_modules(list(plan.resulting))
            await uow.projects.update(project)

            installations = await uow.modules.list_for_project(project_id)
            views = [ModuleInstallationView.of(item) for item in installations]

        if plan.removed:
            await self._events.publish(
                ModuleRemoved(project_id=project_id, payload={"modules": list(plan.removed)})
            )
        return views, plan

    async def upgrade(
        self, *, user: User, project_id: str, key: str, version: str
    ) -> ModuleInstallationView:
        target = SemVer.parse(version)
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            self._assert_editable(project)

            installation = await uow.modules.get(project_id, key)
            if installation is None:
                raise NotFoundError(f"El módulo {key!r} no está instalado en el proyecto")

            current = [item.module_key for item in await uow.modules.list_for_project(project_id)]
            self._installer.plan_upgrade(current, key, target)

            installation.upgrade_to(target)
            await uow.modules.update(installation)
            return ModuleInstallationView.of(installation)

    async def sync_from_specification(self, *, project_id: str, keys: list[str]) -> None:
        """Alinea las instalaciones con lo que decidió el arquitecto durante el build."""
        async with self._uow_factory() as uow:
            existing = {
                item.module_key: item for item in await uow.modules.list_for_project(project_id)
            }
            for key in keys:
                manifest = self._catalog.try_get(key)
                if manifest is None or key in existing:
                    continue
                await uow.modules.add(
                    ModuleInstallation(
                        project_id=project_id, module_key=key, version=manifest.version
                    )
                )
            for key in set(existing) - set(keys):
                await uow.modules.remove(project_id, key)

    def _assert_editable(self, project: Project) -> None:
        if not project.is_editable:
            raise ConflictError(
                "No se pueden cambiar los módulos mientras el proyecto se construye o despliega",
                details={"status": str(project.status)},
            )

    async def _load_owned(self, uow: UnitOfWork, user: User, project_id: str) -> Project:
        project = await uow.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"El proyecto {project_id!r} no existe")
        user.require_same_organization(project.organization_id)
        return project
