"""Genera el backend FastAPI del proyecto: modelos, esquemas, routers y arranque."""

from __future__ import annotations

from factory.codegen.blueprint import Blueprint
from factory.codegen.renderers._common import (
    header,
    python_imports_for,
    python_type,
    snake,
    sqlalchemy_type,
)
from factory.domain.entities.specification import DataEntity
from factory.domain.value_objects import Artifact, table_name_for

_BASE_REQUIREMENTS = (
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "redis>=5.2",
)


def render_backend(blueprint: Blueprint) -> list[Artifact]:
    """Ficheros del backend, listos para `uvicorn app.main:app`."""
    artifacts: list[Artifact] = [
        _requirements(blueprint),
        _config(blueprint),
        _database(blueprint),
        _models(blueprint),
        _schemas(blueprint),
        _dependencies(blueprint),
        _main(blueprint),
        Artifact("backend/app/__init__.py", '"""Aplicación generada."""\n', "python"),
        Artifact("backend/app/routers/__init__.py", '"""Routers REST."""\n', "python"),
    ]
    artifacts.extend(_router(blueprint, entity) for entity in blueprint.entities)
    return artifacts


# ── Ficheros de soporte ───────────────────────────────────────────────────────


def _requirements(blueprint: Blueprint) -> Artifact:
    packages = sorted({*_BASE_REQUIREMENTS, *blueprint.python_packages})
    body = "\n".join(packages) + "\n"
    return Artifact("backend/requirements.txt", body, "text")


def _config(blueprint: Blueprint) -> Artifact:
    env_fields = "\n".join(
        f'    {var.lower()}: str = ""' for var in blueprint.env_vars if var != "DATABASE_URL"
    )
    body = f'''{header("Configuración leída del entorno.")}

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "{blueprint.name}"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/{blueprint.package}"
{env_fields}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
'''
    return Artifact("backend/app/config.py", body, "python")


def _database(blueprint: Blueprint) -> Artifact:
    body = f'''{header("Sesión y metadatos de SQLAlchemy.")}

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia de FastAPI: una sesión por petición, con commit al final."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
'''
    return Artifact("backend/app/database.py", body, "python")


# ── Modelos ───────────────────────────────────────────────────────────────────


def _models(blueprint: Blueprint) -> Artifact:
    extra_imports = "\n".join(python_imports_for(blueprint.entities))
    blocks = [_model_class(entity) for entity in blueprint.entities]
    body = f"""{header("Modelos ORM derivados de la especificación.")}

from __future__ import annotations

{extra_imports}

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

{"".join(blocks)}"""
    return Artifact("backend/app/models.py", body, "python")


def _model_class(entity: DataEntity) -> str:
    lines = [
        f"\n\nclass {entity.name}(Base):",
        f'    """{entity.description or entity.name}."""',
        "",
        f'    __tablename__ = "{entity.table_name}"',
        "",
        "    id: Mapped[int] = mapped_column(Integer, primary_key=True)",
    ]
    for data_field in entity.fields:
        if data_field.name == "id":
            continue
        column = sqlalchemy_type(data_field)
        args = [column]
        if data_field.references:
            args.append(
                f'ForeignKey("{table_name_for(data_field.references)}.id", ondelete="CASCADE")'
            )
        args.append(f"nullable={not data_field.required}")
        if data_field.unique:
            args.append("unique=True")
        annotation = python_type(data_field)
        lines.append(
            f"    {data_field.name}: Mapped[{annotation}] = mapped_column({', '.join(args)})"
        )
    lines.append(
        "    created_at: Mapped[datetime] = mapped_column(\n"
        "        DateTime(timezone=True), server_default=func.now()\n"
        "    )"
    )
    return "\n".join(lines) + "\n"


# ── Esquemas Pydantic ─────────────────────────────────────────────────────────


