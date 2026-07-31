"""Objetos de transferencia entre la capa de aplicación y las interfaces.

Mantienen a FastAPI fuera del dominio: los servicios devuelven DTOs planos y los
routers los serializan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from factory.domain.entities import (
    Build,
    Conversation,
    Deployment,
    ModuleInstallation,
    Project,
)
from factory.domain.entities.specification import RequirementsDocument, Specification


@dataclass(frozen=True, slots=True)
class ProjectView:
    id: str
    name: str
    slug: str
    status: str
    business_domain: str
    prompt: str
    modules: list[str]
    tech_stack: dict[str, str]
    live_url: str | None
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, project: Project) -> ProjectView:
        return cls(
            id=project.id,
            name=project.name,
            slug=str(project.slug),
            status=str(project.status),
            business_domain=str(project.business_domain),
            prompt=project.prompt,
            modules=list(project.module_keys),
            tech_stack=project.tech_stack.as_dict(),
            live_url=project.live_url,
            created_at=project.created_at.isoformat(),
            updated_at=project.updated_at.isoformat(),
        )


@dataclass(frozen=True, slots=True)
class QuestionView:
    id: str
    text: str
    rationale: str
    options: list[str]
    required: bool


@dataclass(frozen=True, slots=True)
class MessageView:
    id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConversationView:
    id: str
    project_id: str
    messages: list[MessageView]
    pending_questions: list[QuestionView]
    answers: dict[str, str]

    @classmethod
    def of(cls, conversation: Conversation) -> ConversationView:
        return cls(
            id=conversation.id,
            project_id=conversation.project_id,
            messages=[
                MessageView(
                    id=message.id,
                    role=str(message.role),
                    content=message.content,
                    created_at=message.created_at.isoformat(),
                    metadata=message.metadata,
                )
                for message in conversation.messages
            ],
            pending_questions=[
                QuestionView(
                    id=question.id,
                    text=question.text,
                    rationale=question.rationale,
                    options=list(question.options),
                    required=question.required,
                )
                for question in conversation.pending_questions
            ],
            answers=dict(conversation.answers),
        )


@dataclass(frozen=True, slots=True)
class StageView:
    name: str
    agent: str
    status: str
    error: str | None
    duration_seconds: float | None
    logs: list[str]


@dataclass(frozen=True, slots=True)
class BuildView:
    id: str
    project_id: str
    status: str
    progress: float
    stages: list[StageView]
    artifact_count: int
    total_bytes: int
    bundle_key: str | None
    error: str | None
    created_at: str

    @classmethod
    def of(cls, build: Build) -> BuildView:
        return cls(
            id=build.id,
            project_id=build.project_id,
            status=str(build.status),
            progress=build.progress,
            stages=[
                StageView(
                    name=stage.name,
                    agent=stage.agent,
                    status=str(stage.status),
                    error=stage.error,
                    duration_seconds=stage.duration_seconds,
                    logs=list(stage.logs),
                )
                for stage in build.stages
            ],
            artifact_count=len(build.artifacts),
            total_bytes=build.total_bytes,
            bundle_key=build.bundle_key,
            error=build.error,
            created_at=build.created_at.isoformat(),
        )


@dataclass(frozen=True, slots=True)
class DeploymentView:
    id: str
    project_id: str
    build_id: str
    provider: str
    status: str
    url: str | None
    error: str | None
    logs: list[str]
    created_at: str

    @classmethod
    def of(cls, deployment: Deployment) -> DeploymentView:
        return cls(
            id=deployment.id,
            project_id=deployment.project_id,
            build_id=deployment.build_id,
            provider=str(deployment.provider),
            status=str(deployment.status),
            url=deployment.url,
            error=deployment.error,
            logs=list(deployment.logs),
            created_at=deployment.created_at.isoformat(),
        )


@dataclass(frozen=True, slots=True)
class ModuleInstallationView:
    module_key: str
    version: str
    state: str
    config: dict[str, Any]

    @classmethod
    def of(cls, installation: ModuleInstallation) -> ModuleInstallationView:
        return cls(
            module_key=installation.module_key,
            version=str(installation.version),
            state=str(installation.state),
            config=dict(installation.config),
        )


@dataclass(frozen=True, slots=True)
class SpecificationView:
    id: str
    project_id: str
    version: int
    tech_stack: dict[str, str]
    entities: list[dict[str, Any]]
    endpoints: list[dict[str, Any]]
    modules: list[str]
    pages: list[str]

    @classmethod
    def of(cls, specification: Specification) -> SpecificationView:
        return cls(
            id=specification.id,
            project_id=specification.project_id,
            version=specification.version,
            tech_stack=specification.tech_stack.as_dict(),
            entities=[
                {
                    "name": entity.name,
                    "table": entity.table_name,
                    "description": entity.description,
                    "fields": [asdict(f) for f in entity.fields],
                }
                for entity in specification.entities
            ],
            endpoints=[asdict(endpoint) for endpoint in specification.endpoints],
            modules=list(specification.modules),
            pages=list(specification.pages),
        )


@dataclass(frozen=True, slots=True)
class RequirementsView:
    id: str
    project_id: str
    summary: str
    business_domain: str
    markdown: str
    suggested_modules: list[str]

    @classmethod
    def of(cls, requirements: RequirementsDocument) -> RequirementsView:
        return cls(
            id=requirements.id,
            project_id=requirements.project_id,
            summary=requirements.summary,
            business_domain=str(requirements.business_domain),
            markdown=requirements.to_markdown(),
            suggested_modules=list(requirements.suggested_modules),
        )
