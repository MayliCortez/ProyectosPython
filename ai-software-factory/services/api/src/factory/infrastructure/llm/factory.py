"""Selección del proveedor de IA según la configuración."""

from __future__ import annotations

import logging

from factory.application.ports.llm import LLMClient
from factory.config import Settings
from factory.infrastructure.llm.anthropic_client import AnthropicClient
from factory.infrastructure.llm.fake import FakeLLMClient

logger = logging.getLogger(__name__)


def build_llm_client(settings: Settings) -> LLMClient:
    """Devuelve el cliente configurado, con reserva determinista si falta la clave."""
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning(
                "FACTORY_LLM_PROVIDER=anthropic pero no hay clave de API; "
                "se usa el proveedor determinista"
            )
            return FakeLLMClient()
        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            effort=settings.llm_effort,
            max_tokens=settings.llm_max_tokens,
        )
    return FakeLLMClient()
