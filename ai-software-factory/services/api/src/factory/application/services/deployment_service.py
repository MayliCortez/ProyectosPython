"""Despliegue de proyectos construidos y entrega de la URL funcional."""

from __future__ import annotations

import logging
from collections.abc import Callable

from factory.application.dto import DeploymentView
from factory.application.ports.deployer import Deployer, DeploymentRequest
from factory.application.ports.event_bus import EventBus
from factory.application.ports.queue import Job, JobQueue
from factory.application.ports.storage import ObjectStorage
from factory.application.ports.uow import UnitOfWork
from factory.domain.entities import (
    Build,
    BuildStatus,
    Deployment,
    DeploymentProvider,
    DeploymentStatus,
    Project,
    ProjectStatus,
    User,
)
from factory.domain.errors import ConflictError, NotFoundError
from factory.domain.events import (
    DeploymentFailed,
    DeploymentStarted,
    DeploymentSucceeded,
    DomainEvent,
)

logger = logging.getLogger(__name__)

UnitOfWorkFactory = Callable[[], UnitOfWork]

#: Tipo de trabajo que el worker reconoce para un despliegue.
DEPLOY_JOB = "deploy_project"


class DeploymentService:
    """Lleva un build correcto hasta una URL funcional.

    Igual que la construcción, el despliegue se encola: la API solo registra la
    intención y devuelve; el worker es quien habla con el proveedor.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: JobQueue,
        events: EventBus,
        storage: ObjectStorage,
        deployer: Deployer,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._events = events
        self._storage = storage
        self._deployer = deployer

    # ── API ───────────────────────────────────────────────────────────────────

    async def request_deployment(
        self,
        *,
        user: User,
        project_id: str,
        build_id: str | None = None,
        provider: DeploymentProvider = DeploymentProvider.DOCKER_LOCAL,
        env: dict[str, str] | None = None,
    ) -> DeploymentView:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            build = await self._resolve_build(uow, project_id, build_id)

            if build.status is not BuildStatus.SUCCEEDED or not build.bundle_key:
                raise ConflictError(
                    "Solo se pueden desplegar construcciones completadas con éxito",
                    details={"build_status": str(build.status)},
                )
            if project.status is ProjectStatus.DEPLOYING:
                raise ConflictError("Ya hay un despliegue en curso")

            deployment = Deployment(
                project_id=project_id,
                build_id=build.id,
                provider=provider,
                env=dict(env or {}),
            )
            await uow.deployments.add(deployment)
            project.transition_to(ProjectStatus.DEPLOYING)
            await uow.projects.update(project)
            view = DeploymentView.of(deployment)

        await self._queue.enqueue(
            Job(
                kind=DEPLOY_JOB,
                payload={"project_id": project_id, "deployment_id": view.id},
            )
        )
        await self._events.publish(
            DeploymentStarted(project_id=project_id, payload={"deployment_id": view.id})
        )
        return view

    async def get(self, *, user: User, project_id: str, deployment_id: str) -> DeploymentView:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            deployment = await uow.deployments.get(deployment_id)
            if deployment is None or deployment.project_id != project_id:
                raise NotFoundError(f"El despliegue {deployment_id!r} no existe")
            return DeploymentView.of(deployment)

    async def list(self, *, user: User, project_id: str, limit: int = 20) -> list[DeploymentView]:
        async with self._uow_factory() as uow:
            await self._load_owned(uow, user, project_id)
            deployments = await uow.deployments.list_for_project(project_id, limit=limit)
            return [DeploymentView.of(item) for item in deployments]

    async def stop(self, *, user: User, project_id: str, deployment_id: str) -> DeploymentView:
        async with self._uow_factory() as uow:
            project = await self._load_owned(uow, user, project_id)
            deployment = await uow.deployments.get(deployment_id)
            if deployment is None or deployment.project_id != project_id:
                raise NotFoundError(f"El despliegue {deployment_id!r} no existe")

            await self._deployer.stop(deployment_id)
            deployment.transition_to(DeploymentStatus.STOPPED)
            deployment.log("Despliegue detenido a petición del usuario")
            await uow.deployments.update(deployment)

            if project.status is ProjectStatus.DEPLOYED:
                project.live_url = None
                project.transition_to(ProjectStatus.BUILT)
                await uow.projects.update(project)
            return DeploymentView.of(deployment)

    # ── Worker ────────────────────────────────────────────────────────────────

    async def execute_deployment(self, *, project_id: str, deployment_id: str) -> DeploymentView:
        """Descarga el bundle, lo entrega al proveedor y publica el resultado."""
        async with self._uow_factory() as uow:
            project = await uow.projects.get(project_id)
            deployment = await uow.deployments.get(deployment_id)
            if project is None or deployment is None:
                raise NotFoundError("El proyecto o el despliegue no existen")
            build = await uow.builds.get(deployment.build_id)
            if build is None or not build.bundle_key:
                raise NotFoundError("La construcción asociada no tiene paquete")
            bundle_key = build.bundle_key

        bundle = await self._storage.get(bundle_key)
        deployment.transition_to(DeploymentStatus.PUSHING)
        deployment.log("Paquete recuperado del almacenamiento")
        deployment.transition_to(DeploymentStatus.STARTING)

        outcome = await self._deployer.deploy(
            DeploymentRequest(
                project_id=project_id,
                project_slug=str(project.slug),
                deployment_id=deployment_id,
                bundle=bundle,
                env=dict(deployment.env),
            )
        )
        for line in outcome.logs:
            deployment.log(line)

        event: DomainEvent
        if outcome.succeeded and outcome.url:
            deployment.image_tag = outcome.image_tag
            deployment.mark_running(outcome.url)
            project.mark_deployed(outcome.url)
            event = DeploymentSucceeded(
                project_id=project_id,
                payload={"deployment_id": deployment_id, "url": outcome.url},
            )
        else:
            error = outcome.error or "El proveedor no devolvió una URL"
            deployment.fail(error)
            if project.can_transition_to(ProjectStatus.FAILED):
                project.transition_to(ProjectStatus.FAILED)
            event = DeploymentFailed(
                project_id=project_id,
                payload={"deployment_id": deployment_id, "error": error},
            )

        async with self._uow_factory() as uow:
            await uow.deployments.update(deployment)
            await uow.projects.update(project)

        await self._events.publish(event)
        return DeploymentView.of(deployment)

    # ── Interno ───────────────────────────────────────────────────────────────

    async def _resolve_build(self, uow: UnitOfWork, project_id: str, build_id: str | None) -> Build:
        build = (
            await uow.builds.get(build_id)
            if build_id
            else await uow.builds.latest_for_project(project_id)
        )
        if build is None or build.project_id != project_id:
            raise NotFoundError("No hay ninguna construcción disponible para desplegar")
        return build

    async def _load_owned(self, uow: UnitOfWork, user: User, project_id: str) -> Project:
        project = await uow.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"El proyecto {project_id!r} no existe")
        user.require_same_organization(project.organization_id)
        return project
