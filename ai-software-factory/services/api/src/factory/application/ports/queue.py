"""Puerto de la cola de trabajos largos (construcción y despliegue)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from factory.domain.value_objects import new_id, utcnow


@dataclass(frozen=True, slots=True)
class Job:
    """Unidad de trabajo encolada."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    attempts: int = 0
    max_attempts: int = 3

    def retried(self) -> Job:
        """Copia del trabajo con un intento más consumido."""
        return Job(
            kind=self.kind,
            payload=self.payload,
            id=self.id,
            attempts=self.attempts + 1,
            max_attempts=self.max_attempts,
        )

    @property
    def exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "payload": self.payload,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "enqueued_at": utcnow().isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        return cls(
            kind=str(data["kind"]),
            payload=dict(data.get("payload") or {}),
            id=str(data.get("id") or new_id()),
            attempts=int(data.get("attempts") or 0),
            max_attempts=int(data.get("max_attempts") or 3),
        )


@runtime_checkable
class JobQueue(Protocol):
    """Cola con reclamación: el trabajo no se pierde si el worker muere."""

    async def enqueue(self, job: Job) -> None:
        """Encola un trabajo para su ejecución asíncrona."""
        ...

    async def reserve(self, *, timeout_seconds: int = 5) -> Job | None:
        """Reclama un trabajo bloqueando como mucho `timeout_seconds`."""
        ...

    async def acknowledge(self, job: Job) -> None:
        """Confirma que el trabajo terminó y lo retira definitivamente."""
        ...

    async def release(self, job: Job) -> None:
        """Devuelve el trabajo a la cola para reintentarlo."""
        ...

    async def size(self) -> int:
        """Trabajos pendientes de reclamar."""
        ...
