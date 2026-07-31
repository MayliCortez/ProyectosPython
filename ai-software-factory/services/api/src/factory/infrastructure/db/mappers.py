"""Traducción entre filas ORM y entidades del dominio.

Se mantiene explícita (y no con un ORM que mapee directamente las entidades) para que
el dominio no herede de `Base` ni dependa de SQLAlchemy: puede evolucionar sin que la
forma de la tabla lo condicione, y viceversa.
"""

from __future__ import annotations

from typing import Any

from factory.domain.entities import (
    Build,
    BuildStage,
    BuildStatus,
    Conversation,
    Deployment,
    DeploymentProvider,
    DeploymentStatus,
    Message,
    MessageRole,
    ModuleInstallation,
    ModuleState,
    Organization,
    Project,
    ProjectStatus,
    StageStatus,
    User,
    UserRole,
)
from factory.domain.entities.specification import (
    DataEntity,
    DataField,
    Endpoint,
    RequirementsDocument,
    Specification,
    UserStory,
)
from factory.domain.value_objects import (
    Artifact,
    BusinessDomain,
    ClarifyingQuestion,
    Email,
    SemVer,
    Slug,
    TechStack,
)
from factory.infrastructure.db.models import (
    BuildRow,
    ConversationRow,
    DeploymentRow,
    MessageRow,
    ModuleInstallationRow,
    OrganizationRow,
    ProjectRow,
    RequirementsRow,
    SpecificationRow,
    UserRow,
)

# ── Organizaciones y usuarios ─────────────────────────────────────────────────


def organization_to_row(entity: Organization) -> OrganizationRow:
    return OrganizationRow(
        id=entity.id,
        name=entity.name,
        slug=str(entity.slug),
        max_projects=entity.max_projects,
    )


def organization_from_row(row: OrganizationRow) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        slug=Slug(row.slug),
        max_projects=row.max_projects,
        created_at=row.created_at,
    )


def user_to_row(entity: User) -> UserRow:
    return UserRow(
        id=entity.id,
        organization_id=entity.organization_id,
        email=str(entity.email),
        password_hash=entity.password_hash,
        full_name=entity.full_name,
        role=str(entity.role),
        is_active=entity.is_active,
    )


def user_from_row(row: UserRow) -> User:
    return User(
        id=row.id,
        organization_id=row.organization_id,
        email=Email(row.email),
        password_hash=row.password_hash,
        full_name=row.full_name,
        role=UserRole(row.role),
        is_active=row.is_active,
        created_at=row.created_at,
    )


# ── Proyectos ─────────────────────────────────────────────────────────────────


def project_to_row(entity: Project) -> ProjectRow:
    return ProjectRow(
        id=entity.id,
        organization_id=entity.organization_id,
        name=entity.name,
        slug=str(entity.slug),
        prompt=entity.prompt,
        business_domain=str(entity.business_domain),
        status=str(entity.status),
        tech_stack=entity.tech_stack.as_dict(),
        module_keys=list(entity.module_keys),
        live_url=entity.live_url,
        created_by=entity.created_by,
        updated_at=entity.updated_at,
    )


def apply_project(row: ProjectRow, entity: Project) -> None:
    """Vuelca la entidad sobre una fila ya cargada en la sesión."""
    row.name = entity.name
    row.slug = str(entity.slug)
    row.prompt = entity.prompt
    row.business_domain = str(entity.business_domain)
    row.status = str(entity.status)
    row.tech_stack = entity.tech_stack.as_dict()
    row.module_keys = list(entity.module_keys)
    row.live_url = entity.live_url
    row.updated_at = entity.updated_at


