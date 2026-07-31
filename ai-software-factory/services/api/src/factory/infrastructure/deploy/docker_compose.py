"""Despliegue en un host con Docker mediante `docker compose`."""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from pathlib import Path

from factory.application.ports.deployer import DeploymentOutcome, DeploymentRequest

logger = logging.getLogger(__name__)


class DockerComposeDeployer:
    """Extrae el bundle en un directorio de trabajo y levanta su `docker-compose.yml`.

    El código generado nunca se ejecuta dentro del proceso de la plataforma: se
    materializa en un directorio propio por despliegue y se entrega a Docker, que lo
    aísla en sus contenedores.
    """

    def __init__(
        self,
        *,
        workspace: Path,
        base_port: int = 9100,
        host: str = "http://localhost",
        startup_timeout: int = 180,
    ) -> None:
        self._workspace = workspace
        self._base_port = base_port
        self._host = host.rstrip("/")
        self._startup_timeout = startup_timeout

    async def deploy(self, request: DeploymentRequest) -> DeploymentOutcome:
        target = self._workspace / request.deployment_id
        logs: list[str] = []

        try:
            self._extract(request.bundle, target)
            logs.append(f"Bundle extraído en {target}")

            root = self._compose_root(target)
            if root is None:
                return DeploymentOutcome(
                    url=None,
                    logs=tuple(logs),
                    error="El bundle no contiene un docker-compose.yml",
                )

            self._write_env(root, request.env)
            port = self._port_for(request.deployment_id)

            code, output = await self._compose(root, "up", "-d", "--build", port=port)
            logs.extend(output.splitlines()[-40:])
            if code != 0:
                return DeploymentOutcome(
                    url=None, logs=tuple(logs), error=f"docker compose up falló (código {code})"
                )

            url = f"{self._host}:{port}"
            if not await self._wait_healthy(url):
                return DeploymentOutcome(
                    url=None,
                    logs=tuple(logs),
                    error="El servicio no respondió a la sonda de vida a tiempo",
                )

            logs.append(f"Servicio disponible en {url}")
            return DeploymentOutcome(
                url=url,
                image_tag=f"{request.project_slug}:{request.deployment_id[:8]}",
                logs=tuple(logs),
            )
        except Exception as exc:
            logger.exception("Fallo desplegando %s", request.deployment_id)
            return DeploymentOutcome(url=None, logs=tuple(logs), error=str(exc))

    async def stop(self, deployment_id: str) -> None:
        root = self._compose_root(self._workspace / deployment_id)
        if root is not None:
            await self._compose(root, "down", "-v")

    # ── Interno ───────────────────────────────────────────────────────────────

    def _extract(self, bundle: bytes, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            for member in archive.namelist():
                # Defensa frente a rutas maliciosas dentro del ZIP.
                destination = (target / member).resolve()
                if not str(destination).startswith(str(target.resolve())):
                    raise ValueError(f"Ruta insegura en el bundle: {member}")
            archive.extractall(target)

    def _compose_root(self, target: Path) -> Path | None:
        if not target.exists():
            return None
        for candidate in sorted(target.rglob("docker-compose.yml")):
            return candidate.parent
        return None

    def _write_env(self, root: Path, env: dict[str, str]) -> None:
        example = root / ".env.example"
        lines = example.read_text(encoding="utf-8").splitlines() if example.exists() else []
        overrides = {key: value for key, value in env.items() if value}
        merged: list[str] = []
        for line in lines:
            key = line.split("=", 1)[0].strip()
            merged.append(f"{key}={overrides.pop(key)}" if key in overrides else line)
        merged.extend(f"{key}={value}" for key, value in overrides.items())
        (root / ".env").write_text("\n".join(merged) + "\n", encoding="utf-8")

    def _port_for(self, deployment_id: str) -> int:
        """Puerto estable por despliegue, derivado de su identificador."""
        return self._base_port + (abs(hash(deployment_id)) % 400)

    async def _compose(self, root: Path, *args: str, port: int | None = None) -> tuple[int, str]:
        env_extra = {"BACKEND_PORT": str(port)} if port else {}
        process = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            *args,
            cwd=str(root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**env_extra},
        )
        stdout, _ = await process.communicate()
        return process.returncode or 0, stdout.decode("utf-8", errors="replace")

    async def _wait_healthy(self, url: str) -> bool:
        import httpx

        deadline = asyncio.get_running_loop().time() + self._startup_timeout
        async with httpx.AsyncClient(timeout=5.0) as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    response = await client.get(f"{url}/health")
                    if response.status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(3)
        return False
