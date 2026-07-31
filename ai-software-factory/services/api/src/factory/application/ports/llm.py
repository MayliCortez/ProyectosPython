"""Puerto del motor de IA. Aísla a los agentes del proveedor concreto."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Respuesta del modelo, ya normalizada."""

    text: str
    data: dict[str, Any] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    refused: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMClient(Protocol):
    """Contrato mínimo que necesitan los agentes.

    Dos operaciones: texto libre y salida estructurada contra un esquema JSON.
    La implementación falsa (`infrastructure.llm.fake`) cumple el mismo contrato de
    forma determinista, lo que hace testeable el pipeline completo sin red.
    """

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Genera texto libre."""
        ...

    async def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Genera una respuesta que valida contra `schema`; el resultado va en `data`."""
        ...