def project_from_row(row: ProjectRow) -> Project:
    return Project(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        slug=Slug(row.slug),
        prompt=row.prompt,
        business_domain=BusinessDomain(row.business_domain),
        status=ProjectStatus(row.status),
        tech_stack=TechStack(**(row.tech_stack or {})),
        module_keys=list(row.module_keys or []),
        live_url=row.live_url,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ── Conversaciones ────────────────────────────────────────────────────────────


def conversation_to_row(entity: Conversation) -> ConversationRow:
    return ConversationRow(
        id=entity.id,
        project_id=entity.project_id,
        pending_questions=[_question_to_dict(q) for q in entity.pending_questions],
        answers=dict(entity.answers),
        updated_at=entity.updated_at,
    )


def apply_conversation(row: ConversationRow, entity: Conversation) -> None:
    row.pending_questions = [_question_to_dict(q) for q in entity.pending_questions]
    row.answers = dict(entity.answers)
    row.updated_at = entity.updated_at


def conversation_from_row(row: ConversationRow, messages: list[MessageRow]) -> Conversation:
    return Conversation(
        id=row.id,
        project_id=row.project_id,
        messages=[message_from_row(message) for message in messages],
        pending_questions=[_question_from_dict(item) for item in (row.pending_questions or [])],
        answers=dict(row.answers or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def message_to_row(entity: Message) -> MessageRow:
    return MessageRow(
        id=entity.id,
        conversation_id=entity.conversation_id,
        role=str(entity.role),
        content=entity.content,
        message_metadata=dict(entity.metadata),
        created_at=entity.created_at,
    )


def message_from_row(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        metadata=dict(row.message_metadata or {}),
        created_at=row.created_at,
    )


def _question_to_dict(question: ClarifyingQuestion) -> dict[str, Any]:
    return {
        "id": question.id,
        "text": question.text,
        "rationale": question.rationale,
        "options": list(question.options),
        "required": question.required,
    }


def _question_from_dict(data: dict[str, Any]) -> ClarifyingQuestion:
    return ClarifyingQuestion(
        id=str(data["id"]),
        text=str(data["text"]),
        rationale=str(data.get("rationale", "")),
        options=tuple(data.get("options", ())),
        required=bool(data.get("required", True)),
    )


# ── Requisitos y especificación ───────────────────────────────────────────────


def requirements_to_row(entity: RequirementsDocument) -> RequirementsRow:
    return RequirementsRow(
        id=entity.id,
        project_id=entity.project_id,
        summary=entity.summary,
        business_domain=str(entity.business_domain),
        stories=[
            {
                "id": story.id,
                "role": story.role,
                "goal": story.goal,
                "benefit": story.benefit,
                "acceptance_criteria": list(story.acceptance_criteria),
                "priority": story.priority,
            }
            for story in entity.stories
        ],
        constraints=list(entity.constraints),
        out_of_scope=list(entity.out_of_scope),
        suggested_modules=list(entity.suggested_modules),
    )


def requirements_from_row(row: RequirementsRow) -> RequirementsDocument:
    return RequirementsDocument(
        id=row.id,
        project_id=row.project_id,
        summary=row.summary,
        business_domain=BusinessDomain(row.business_domain),
        stories=[
            UserStory(
                id=str(item["id"]),
                role=str(item["role"]),
                goal=str(item["goal"]),
                benefit=str(item.get("benefit", "")),
                acceptance_criteria=tuple(item.get("acceptance_criteria", ())),
                priority=int(item.get("priority", 2)),
            )
            for item in (row.stories or [])
        ],
        constraints=list(row.constraints or []),
        out_of_scope=list(row.out_of_scope or []),
        suggested_modules=list(row.suggested_modules or []),
        created_at=row.created_at,
    )


def specification_to_row(entity: Specification) -> SpecificationRow:
    return SpecificationRow(
        id=entity.id,
        project_id=entity.project_id,
        requirements_id=entity.requirements_id,
        version=entity.version,
        tech_stack=entity.tech_stack.as_dict(),
        entities=[
            {
                "name": data_entity.name,
                "description": data_entity.description,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.type,
                        "required": f.required,
                        "unique": f.unique,
                        "references": f.references,
                        "description": f.description,
                    }
                    for f in data_entity.fields
                ],
            }
            for data_entity in entity.entities
        ],
        endpoints=[
            {
                "method": endpoint.method,
                "path": endpoint.path,
                "summary": endpoint.summary,
                "entity": endpoint.entity,
                "auth_required": endpoint.auth_required,
            }
            for endpoint in entity.endpoints
        ],
        modules=list(entity.modules),
        pages=list(entity.pages),
        notes=dict(entity.notes),
    )


def specification_from_row(row: SpecificationRow) -> Specification:
    return Specification(
        id=row.id,
        project_id=row.project_id,
        requirements_id=row.requirements_id,
        version=row.version,
        tech_stack=TechStack(**(row.tech_stack or {})),
        entities=[
            DataEntity(
                name=str(item["name"]),
                description=str(item.get("description", "")),
                fields=tuple(
                    DataField(
                        name=str(f["name"]),
                        type=str(f.get("type", "string")),
                        required=bool(f.get("required", True)),
                        unique=bool(f.get("unique", False)),
                        references=f.get("references"),
                        description=str(f.get("description", "")),
                    )
                    for f in item.get("fields", [])
                ),
            )
            for item in (row.entities or [])
        ],
        endpoints=[
            Endpoint(
                method=str(item["method"]),
                path=str(item["path"]),
                summary=str(item.get("summary", "")),
                entity=item.get("entity"),
                auth_required=bool(item.get("auth_required", True)),
            )
            for item in (row.endpoints or [])
        ],
        modules=list(row.modules or []),
        pages=list(row.pages or []),
        notes=dict(row.notes or {}),
        created_at=row.created_at,
    )


# ── Construcciones ────────────────────────────────────────────────────────────


def build_to_row(entity: Build) -> BuildRow:
    row = BuildRow(
        id=entity.id,
        project_id=entity.project_id,
        specification_id=entity.specification_id,
    )
    apply_build(row, entity)
    return row


def apply_build(row: BuildRow, entity: Build) -> None:
    row.status = str(entity.status)
    row.progress = entity.progress
    row.specification_id = entity.specification_id
    row.stages = [_stage_to_dict(stage) for stage in entity.stages]
    # Solo el inventario: el contenido vive en el bundle de S3, no en la base de datos.
    row.artifacts = [
        {"path": artifact.path, "language": artifact.language, "size": artifact.size_bytes}
        for artifact in entity.artifacts
    ]
    row.bundle_key = entity.bundle_key
    row.error = entity.error
    row.started_at = entity.started_at
    row.finished_at = entity.finished_at


def build_from_row(row: BuildRow) -> Build:
    return Build(
        id=row.id,
        project_id=row.project_id,
        specification_id=row.specification_id,
        status=BuildStatus(row.status),
        stages=[_stage_from_dict(item) for item in (row.stages or [])],
        artifacts=[
            Artifact(path=str(item["path"]), content="", language=str(item.get("language", "text")))
            for item in (row.artifacts or [])
        ],
        bundle_key=row.bundle_key,
        error=row.error,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _stage_to_dict(stage: BuildStage) -> dict[str, Any]:
    return {
        "name": stage.name,
        "agent": stage.agent,
        "status": str(stage.status),
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "finished_at": stage.finished_at.isoformat() if stage.finished_at else None,
        "error": stage.error,
        "logs": list(stage.logs),
    }


def _stage_from_dict(data: dict[str, Any]) -> BuildStage:
    from datetime import datetime

    def parse(value: Any) -> Any:
        return datetime.fromisoformat(value) if value else None

    return BuildStage(
        name=str(data["name"]),
        agent=str(data["agent"]),
        status=StageStatus(data.get("status", "pending")),
        started_at=parse(data.get("started_at")),
        finished_at=parse(data.get("finished_at")),
        error=data.get("error"),
        logs=list(data.get("logs", [])),
    )


# ── Despliegues y módulos ─────────────────────────────────────────────────────


def deployment_to_row(entity: Deployment) -> DeploymentRow:
    row = DeploymentRow(
        id=entity.id,
        project_id=entity.project_id,
        build_id=entity.build_id,
        provider=str(entity.provider),
    )
    apply_deployment(row, entity)
    return row


def apply_deployment(row: DeploymentRow, entity: Deployment) -> None:
    row.status = str(entity.status)
    row.url = entity.url
    row.image_tag = entity.image_tag
    row.env = dict(entity.env)
    row.logs = list(entity.logs)
    row.error = entity.error
    row.updated_at = entity.updated_at


def deployment_from_row(row: DeploymentRow) -> Deployment:
    return Deployment(
        id=row.id,
        project_id=row.project_id,
        build_id=row.build_id,
        provider=DeploymentProvider(row.provider),
        status=DeploymentStatus(row.status),
        url=row.url,
        image_tag=row.image_tag,
        env=dict(row.env or {}),
        logs=list(row.logs or []),
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def module_to_row(entity: ModuleInstallation) -> ModuleInstallationRow:
    return ModuleInstallationRow(
        id=entity.id,
        project_id=entity.project_id,
        module_key=entity.module_key,
        version=str(entity.version),
        state=str(entity.state),
        config=dict(entity.config),
        updated_at=entity.updated_at,
    )


def apply_module(row: ModuleInstallationRow, entity: ModuleInstallation) -> None:
    row.version = str(entity.version)
    row.state = str(entity.state)
    row.config = dict(entity.config)
    row.updated_at = entity.updated_at


def module_from_row(row: ModuleInstallationRow) -> ModuleInstallation:
    return ModuleInstallation(
        id=row.id,
        project_id=row.project_id,
        module_key=row.module_key,
        version=SemVer.parse(row.version),
        state=ModuleState(row.state),
        config=dict(row.config or {}),
        installed_at=row.installed_at,
        updated_at=row.updated_at,
    )
