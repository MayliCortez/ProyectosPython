"""Worker de trabajos largos: construcción y despliegue de proyectos.

Se ejecuta como proceso independiente (`python -m factory.infrastructure.queue.worker`)
y escala horizontalmente: cada réplica reclama trabajos de la misma cola, de modo que
añadir workers aumenta linealmente los proyectos que se pueden construir a la vez.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from factory.application.ports.queue import Job
from factory.application.services.build_service import BUILD_JOB
from factory.application.services.deployment_service import DEPLOY_JOB
from factory.config import get_settings
from factory.container import Container, build_container

logger = logging.getLogger(__name__)


class Worker:
    """Bucle de reclamación y ejecución con reintentos acotados."""

    def __init__(self, container: Container, *, concurrency: int = 4) -> None:
        self._container = container
        self._concurrency = max(1, concurrency)
        self._stopping = asyncio.Event()
        self._running: set[asyncio.Task[None]] = set()

    def request_stop(self) -> None:
        """Deja de reclamar trabajos nuevos; los que están en curso terminan."""
        logger.info("Parada solicitada; se espera a los trabajos en curso")
        self._stopping.set()

    async def run(self) -> None:
        logger.info("Worker iniciado con concurrencia %s", self._concurrency)
        queue = self._container.queue

        recover = getattr(queue, "recover_stale", None)
        if recover is not None:
            recovered = await recover()
            if recovered:
                logger.warning("Se han recuperado %s trabajo(s) huérfanos", recovered)

        while not self._stopping.is_set():
            if len(self._running) >= self._concurrency:
                await asyncio.sleep(0.1)
                continue

            job = await queue.reserve(timeout_seconds=5)
            if job is None:
                continue

            task = asyncio.create_task(self._process(job))
            self._running.add(task)
            task.add_done_callback(self._running.discard)

        if self._running:
            await asyncio.gather(*self._running, return_exceptions=True)
        logger.info("Worker detenido")

    async def _process(self, job: Job) -> None:
        logger.info("Procesando trabajo %s (%s)", job.id, job.kind)
        try:
            await self._dispatch(job)
        except Exception:
            logger.exception("El trabajo %s (%s) ha fallado", job.id, job.kind)
            await self._container.queue.release(job)
            return
        await self._container.queue.acknowledge(job)
        logger.info("Trabajo %s completado", job.id)

    async def _dispatch(self, job: Job) -> None:
        if job.kind == BUILD_JOB:
            await self._container.builds.execute_build(
                project_id=str(job.payload["project_id"]),
                build_id=str(job.payload["build_id"]),
            )
        elif job.kind == DEPLOY_JOB:
            await self._container.deployments.execute_deployment(
                project_id=str(job.payload["project_id"]),
                deployment_id=str(job.payload["deployment_id"]),
            )
        else:
            logger.error("Tipo de trabajo desconocido: %s", job.kind)


async def main() -> None:
    """Punto de entrada del proceso worker."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    container = await build_container(settings)
    worker = Worker(container, concurrency=settings.worker_concurrency)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.request_stop)

    try:
        await worker.run()
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