def _schemas(blueprint: Blueprint) -> Artifact:
    extra_imports = "\n".join(python_imports_for(blueprint.entities))
    blocks: list[str] = []
    for entity in blueprint.entities:
        fields = [
            f"    {f.name}: {python_type(f)}" + ("" if f.required else " = None")
            for f in entity.fields
            if f.name != "id"
        ]
        field_block = "\n".join(fields) or "    pass"
        blocks.append(
            f"\n\nclass {entity.name}Base(BaseModel):\n{field_block}\n"
            f"\n\nclass {entity.name}Create({entity.name}Base):\n"
            f'    """Carga útil de creación."""\n'
            f"\n\nclass {entity.name}Update(BaseModel):\n"
            + "\n".join(
                f"    {f.name}: {python_type(f).removesuffix(' | None')} | None = None"
                for f in entity.fields
                if f.name != "id"
            )
            + f"\n\n\nclass {entity.name}Read({entity.name}Base):\n"
            "    model_config = ConfigDict(from_attributes=True)\n\n"
            "    id: int\n"
            "    created_at: datetime\n"
        )
    body = f"""{header("Esquemas de entrada y salida de la API.")}

from __future__ import annotations

from datetime import datetime
{extra_imports}

from pydantic import BaseModel, ConfigDict

{"".join(blocks)}"""
    return Artifact("backend/app/schemas.py", body, "python")


# ── Routers ───────────────────────────────────────────────────────────────────


def _router(blueprint: Blueprint, entity: DataEntity) -> Artifact:
    resource = entity.table_name
    name = entity.name
    body = f'''{header(f"Endpoints REST de {name}.")}

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import {name}
from app.schemas import {name}Create, {name}Read, {name}Update

router = APIRouter(prefix="/{resource}", tags=["{resource}"])


@router.get("", response_model=list[{name}Read])
async def list_{resource}(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[{name}]:
    """Lista paginada de {resource}."""
    result = await session.execute(select({name}).limit(limit).offset(offset))
    return list(result.scalars())


@router.post("", response_model={name}Read, status_code=status.HTTP_201_CREATED)
async def create_{snake(name)}(
    payload: {name}Create,
    session: AsyncSession = Depends(get_session),
) -> {name}:
    """Crea un registro de {name}."""
    record = {name}(**payload.model_dump())
    session.add(record)
    await session.flush()
    return record


@router.get("/{{record_id}}", response_model={name}Read)
async def get_{snake(name)}(
    record_id: int,
    session: AsyncSession = Depends(get_session),
) -> {name}:
    """Devuelve un {name} por identificador."""
    record = await session.get({name}, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "{name} no encontrado")
    return record


@router.patch("/{{record_id}}", response_model={name}Read)
async def update_{snake(name)}(
    record_id: int,
    payload: {name}Update,
    session: AsyncSession = Depends(get_session),
) -> {name}:
    """Actualiza los campos aportados."""
    record = await session.get({name}, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "{name} no encontrado")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    await session.flush()
    return record


@router.delete("/{{record_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_{snake(name)}(
    record_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Elimina el registro."""
    record = await session.get({name}, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "{name} no encontrado")
    await session.delete(record)
'''
    return Artifact(f"backend/app/routers/{snake(name)}.py", body, "python")


def _dependencies(blueprint: Blueprint) -> Artifact:
    auth_block = (
        '''

async def current_user(token: str = Depends(oauth2_scheme)) -> dict[str, str]:
    """Valida el token JWT y devuelve la identidad del solicitante."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido") from exc
    return {"id": payload["sub"], "email": payload.get("email", "")}
'''
        if blueprint.has_module("login")
        else '''

async def current_user() -> dict[str, str]:
    """El módulo de login no está instalado: no hay identidad que resolver."""
    return {"id": "anonymous", "email": ""}
'''
    )
    imports = (
        "import jwt\nfrom fastapi import Depends, HTTPException, status\n"
        "from fastapi.security import OAuth2PasswordBearer\n\n"
        "from app.config import get_settings\n\n"
        'oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")\n'
        if blueprint.has_module("login")
        else ""
    )
    body = f"{header('Dependencias compartidas por los routers.')}\n\n{imports}{auth_block}"
    return Artifact("backend/app/dependencies.py", body, "python")


def _main(blueprint: Blueprint) -> Artifact:
    router_imports = "\n".join(
        f"from app.routers import {snake(entity.name)}" for entity in blueprint.entities
    )
    router_includes = "\n".join(
        f"    application.include_router({snake(entity.name)}.router, prefix=API_PREFIX)"
        for entity in blueprint.entities
    )
    body = f'''{header(f"Punto de entrada de {blueprint.name}.")}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
{router_imports}

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    """Construye la aplicación con sus routers y middlewares."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        docs_url="/docs",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["sistema"])
    async def health() -> dict[str, str]:
        """Sonda de vida para el orquestador de contenedores."""
        return {{"status": "ok", "app": settings.app_name}}

{router_includes or "    pass"}
    return application


app = create_app()
'''
    return Artifact("backend/app/main.py", body, "python")
