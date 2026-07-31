"""Cliente del motor de IA sobre la API de Claude."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import anthropic

from factory.application.ports.llm import LLMResponse
from factory.domain.errors import AgentExecutionError

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Implementación de `LLMClient` con el SDK oficial de Anthropic.

    Usa salida estructurada (`output_config.format`) para las llamadas que necesitan
    un JSON conforme a esquema, de modo que los agentes reciben datos ya validados en
    lugar de tener que analizar texto libre.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-opus-5",
        effort: str = "high",
        max_tokens: int = 16_000,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Texto libre. Se transmite en streaming para evitar timeouts en respuestas largas."""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config=cast("Any", {"effort": self._effort}),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = await stream.get_final_message()

        if message.stop_reason == "refusal":
            return LLMResponse(text="", model=message.model, refused=True)

        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Salida conforme al esquema. El resultado analizado va en `data`."""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config=cast(
                "Any",
                {
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            ),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = await stream.get_final_message()

        if message.stop_reason == "refusal":
            raise AgentExecutionError(
                schema_name, "El modelo declinó la petición por motivos de seguridad"
            )

        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Respuesta no analizable para %s: %s", schema_name, text[:500])
            raise AgentExecutionError(
                schema_name, f"El modelo devolvió un JSON inválido: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise AgentExecutionError(schema_name, "Se esperaba un objeto JSON en la raíz")

        return LLMResponse(
            text=text,
            data=data,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
