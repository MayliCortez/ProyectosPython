"""Orquestador: ejecuta el pipeline de agentes y emite el progreso."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum

from factory.agents.base import AgentContext, AgentResult
from factory.agents.pipeline import Pipeline, PipelineStage
from factory.agents.registry import AgentRegistry
from factory.domain.entities import Build, BuildStage, Conversation, Project, StageStatus
from factory.domain.errors import AgentExecutionError
from factory.domain.events import (
    BuildFailed,
    BuildStageCompleted,
    BuildStageStarted,
    BuildStarted,
    BuildSucceeded,
    ClarificationRequested,
    DomainEvent,
)

logger = logging.getLogger(__name__)

#: Publicador de eventos hacia el bus de progreso.
EventEmitter = Callable[[DomainEvent], Awaitable[None]]


async def _discard(_: DomainEvent) -> None:
    """Emisor nulo, para ejecuciones sin observadores."""


class _LevelOutcome(IntEnum):
    """Cómo terminó un nivel del pipeline, ordenado por gravedad."""

    CONTINUE = 0
    HALT_FOR_CLARIFICATION = 1
    FAIL = 2


@dataclass(slots=True)
class PipelineReport:
    """Resultado de una ejecución completa del pipeline."""

    build: Build
    context: AgentContext
    succeeded: bool = False
    failed_stage: str | None = None
    error: str | None = None
    awaiting_clarification: bool = False
    skipped: list[str] = field(default_factory=list)

    @property
    def artifact_count(self) -> int:
        return len(self.context.artifacts)


class Orchestrator:
    """Coordina a los agentes sin que ninguno conozca a los demás.

    Responsabilidades: validar el pipeline, ejecutar cada nivel (en paralelo cuando
    las dependencias lo permiten), mantener el estado del `Build` y publicar eventos
    de progreso. Cualquier fallo de una etapa obligatoria detiene la construcción y la
    marca como fallida; las etapas opcionales solo se saltan.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        pipeline: Pipeline,
        *,
        emit: EventEmitter = _discard,
    ) -> None:
        self._registry = registry
        self._pipeline = pipeline
        self._emit = emit
        pipeline.validate(registry)

    async def run(
        self,
        *,
        project: Project,
        conversation: Conversation,
        build: Build,
        context: AgentContext,
    ) -> PipelineReport:
        """Ejecuta el pipeline completo sobre un build ya persistido en estado `queued`."""
        report = PipelineReport(build=build, context=context)
        self._prepare_stages(build)

        build.start()
        await self._emit(BuildStarted(project_id=project.id, payload={"build_id": build.id}))

        for level in self._pipeline.execution_levels(self._registry):
            outcome = await self._run_level(level, build, context, report)
            if outcome is not _LevelOutcome.CONTINUE:
                if outcome is _LevelOutcome.HALT_FOR_CLARIFICATION:
                    return await self._halt_for_clarification(project, build, conversation, report)
                return await self._fail(project, build, report)

        build.add_artifacts(list(context.artifacts.values()))
        build.succeed()
        report.succeeded = True
        await self._emit(
            BuildSucceeded(
                project_id=project.id,
                payload={
                    "build_id": build.id,
                    "artifacts": len(build.artifacts),
                    "bytes": build.total_bytes,
                },
            )
        )
        return report

    # ── Ejecución por niveles ─────────────────────────────────────────────────

    async def _run_level(
        self,
        level: list[PipelineStage],
        build: Build,
        context: AgentContext,
        report: PipelineReport,
    ) -> _LevelOutcome:
        for stage in level:
            build.stage(stage.name).start()
            await self._emit(
                BuildStageStarted(
                    project_id=context.project.id,
                    payload={
                        "build_id": build.id,
                        "stage": stage.name,
                        "agent": stage.agent_key,
                        "progress": build.progress,
                    },
                )
            )

        results = await asyncio.gather(
            *(self._run_stage(stage, context) for stage in level),
            return_exceptions=True,
        )

        outcome = _LevelOutcome.CONTINUE
        for stage, result in zip(level, results, strict=True):
            build_stage = build.stage(stage.name)

            if isinstance(result, BaseException):
                stage_outcome = self._handle_failure(stage, build_stage, result, report)
                outcome = _worst(outcome, stage_outcome)
                continue

            result.merge_into(context)
            build_stage.logs.extend(result.logs)
            build_stage.succeed()

        # Los productos se vuelcan antes de comprobar la puerta de aclaración,
        # para que las preguntas registradas por el analista sean visibles.
        if outcome is _LevelOutcome.CONTINUE and context.conversation.has_blocking_questions:
            outcome = _LevelOutcome.HALT_FOR_CLARIFICATION

        for stage in level:
            build_stage = build.stage(stage.name)
            if build_stage.status is StageStatus.SUCCEEDED:
                await self._emit(
                    BuildStageCompleted(
                        project_id=context.project.id,
                        payload={
                            "build_id": build.id,
                            "stage": stage.name,
                            "progress": build.progress,
                            "duration_seconds": build_stage.duration_seconds,
                        },
                    )
                )
        return outcome

    async def _run_stage(self, stage: PipelineStage, context: AgentContext) -> AgentResult:
        agent = self._registry.get(stage.agent_key)
        logger.info("Ejecutando etapa %s con el agente %s", stage.name, agent.key)
        return await agent.execute(context)

    def _handle_failure(
        self,
        stage: PipelineStage,
        build_stage: BuildStage,
        error: BaseException,
        report: PipelineReport,
    ) -> _LevelOutcome:
        message = (
            error.message if isinstance(error, AgentExecutionError) else str(error) or repr(error)
        )
        if stage.optional:
            build_stage.skip(f"etapa opcional omitida: {message}")
            report.skipped.append(stage.name)
            logger.warning("Etapa opcional %s omitida: %s", stage.name, message)
            return _LevelOutcome.CONTINUE

        build_stage.fail(message)
        report.failed_stage = stage.name
        report.error = message
        logger.error("La etapa %s ha fallado: %s", stage.name, message)
        return _LevelOutcome.FAIL

    # ── Finales ───────────────────────────────────────────────────────────────

    async def _fail(self, project: Project, build: Build, report: PipelineReport) -> PipelineReport:
        error = report.error or "fallo desconocido"
        for stage in build.stages:
            if stage.status is StageStatus.PENDING:
                stage.skip("no ejecutada por un fallo previo")
        build.fail(error)
        await self._emit(
            BuildFailed(
                project_id=project.id,
                payload={"build_id": build.id, "stage": report.failed_stage, "error": error},
            )
        )
        return report

    async def _halt_for_clarification(
        self,
        project: Project,
        build: Build,
        conversation: Conversation,
        report: PipelineReport,
    ) -> PipelineReport:
        """Pausa limpia: faltan respuestas del usuario, no es un error del sistema."""
        questions = [
            {"id": question.id, "text": question.text, "options": list(question.options)}
            for question in conversation.pending_questions
        ]
        for stage in build.stages:
            if stage.status is StageStatus.PENDING:
                stage.skip("a la espera de respuestas del usuario")
        build.cancel()
        report.awaiting_clarification = True
        await self._emit(
            ClarificationRequested(
                project_id=project.id,
                payload={"build_id": build.id, "questions": questions},
            )
        )
        return report

    def _prepare_stages(self, build: Build) -> None:
        """Refleja el pipeline en el build para que el panel vea todas las etapas."""
        build.stages = [
            BuildStage(name=stage.name, agent=stage.agent_key) for stage in self._pipeline.stages
        ]


def _worst(left: _LevelOutcome, right: _LevelOutcome) -> _LevelOutcome:
    """El resultado de un nivel es el peor de los resultados de sus etapas."""
    return left if left.value >= right.value else right
