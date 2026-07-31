"""Eventos de dominio. Alimentan el WebSocket de progreso y la auditoría."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from factory.domain.value_objects import new_id, utcnow


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Evento base: qué pasó, sobre qué proyecto y cuándo."""

    project_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    occurred_at: datetime = field(default_factory=utcnow)

    @property
    def name(self) -> str:
        """Nombre estable del evento, usado como tipo en el canal de eventos."""
        return _event_name(type(self))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event": self.name,
            "project_id": self.project_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
        }


def _event_name(cls: type) -> str:
    """`BuildStageStarted` → `build.stage_started`."""
    return _EVENT_NAMES.get(cls.__name__, cls.__name__)


@dataclass(frozen=True, slots=True)
class ProjectCreated(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class RequirementsCaptured(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ClarificationRequested(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class SpecificationReady(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildQueued(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildStarted(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildStageStarted(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildStageCompleted(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildProgressed(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildSucceeded(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class BuildFailed(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentStarted(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentSucceeded(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentFailed(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ModuleInstalled(DomainEvent):
    pass


@dataclass(frozen=True, slots=True)
class ModuleRemoved(DomainEvent):
    pass


_EVENT_NAMES: dict[str, str] = {
    "DomainEvent": "domain.event",
    "ProjectCreated": "project.created",
    "RequirementsCaptured": "requirements.captured",
    "ClarificationRequested": "requirements.clarification_requested",
    "SpecificationReady": "specification.ready",
    "BuildQueued": "build.queued",
    "BuildStarted": "build.started",
    "BuildStageStarted": "build.stage_started",
    "BuildStageCompleted": "build.stage_completed",
    "BuildProgressed": "build.progressed",
    "BuildSucceeded": "build.succeeded",
    "BuildFailed": "build.failed",
    "DeploymentStarted": "deployment.started",
    "DeploymentSucceeded": "deployment.succeeded",
    "DeploymentFailed": "deployment.failed",
    "ModuleInstalled": "module.installed",
    "ModuleRemoved": "module.removed",
}
