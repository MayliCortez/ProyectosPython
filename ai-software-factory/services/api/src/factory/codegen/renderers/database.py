"""Genera el esquema SQL y la migración inicial del proyecto."""

from __future__ import annotations

from factory.codegen.blueprint import Blueprint
from factory.codegen.renderers._common import sql_type
from factory.domain.entities.specification import DataEntity
from factory.domain.value_objects import Artifact, table_name_for


def render_database(blueprint: Blueprint) -> list[Artifact]:
    """Esquema DDL, migración de Alembic y datos de ejemplo."""
    return [
        _schema_sql(blueprint),
        _alembic_ini(),
        _alembic_env(blueprint),
        _initial_migration(blueprint),
        _seed(blueprint),
    ]


def _ordered_entities(blueprint: Blueprint) -> list[DataEntity]:
    """Ordena las tablas para que las referenciadas se creen antes que sus referencias."""
    by_name = {entity.name: entity for entity in blueprint.entities}
    placed: list[DataEntity] = []
    seen: set[str] = set()

    def place(entity: DataEntity, trail: frozenset[str]) -> None:
        if entity.name in seen or entity.name in trail:
            return
        for data_field in entity.fields:
            target = data_field.references
            if target and target in by_name and target != entity.name:
                place(by_name[target], trail | {entity.name})
        seen.add(entity.name)
        placed.append(entity)

    for entity in blueprint.entities:
        place(entity, frozenset())
    return placed


def _columns(entity: DataEntity) -> list[str]:
    columns = ["    id SERIAL PRIMARY KEY"]
    for data_field in entity.fields:
        if data_field.name == "id":
            continue
        parts = [f"    {data_field.name} {sql_type(data_field)}"]
        if data_field.required:
            parts.append("NOT NULL")
        if data_field.unique:
            parts.append("UNIQUE")
        if data_field.references:
            parts.append(
                f"REFERENCES {table_name_for(data_field.references)}(id) ON DELETE CASCADE"
            )
        columns.append(" ".join(parts))
    columns.append("    created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
    return columns


def _schema_sql(blueprint: Blueprint) -> Artifact:
    statements = [
        f"-- Esquema de {blueprint.name}",
        "-- Generado por AI Software Factory",
        "",
    ]
    for entity in _ordered_entities(blueprint):
        columns = ",\n".join(_columns(entity))
        statements.append(f"CREATE TABLE IF NOT EXISTS {entity.table_name} (\n{columns}\n);")
        for data_field in entity.fields:
            if data_field.references:
                statements.append(
                    f"CREATE INDEX IF NOT EXISTS idx_{entity.table_name}_{data_field.name} "
                    f"ON {entity.table_name}({data_field.name});"
                )
        statements.append("")
    return Artifact("database/schema.sql", "\n".join(statements), "sql")


def _alembic_ini() -> Artifact:
    body = """[alembic]
script_location = migrations
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
"""
    return Artifact("backend/alembic.ini", body, "ini")


def _alembic_env(blueprint: Blueprint) -> Artifact:
    body = f'''"""Entorno de Alembic de {blueprint.name}."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401  — registra los modelos en los metadatos

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn, target_metadata=target_metadata
            )
        )
        await connection.run_sync(lambda _: context.run_migrations())
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
'''
    return Artifact("backend/migrations/env.py", body, "python")


def _initial_migration(blueprint: Blueprint) -> Artifact:
    ups: list[str] = []
    downs: list[str] = []
    for entity in _ordered_entities(blueprint):
        columns = [
            '        sa.Column("id", sa.Integer, primary_key=True),',
        ]
        for data_field in entity.fields:
            if data_field.name == "id":
                continue
            # El orden importa: ForeignKey es posicional y va antes de los kwargs.
            parts = [f'"{data_field.name}"', "sa.Text"]
            if data_field.references:
                target = table_name_for(data_field.references)
                parts.append(f'sa.ForeignKey("{target}.id", ondelete="CASCADE")')
            parts.append(f"nullable={not data_field.required}")
            if data_field.unique:
                parts.append("unique=True")
            columns.append(f"        sa.Column({', '.join(parts)}),")
        columns.append(
            '        sa.Column("created_at", sa.DateTime(timezone=True), '
            "server_default=sa.func.now()),"
        )
        body = "\n".join(columns)
        ups.append(f'    op.create_table(\n        "{entity.table_name}",\n{body}\n    )')
        downs.insert(0, f'    op.drop_table("{entity.table_name}")')

    body = f'''"""Migración inicial de {blueprint.name}.

Revision ID: 0001_initial
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
{chr(10).join(ups) or "    pass"}


def downgrade() -> None:
{chr(10).join(downs) or "    pass"}
'''
    return Artifact("backend/migrations/versions/0001_initial.py", body, "python")


def _seed(blueprint: Blueprint) -> Artifact:
    inserts = [
        f"-- Datos de ejemplo para {entity.table_name} (rellenar según necesidad)"
        for entity in blueprint.entities
    ]
    body = "\n".join([f"-- Datos iniciales de {blueprint.name}", "", *inserts, ""])
    return Artifact("database/seed.sql", body, "sql")
