"""Cola de trabajos sobre Redis con reclamación y reintentos."""

from __future__ import annotations

import json
import logging

from redis.asyncio import Redis

from factory.application.ports.queue import Job

logger = logging.getLogger(__name__)


class RedisJobQueue:
    """Cola FIFO con lista de trabajos en curso.

    `reserve` mueve el trabajo de la cola pendiente a la de procesamiento de forma
    atómica (`BLMOVE`). Si el worker muere sin confirmar, el trabajo sigue en la lista
    de procesamiento y `recover_stale` lo devuelve a la cola: ningún trabajo se pierde
    por una caída.
    """

    def __init__(self, redis: Redis, *, name: str = "factory:jobs") -> None:
        self._redis = redis
        self._pending = name
        self._processing = f"{name}:processing"

    async def enqueue(self, job: Job) -> None:
        await self._redis.lpush(self._pending, json.dumps(job.as_dict()))
        logger.info("Trabajo %s (%s) encolado", job.id, job.kind)

    async def reserve(self, *, timeout_seconds: int = 5) -> Job | None:
        raw = await self._redis.blmove(
            self._pending, self._processing, timeout=timeout_seconds, src="RIGHT", dest="LEFT"
        )
        if raw is None:
            return None
        return Job.from_dict(json.loads(raw))

    async def acknowledge(self, job: Job) -> None:
        await self._redis.lrem(self._processing, 1, json.dumps(job.as_dict()))

    async def release(self, job: Job) -> None:
        """Devuelve el trabajo a la cola con un intento más, o lo descarta si se agotó."""
        await self.acknowledge(job)
        retried = job.retried()
        if retried.exhausted:
            logger.error(
                "Trabajo %s (%s) descartado tras %s intentos", job.id, job.kind, retried.attempts
            )
            return
        await self._redis.lpush(self._pending, json.dumps(retried.as_dict()))

    async def size(self) -> int:
        return int(await self._redis.llen(self._pending))

    async def recover_stale(self) -> int:
        """Reencola lo que quedó en procesamiento por una caída del worker."""
        recovered = 0
        while True:
            raw = await self._redis.rpoplpush(self._processing, self._pending)
            if raw is None:
                return recovered
            recovered += 1
            logger.warning("Trabajo recuperado de la cola de procesamiento")
