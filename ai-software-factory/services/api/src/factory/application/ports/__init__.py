"""Puertos: contratos que la capa de aplicación exige a la infraestructura."""

from factory.application.ports.event_bus import EventBus
from factory.application.ports.llm import LLMClient, LLMResponse
from factory.application.ports.queue import Job, JobQueue
from factory.application.ports.repositories import (
    BuildRepository,
    ConversationRepository,
    DeploymentRepository,
    ModuleRepository,
    OrganizationRepository,
    ProjectRepository,
    SpecificationRepository,
    UserRepository,
)
from factory.application.ports.storage import ObjectStorage
from factory.application.ports.uow import UnitOfWork

__all__ = [
    "BuildRepository",
    "ConversationRepository",
    "DeploymentRepository",
    "EventBus",
    "Job",
    "JobQueue",
    "LLMClient",
    "LLMResponse",
    "ModuleRepository",
    "ObjectStorage",
    "OrganizationRepository",
    "ProjectRepository",
    "SpecificationRepository",
    "UnitOfWork",
    "UserRepository",
]
