"""Cola en memoria: pruebas y ejecución en un solo proceso."""

from __future__ import annotations

import asyncio
import contextlib

from factory.application.ports.queue import Job


class InMemoryJobQueue:
    """Implementación de `JobQueue` sin dependencias externas."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._in_flight: dict[str, Job] = {}
        self.processed: list[Job] = []

    async def enqueue(self, job: Job) -> None:
        await self._queue.put(job)

    async def reserve(self, *, timeout_seconds: int = 5) -> Job | None:
        try:
            job = await asyncio.wait_for(self._queue.get(), timeout=timeout_seconds)
        except TimeoutError:
            return None
        self._in_flight[job.id] = job
        return job

    async def acknowledge(self, job: Job) -> None:
        self._in_flight.pop(job.id, None)
        self.processed.append(job)

    async def release(self, job: Job) -> None:
        self._in_flight.pop(job.id, None)
        retried = job.retried()
        if not retried.exhausted:
            await self._queue.put(retried)

    async def size(self) -> int:
        return self._queue.qsize()

    async def drain(self) -> list[Job]:
        """Vacía la cola y devuelve lo pendiente. Solo para pruebas."""
        jobs: list[Job] = []
        while not self._queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                jobs.append(self._queue.get_nowait())
        return jobs
