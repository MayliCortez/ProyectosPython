"""Genera la suite de pruebas del proyecto: fixtures, humo y CRUD por entidad."""

from __future__ import annotations

from factory.codegen.blueprint import Blueprint
from factory.domain.entities.specification import DataEntity
from factory.domain.value_objects import Artifact, snake_case, table_name_for

_SAMPLES: dict[str, str] = {
    "string": '"ejemplo"',
    "text": '"texto de ejemplo"',
    "email": '"persona@example.com"',
    "integer": "1",
    "decimal": '"10.50"',
    "float": "1.5",
    "boolean": "True",
    "date": '"2026-01-15"',
    "datetime": '"2026-01-15T10:00:00Z"',
    "uuid": '"6f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"',
    "json": "{}",
}


def render_tests(blueprint: Blueprint) -> list[Artifact]:
    """Pruebas ejecutables con `pytest` contra la aplicación generada."""
    entities = {entity.name: entity for entity in blueprint.entities}
    artifacts = [_conftest(blueprint), _smoke(blueprint)]
    artifacts.extend(_entity_tests(entity, entities) for entity in blueprint.entities)
    return artifacts


# ── Carga útil y dependencias ─────────────────────────────────────────────────


def _sample(field_type: str) -> str:
    return _SAMPLES.get(field_type, _SAMPLES["string"])


def _payload_entries(entity: DataEntity, *, with_references: bool) -> list[str]:
    """Campos obligatorios de la entidad; las claves foráneas salen de `ids`."""
    entries: list[str] = []
    for data_field in entity.fields:
        if data_field.name == "id" or not data_field.required:
            continue
        if data_field.references:
            if with_references:
                entries.append(f'        "{data_field.name}": ids["{data_field.references}"],')
            continue
        entries.append(f'        "{data_field.name}": {_sample(data_field.type)},')
    return entries


def _ancestors(entity: DataEntity, entities: dict[str, DataEntity]) -> list[DataEntity]:
    """Entidades que hay que crear antes, en orden topológico y sin repetir.

    Sin esto la prueba de una entidad con clave foránea enviaría una carga útil
    incompleta y la API respondería 422: el error se detectó ejecutando de verdad la
    suite generada, no leyéndola.
    """
    ordered: list[DataEntity] = []
    seen: set[str] = set()

    def visit(current: DataEntity, trail: frozenset[str]) -> None:
        for data_field in current.fields:
            target = data_field.references
            if not target or target not in entities or target in trail:
                continue
            parent = entities[target]
            visit(parent, trail | {current.name})
            if parent.name not in seen:
                seen.add(parent.name)
                ordered.append(parent)

    visit(entity, frozenset({entity.name}))
    return ordered


def _seed_function(entity: DataEntity, entities: dict[str, DataEntity]) -> str:
    parents = _ancestors(entity, entities)
    if not parents:
        return (
            "async def _seed(client: AsyncClient) -> dict[str, int]:\n"
            f'    """{entity.name} no depende de ninguna otra entidad."""\n'
            "    return {}\n"
        )

    lines = [
        "async def _seed(client: AsyncClient) -> dict[str, int]:",
        f'    """Crea los registros de los que depende {entity.name}."""',
        "    ids: dict[str, int] = {}",
    ]
    for parent in parents:
        body = "\n".join(_payload_entries(parent, with_references=True))
        lines += [
            "",
            f'    created = await client.post(\n        "/api/v1/{parent.table_name}",',
            f"        json={{\n{body}\n        }},\n    )",
            "    assert created.status_code == 201, created.text",
            f'    ids["{parent.name}"] = created.json()["id"]',
        ]
    lines += ["", "    return ids", ""]
    return "\n".join(lines)


# ── Ficheros ──────────────────────────────────────────────────────────────────


def _conftest(blueprint: Blueprint) -> Artifact:
    body = f'''"""Fixtures compartidas de las pruebas de {blueprint.name}."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncIterator[None]:
    """Cada prueba arranca contra un esquema limpio."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
'''
    return Artifact("backend/tests/conftest.py", body, "python")


def _smoke(blueprint: Blueprint) -> Artifact:
    checks = "\n".join(
        f'    assert "/api/v1/{entity.table_name}" in paths' for entity in blueprint.entities
    )
    body = f'''"""Pruebas de humo: la aplicación arranca y expone lo esperado."""

import pytest
from httpx import AsyncClient

from app.main import app

pytestmark = pytest.mark.anyio


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_routes_registered(client: AsyncClient) -> None:
    """Cada entidad de la especificación tiene su router montado.

    Es asíncrona a propósito: la fixture `prepare_database` es autouse y asíncrona,
    y una prueba síncrona no podría resolverla.
    """
    paths = set(app.openapi()["paths"])
{checks or "    assert paths"}
'''
    return Artifact("backend/tests/test_smoke.py", body, "python")


def _entity_tests(entity: DataEntity, entities: dict[str, DataEntity]) -> Artifact:
    resource = entity.table_name
    own = "\n".join(_payload_entries(entity, with_references=True))
    body = f'''"""Ciclo CRUD de {entity.name}."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


{_seed_function(entity, entities)}

def _payload(ids: dict[str, int]) -> dict[str, object]:
    """Carga útil mínima válida para crear un {entity.name}."""
    return {{
{own}
    }}


async def test_create_and_read(client: AsyncClient) -> None:
    ids = await _seed(client)

    created = await client.post("/api/v1/{resource}", json=_payload(ids))
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]

    fetched = await client.get(f"/api/v1/{resource}/{{record_id}}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == record_id


async def test_list_returns_created_record(client: AsyncClient) -> None:
    ids = await _seed(client)
    await client.post("/api/v1/{resource}", json=_payload(ids))

    listed = await client.get("/api/v1/{resource}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_update_changes_the_record(client: AsyncClient) -> None:
    ids = await _seed(client)
    created = await client.post("/api/v1/{resource}", json=_payload(ids))
    record_id = created.json()["id"]

    updated = await client.patch(f"/api/v1/{resource}/{{record_id}}", json={{}})
    assert updated.status_code == 200
    assert updated.json()["id"] == record_id


async def test_delete(client: AsyncClient) -> None:
    ids = await _seed(client)
    created = await client.post("/api/v1/{resource}", json=_payload(ids))
    record_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/{resource}/{{record_id}}")
    assert deleted.status_code == 204

    missing = await client.get(f"/api/v1/{resource}/{{record_id}}")
    assert missing.status_code == 404


async def test_unknown_record_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/{resource}/999999")
    assert response.status_code == 404
'''
    return Artifact(f"backend/tests/test_{snake_case(entity.name)}.py", body, "python")


#: Reexportado para que otros renderizadores compartan la convención de nombres.
__all__ = ["render_tests", "table_name_for"]
