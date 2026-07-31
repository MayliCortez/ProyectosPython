"""Proveedor de despliegue simulado.

Valida el bundle y devuelve una URL sin arrancar contenedores. Es el proveedor por
defecto en desarrollo y en pruebas: permite recorrer el flujo completo —incluido el
estado del despliegue y la URL entregada— en entornos donde no hay demonio Docker.
"""

from __future__ import annotations

import io
import zipfile

from factory.application.ports.deployer import DeploymentOutcome, DeploymentRequest

_REQUIRED = ("docker-compose.yml", "backend/Dockerfile", ".env.example")


class DryRunDeployer:
    """Comprueba que el bundle es desplegable y publica una URL simulada."""

    def __init__(self, *, host: str = "http://localhost", base_port: int = 9100) -> None:
        self._host = host.rstrip("/")
        self._base_port = base_port
        self.deployed: dict[str, str] = {}

    async def deploy(self, request: DeploymentRequest) -> DeploymentOutcome:
        try:
            with zipfile.ZipFile(io.BytesIO(request.bundle)) as archive:
                names = {name.split("/", 1)[-1] for name in archive.namelist()}
        except zipfile.BadZipFile:
            return DeploymentOutcome(url=None, error="El paquete del proyecto está corrupto")

        missing = [required for required in _REQUIRED if required not in names]
        if missing:
            return DeploymentOutcome(
                url=None,
                error=f"El paquete no incluye los artefactos de despliegue: {missing}",
            )

        port = self._base_port + (abs(hash(request.deployment_id)) % 400)
        url = f"{self._host}:{port}"
        self.deployed[request.deployment_id] = url
        return DeploymentOutcome(
            url=url,
            image_tag=f"{request.project_slug}:{request.deployment_id[:8]}",
            logs=(
                f"Verificados {len(names)} ficheros del paquete",
                "Despliegue simulado: no se han arrancado contenedores",
                f"URL asignada: {url}",
            ),
        )

    async def stop(self, deployment_id: str) -> None:
        self.deployed.pop(deployment_id, None)
