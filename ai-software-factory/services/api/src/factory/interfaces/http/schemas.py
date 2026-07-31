"""Esquemas de entrada y salida de la API REST."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    organization_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(default="", max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    organization_id: str
    role: str
    email: str


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    prompt: str = Field(default="", max_length=20_000)


class RenameProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CreateProjectResponse(BaseModel):
    project: ProjectResponse
    conversation_id: str


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = Field(min_length=1, max_length=5_000)


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    rationale: str
    options: list[str]
    required: bool


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any]


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    messages: list[MessageResponse]
    pending_questions: list[QuestionResponse]
    answers: dict[str, str]


class StageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    agent: str
    status: str
    error: str | None
    duration_seconds: float | None
    logs: list[str]


class BuildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    status: str
    progress: float
    stages: list[StageResponse]
    artifact_count: int
    total_bytes: int
    bundle_key: str | None
    error: str | None
    created_at: str


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    build_id: str
    provider: str
    status: str
    url: str | None
    error: str | None
    logs: list[str]
    created_at: str


class CreateDeploymentRequest(BaseModel):
    build_id: str | None = None
    provider: str = "docker_local"
    env: dict[str, str] = Field(default_factory=dict)


class InstallModulesRequest(BaseModel):
    modules: list[str] = Field(min_length=1)


class RemoveModulesRequest(BaseModel):
    modules: list[str] = Field(min_length=1)
    cascade: bool = False


class UpgradeModuleRequest(BaseModel):
    version: str


class ModuleInstallationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_key: str
    version: str
    state: str
    config: dict[str, Any]


class ModuleOperationResponse(BaseModel):
    installed: list[ModuleInstallationResponse]
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SpecificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    version: int
    tech_stack: dict[str, str]
    entities: list[dict[str, Any]]
    endpoints: list[dict[str, Any]]
    modules: list[str]
    pages: list[str]


class RequirementsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    summary: str
    business_domain: str
    markdown: str
    suggested_modules: list[str]


class DownloadResponse(BaseModel):
    url: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
