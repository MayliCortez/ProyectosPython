"""Productos tipados que los agentes dejan en la pizarra compartida.

Tenerlos como estructuras explícitas —en vez de diccionarios sueltos— hace que el
contrato entre agentes sea verificable: si el arquitecto cambia lo que produce, el
diseñador de APIs deja de compilar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from factory.domain.value_objects import TechStack


@dataclass(frozen=True, slots=True)
class ArchitectureDecision:
    """Salida del arquitecto: pila, módulos resueltos y pantallas."""

    tech_stack: TechStack
    modules: tuple[str, ...]
    pages: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""
