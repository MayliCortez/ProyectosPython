"""Construcción: la ejecución del pipeline de agentes sobre un proyecto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from factory.domain.errors import InvalidTransitionError, ValidationError
from factory.domain.value_objects import Artifact, new_id, utcnow


class BuildStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


_TERMINAL_BUILD = {BuildStatus.SUCCEEDED, BuildStatus.FAILED, BuildStatus.CANCELLED}


@dataclass(slots=True)
class BuildStage:
    """Etapa del pipeline, correspondiente a un agente."""

    name: str
    agent: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.status = StageStatus.RUNNING
        self.started_at = utcnow()

    def succeed(self) -> None:
        self.status = StageStatus.SUCCEEDED
        self.finished_at = utcnow()

    def fail(self, error: str) -> None:
        self.status = StageStatus.FAILED
        self.finished_at = utcnow()
        self.error = error

    def skip(self, reason: str = "") -> None:
        self.status = StageStatus.SKIPPED
        self.finished_at = utcnow()
        if reason:
            self.logs.append(reason)

    def log(self, line: str) -> None:
        self.logs.append(line)

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at or not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()


@dataclass(slots=True)
class Build:
    """Una ejecución del pipeline: sus etapas, su progreso y sus artefactos."""

    project_id: str
    specification_id: str | None = None
    stages: list[BuildStage] = field(default_factory=list)
    status: BuildStatus = BuildStatus.QUEUED
    artifacts: list[Artifact] = field(default_factory=list)
    bundle_key: str | None = None
    error: str | None = None
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # ── Progreso ──────────────────────────────────────────────────────────────

    @property
    def progress(self) -> float:
        """Fracción de etapas resueltas, entre 0.0 y 1.0."""
        if not self.stages:
            return 0.0
        done = sum(
            1
            for stage in self.stages
            if stage.status in {StageStatus.SUCCEEDED, StageStatus.SKIPPED}
        )
        return round(done / len(self.stages), 4)

    @property
    def current_stage(self) -> BuildStage | None:
        return next((s for s in self.stages if s.status is StageStatus.RUNNING), None)

    def stage(self, name: str) -> BuildStage:
        found = next((s for s in self.stages if s.name == name), None)
        if found is None:
            raise ValidationError(f"La construcción no tiene la etapa {name!r}")
        return found

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if self.status is not BuildStatus.QUEUED:
            raise InvalidTransitionError("Build", self.status, BuildStatus.RUNNING)
        self.status = BuildStatus.RUNNING
        self.started_at = utcnow()

    def succeed(self, *, bundle_key: str | None = None) -> None:
        if self.status is not BuildStatus.RUNNING:
            raise InvalidTransitionError("Build", self.status, BuildStatus.SUCCEEDED)
        self.status = BuildStatus.SUCCEEDED
        self.bundle_key = bundle_key
        self.finished_at = utcnow()

    def fail(self, error: str) -> None:
        if self.status in _TERMINAL_BUILD:
            raise InvalidTransitionError("Build", self.status, BuildStatus.FAILED)
        self.status = BuildStatus.FAILED
        self.error = error
        self.finished_at = utcnow()

    def cancel(self) -> None:
        if self.status in _TERMINAL_BUILD:
            raise InvalidTransitionError("Build", self.status, BuildStatus.CANCELLED)
        self.status = BuildStatus.CANCELLED
        self.finished_at = utcnow()
        for stage in self.stages:
            if stage.status in {StageStatus.PENDING, StageStatus.RUNNING}:
                stage.skip("cancelada")

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_BUILD

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at or not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()

    # ── Artefactos ────────────────────────────────────────────────────────────

    def add_artifacts(self, artifacts: list[Artifact]) -> None:
        """Añade artefactos; los de igual ruta sustituyen a los anteriores."""
        by_path = {artifact.path: artifact for artifact in self.artifacts}
        for artifact in artifacts:
            by_path[artifact.path] = artifact
        self.artifacts = list(by_path.values())

    @property
    def total_bytes(self) -> int:
        return sum(artifact.size_bytes for artifact in self.artifacts)
