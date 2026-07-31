"""Bus de eventos sobre Redis pub/sub.

Es lo que desacopla al worker del proceso que atiende el WebSocket: el worker publica
en el canal del proyecto y cualquier réplica de la API suscrita lo recibe.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from factory.domain.events import DomainEvent

logger = logging.getLogger(__name__)


class RedisEventBus:
    """Publicación y suscripción por proyecto."""

    def __init__(self, redis: Redis, *, prefix: str = "factory:events") -> None:
        self._redis = redis
        self._prefix = prefix

    def _channel(self, project_id: str) -> str:
        return f"{self._prefix}:{project_id}"

    async def publish(self, event: DomainEvent) -> None:
        await self._redis.publish(self._channel(event.project_id), json.dumps(event.as_dict()))

    async def subscribe(self, project_id: str) -> AsyncIterator[dict[str, object]]:
        """Itera los eventos del proyecto hasta que el consumidor abandone el bucle."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(project_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    yield json.loads(message["data"])
                except (TypeError, ValueError):
                    logger.warning("Evento no analizable en el canal %s", project_id)
        finally:
            await pubsub.unsubscribe(self._channel(project_id))
            await pubsub.aclose()
