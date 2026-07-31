"""Despliegue del proyecto generado en un proveedor de contenedores."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from factory.domain.errors import InvalidTransitionError, ValidationError
from factory.domain.value_objects import new_id, utcnow


class DeploymentProvider(StrEnum):
    """Destino del despliegue. Todos consumen el mismo bundle Docker."""

    DOCKER_LOCAL = "docker_local"
    VPS_SSH = "vps_ssh"
    CONTAINER_REGISTRY = "container_registry"


class DeploymentStatus(StrEnum):
    PENDING = "pending"
    PUSHING = "pushing"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


_ALLOWED: dict[DeploymentStatus, frozenset[DeploymentStatus]] = {
    DeploymentStatus.PENDING: frozenset({DeploymentStatus.PUSHING, DeploymentStatus.FAILED}),
    DeploymentStatus.PUSHING: frozenset({DeploymentStatus.STARTING, DeploymentStatus.FAILED}),
    DeploymentStatus.STARTING: frozenset({DeploymentStatus.RUNNING, DeploymentStatus.FAILED}),
    DeploymentStatus.RUNNING: frozenset({DeploymentStatus.STOPPED, DeploymentStatus.FAILED}),
    DeploymentStatus.FAILED: frozenset({DeploymentStatus.PENDING}),
    DeploymentStatus.STOPPED: frozenset({DeploymentStatus.PENDING}),
}


@dataclass(slots=True)
class Deployment:
    """Instancia desplegada de un build concreto, con su URL funcional."""

    project_id: str
    build_id: str
    provider: DeploymentProvider = DeploymentProvider.DOCKER_LOCAL
    status: DeploymentStatus = DeploymentStatus.PENDING
    url: str | None = None
    image_tag: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def transition_to(self, target: DeploymentStatus) -> None:
        if target == self.status:
            return
        if target not in _ALLOWED[self.status]:
            raise InvalidTransitionError("Deployment", self.status, target)
        self.status = target
        self.updated_at = utcnow()

    def mark_running(self, url: str) -> None:
        """El contenedor responde: se publica la URL entregable al usuario."""
        if not url.startswith(("http://", "https://")):
            raise ValidationError(f"URL de despliegue inválida: {url!r}")
        self.transition_to(DeploymentStatus.RUNNING)
        self.url = url

    def fail(self, error: str) -> None:
        self.transition_to(DeploymentStatus.FAILED)
        self.error = error

    def log(self, line: str) -> None:
        self.logs.append(f"[{utcnow().isoformat()}] {line}")
        self.updated_at = utcnow()

    @property
    def is_live(self) -> bool:
        return self.status is DeploymentStatus.RUNNING and bool(self.url)
