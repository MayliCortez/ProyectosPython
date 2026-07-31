"""Fixtures compartidas de la suite.

Toda la suite corre con el proveedor de IA determinista y SQLite en memoria: es
rápida, no toca la red y no depende de que haya Postgres o Redis levantados.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from factory.application.services import (
    AuthService,
    BuildService,
    ConversationService,
    DeploymentService,
    ModuleService,
    ProjectService,
)
from factory.catalog.catalog import get_catalog
from factory.config import Settings
from factory.container import Container
from factory.domain.entities import Conversation, Organization, Project, User, UserRole
from factory.domain.value_objects import Email
from factory.infrastructure.db.session import Database
from factory.infrastructure.db.uow import SqlAlchemyUnitOfWork
from factory.infrastructure.deploy import DryRunDeployer
from factory.infrastructure.events import InMemoryEventBus
from factory.infrastructure.llm.fake import FakeLLMClient
from factory.infrastructure.queue import InMemoryJobQueue
from factory.infrastructure.security.hasher import Pbkdf2PasswordHasher
from factory.infrastructure.security.tokens import TokenService
from factory.infrastructure.storage import InMemoryObjectStorage
from factory.interfaces.http.app import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="",
        jwt_secret="secreto-de-pruebas",
        llm_provider="fake",
        log_level="WARNING",
    )


@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    # SQLite en memoria vive mientras dure el motor: se comparte una sola conexión.
    db = Database("sqlite+aiosqlite:///file:test?mode=memory&cache=shared&uri=true")
    await db.create_all()
    yield db
    await db.dispose()


@pytest.fixture
def llm() -> FakeLLMClient:
    """Proveedor determinista que además contesta a sus propias preguntas."""
    return FakeLLMClient(answer_questions=True)


@pytest.fixture
def asking_llm() -> FakeLLMClient:
    """Proveedor determinista que sí formula preguntas de aclaración."""
    return FakeLLMClient(answer_questions=False)


@pytest.fixture
def events() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()


@pytest.fixture
def queue() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def deployer() -> DryRunDeployer:
    return DryRunDeployer()


@pytest.fixture
def container(
    settings: Settings,
    database: Database,
    llm: FakeLLMClient,
    events: InMemoryEventBus,
    storage: InMemoryObjectStorage,
    queue: InMemoryJobQueue,
    deployer: DryRunDeployer,
) -> Container:
    """Contenedor con todas las dependencias sustituidas por dobles en memoria."""
    instance = Container(settings=settings, database=database, redis=None)
    catalog = get_catalog()
    uow_factory = lambda: SqlAlchemyUnitOfWork(database)  # noqa: E731

    tokens = TokenService(secret=settings.jwt_secret, ttl_minutes=60)
    instance.__dict__.update(
        {
            "catalog": catalog,
            "llm": llm,
            "events": events,
            "storage": storage,
            "queue": queue,
            "deployer": deployer,
            "tokens": tokens,
            "auth": AuthService(uow_factory, tokens, Pbkdf2PasswordHasher()),
            "projects": ProjectService(uow_factory, events),
            "conversations": ConversationService(uow_factory, events, llm, catalog),
            "modules": ModuleService(uow_factory, catalog, events),
            "builds": BuildService(uow_factory, queue, events, llm, storage, catalog),
            "deployments": DeploymentService(uow_factory, queue, events, storage, deployer),
        }
    )
    return instance


@pytest_asyncio.fixture
async def organization(database: Database) -> Organization:
    entity = Organization.create("Acme")
    async with SqlAlchemyUnitOfWork(database) as uow:
        await uow.organizations.add(entity)
    return entity


@pytest_asyncio.fixture
async def user(database: Database, organization: Organization) -> User:
    entity = User(
        organization_id=organization.id,
        email=Email("dev@acme.test"),
        password_hash=Pbkdf2PasswordHasher().hash("contrasena-segura"),
        full_name="Dev de pruebas",
        role=UserRole.OWNER,
    )
    async with SqlAlchemyUnitOfWork(database) as uow:
        await uow.users.add(entity)
    return entity


@pytest_asyncio.fixture
async def project(database: Database, user: User) -> Project:
    entity = Project.create(
        organization_id=user.organization_id,
        name="Gimnasio Titan",
        prompt="Necesito un sistema para un gimnasio",
        created_by=user.id,
    )
    async with SqlAlchemyUnitOfWork(database) as uow:
        await uow.projects.add(entity)
        await uow.conversations.add(Conversation(project_id=entity.id))
    return entity


@pytest.fixture
def token(container: Container, user: User) -> str:
    issued, _ = container.tokens.issue(user)
    return issued


@pytest_asyncio.fixture
async def client(container: Container, settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings=settings, container=container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        # El `lifespan` no se ejecuta con ASGITransport: se inyecta el contenedor.
        app.state.container = container
        yield http_client


@pytest.fixture
def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
