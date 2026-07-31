"""Bus de eventos en memoria: pruebas y despliegue de un solo proceso."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from factory.domain.events import DomainEvent


class InMemoryEventBus:
    """Reparte los eventos a los suscriptores vivos del mismo proceso."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self.published: list[DomainEvent] = []

    async def publish(self, event: DomainEvent) -> None:
        self.published.append(event)
        payload = event.as_dict()
        for queue in self._subscribers.get(event.project_id, []):
            queue.put_nowait(payload)

    async def subscribe(self, project_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(project_id, []).append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            listeners = self._subscribers.get(project_id, [])
            if queue in listeners:
                listeners.remove(queue)

    def events_for(self, project_id: str) -> list[DomainEvent]:
        """Historial publicado para un proyecto. Solo para pruebas."""
        return [event for event in self.published if event.project_id == project_id]
