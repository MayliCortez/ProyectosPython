"""Configuración de la plataforma, cargada desde variables de entorno."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes del proceso. Todas las variables llevan el prefijo ``FACTORY_``."""

    model_config = SettingsConfigDict(
        env_prefix="FACTORY_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_port: int = 8000

    database_url: str = "postgresql+asyncpg://factory:factory@localhost:5432/factory"
    database_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "clave-de-desarrollo-no-usar-en-produccion"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 720

    llm_provider: Literal["anthropic", "fake"] = "fake"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    llm_max_tokens: int = 16_000

    s3_endpoint_url: str | None = None
    s3_bucket: str = "factory-artifacts"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    queue_name: str = "factory:jobs"
    queue_visibility_timeout_seconds: int = 900
    worker_concurrency: int = 4

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Permite declarar los orígenes CORS como lista separada por comas."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def validate_for_production(self) -> list[str]:
        """Devuelve los problemas que impiden arrancar de forma segura en producción."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if self.jwt_secret == Settings.model_fields["jwt_secret"].default:
            problems.append("FACTORY_JWT_SECRET conserva el valor por defecto")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            problems.append("FACTORY_ANTHROPIC_API_KEY no está definida")
        if self.database_url.startswith("sqlite"):
            problems.append("FACTORY_DATABASE_URL apunta a SQLite")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instancia única de configuración para todo el proceso."""
    return Settings()
