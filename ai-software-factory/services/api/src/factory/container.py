"""Composición de dependencias.

Es el único punto donde se decide qué implementación concreta cumple cada puerto.
Cambiar Redis por una cola en memoria, o S3 por disco local, es cambiar una rama aquí
y nada más: ni los servicios ni los agentes conocen la diferencia.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from redis.asyncio import Redis

from factory.application.ports.deployer import Deployer
from factory.application.ports.event_bus import EventBus
from factory.application.ports.llm import LLMClient
from factory.application.ports.queue import JobQueue
from factory.application.ports.storage import ObjectStorage
from factory.application.ports.uow import UnitOfWork
from factory.application.services import (
    AuthService,
    BuildService,
    ConversationService,
    DeploymentService,
    ModuleService,
    ProjectService,
)
from factory.catalog.catalog import ModuleCatalog, get_catalog
from factory.config import Settings, get_settings
from factory.infrastructure.db.session import Database
from factory.infrastructure.db.uow import SqlAlchemyUnitOfWork
from factory.infrastructure.deploy import DockerComposeDeployer, DryRunDeployer
from factory.infrastructure.events import InMemoryEventBus, RedisEventBus
from factory.infrastructure.llm import build_llm_client
from factory.infrastructure.queue import InMemoryJobQueue, RedisJobQueue
from factory.infrastructure.security.hasher import Pbkdf2PasswordHasher
from factory.infrastructure.security.tokens import TokenService
from factory.infrastructure.storage import InMemoryObjectStorage, S3ObjectStorage

logger = logging.getLogger(__name__)


@dataclass
class Container:
    """Grafo de dependencias del proceso, construido perezosamente."""

    settings: Settings
    database: Database
    redis: Redis | None = None

    # ── Infraestructura ───────────────────────────────────────────────────────

    @cached_property
    def catalog(self) -> ModuleCatalog:
        return get_catalog()

    @cached_property
    def llm(self) -> LLMClient:
        return build_llm_client(self.settings)

    @cached_property
    def queue(self) -> JobQueue:
        if self.redis is None:
            logger.warning("Sin Redis: se usa la cola en memoria (un solo proceso)")
            return InMemoryJobQueue()
        return RedisJobQueue(self.redis, name=self.settings.queue_name)

    @cached_property
    def events(self) -> EventBus:
        if self.redis is None:
            return InMemoryEventBus()
        return RedisEventBus(self.redis)

    @cached_property
    def storage(self) -> ObjectStorage:
        if not self.settings.s3_endpoint_url and not self.settings.s3_access_key:
            logger.warning("Sin configuración de S3: los artefactos se guardan en memoria")
            return InMemoryObjectStorage()
        return S3ObjectStorage(
            bucket=self.settings.s3_bucket,
            endpoint_url=self.settings.s3_endpoint_url,
            access_key=self.settings.s3_access_key,
            secret_key=self.settings.s3_secret_key,
            region=self.settings.s3_region,
        )

    @cached_property
    def deployer(self) -> Deployer:
        if self.settings.is_production:
            return DockerComposeDeployer(workspace=Path("/var/lib/factory/deployments"))
        return DryRunDeployer()

    @cached_property
    def tokens(self) -> TokenService:
        return TokenService(
            secret=self.settings.jwt_secret,
            algorithm=self.settings.jwt_algorithm,
            ttl_minutes=self.settings.jwt_ttl_minutes,
        )

    def unit_of_work(self) -> UnitOfWork:
        return SqlAlchemyUnitOfWork(self.database)

    # ── Servicios ─────────────────────────────────────────────────────────────

    @cached_property
    def auth(self) -> AuthService:
        return AuthService(self.unit_of_work, self.tokens, Pbkdf2PasswordHasher())

    @cached_property
    def projects(self) -> ProjectService:
        return ProjectService(self.unit_of_work, self.events)

    @cached_property
    def conversations(self) -> ConversationService:
        return ConversationService(self.unit_of_work, self.events, self.llm, self.catalog)

    @cached_property
    def modules(self) -> ModuleService:
        return ModuleService(self.unit_of_work, self.catalog, self.events)

    @cached_property
    def builds(self) -> BuildService:
        return BuildService(
            self.unit_of_work,
            self.queue,
            self.events,
            self.llm,
            self.storage,
            self.catalog,
        )

    @cached_property
    def deployments(self) -> DeploymentService:
        return DeploymentService(
            self.unit_of_work,
            self.queue,
            self.events,
            self.storage,
            self.deployer,
        )

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self.database.dispose()
        if self.redis is not None:
            await self.redis.aclose()


async def build_container(settings: Settings | None = None) -> Container:
    """Construye el contenedor y verifica lo imprescindible antes de servir tráfico."""
    resolved = settings or get_settings()

    problems = resolved.validate_for_production()
    if problems:
        raise RuntimeError("La configuración no es apta para producción: " + "; ".join(problems))

    database = Database(resolved.database_url, echo=resolved.database_echo)
    redis: Redis | None = None
    if resolved.redis_url:
        try:
            redis = Redis.from_url(resolved.redis_url, decode_responses=True)
            await redis.ping()
        except Exception:  # noqa: BLE001 — degradación explícita a modo local
            logger.warning("Redis no está disponible en %s", resolved.redis_url)
            redis = None

    return Container(settings=resolved, database=database, redis=redis)
