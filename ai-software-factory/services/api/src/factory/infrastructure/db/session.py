"""Motor y fábrica de sesiones de base de datos."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from factory.config import Settings, get_settings
from factory.infrastructure.db.models import Base


class Database:
    """Envoltura del motor asíncrono con utilidades de arranque y cierre."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            pool_pre_ping=not url.startswith("sqlite"),
            connect_args=connect_args,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    def session(self) -> AsyncSession:
        return self._session_factory()

    async def create_all(self) -> None:
        """Crea el esquema. En producción manda Alembic; esto es para pruebas y demos."""
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

    async def dispose(self) -> None:
        await self._engine.dispose()


@lru_cache(maxsize=1)
def get_database(settings: Settings | None = None) -> Database:
    """Instancia única del motor para el proceso."""
    resolved = settings or get_settings()
    return Database(resolved.database_url, echo=resolved.database_echo)
