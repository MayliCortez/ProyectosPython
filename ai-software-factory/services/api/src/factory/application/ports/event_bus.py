"""Puerto del bus de eventos que alimenta el progreso en tiempo real."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from factory.domain.events import DomainEvent


@runtime_checkable
class EventBus(Protocol):
    """Publicación/suscripción por proyecto.

    Es lo que permite que un WebSocket abierto contra cualquier réplica de la API
    reciba el progreso emitido por un worker en otro nodo.
    """

    async def publish(self, event: DomainEvent) -> None:
        """Emite un evento al canal del proyecto."""
        ...

    def subscribe(self, project_id: str) -> AsyncIterator[dict[str, object]]:
        """Itera los eventos del proyecto hasta que el consumidor cierre el flujo."""
        ...
