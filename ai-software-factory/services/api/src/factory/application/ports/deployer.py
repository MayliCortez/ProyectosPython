"""Puerto del servicio de despliegue."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class DeploymentRequest:
    """Todo lo que un proveedor necesita para levantar un proyecto generado."""

    project_id: str
    project_slug: str
    deployment_id: str
    bundle: bytes
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeploymentOutcome:
    """Resultado de un intento de despliegue."""

    url: str | None
    image_tag: str | None = None
    logs: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and bool(self.url)


@runtime_checkable
class Deployer(Protocol):
    """Lleva un bundle generado hasta una URL funcional."""

    async def deploy(self, request: DeploymentRequest) -> DeploymentOutcome:
        """Despliega el proyecto y devuelve su URL, o el error que lo impidió."""
        ...

    async def stop(self, deployment_id: str) -> None:
        """Detiene un despliegue previamente iniciado."""
        ...
