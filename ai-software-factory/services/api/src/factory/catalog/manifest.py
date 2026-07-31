"""Manifiesto de un módulo reutilizable.

El manifiesto es el contrato completo del módulo: qué necesita, qué aporta y qué
toca del sistema generado. Todo lo que el instalador y los generadores necesitan
saber está aquí, de modo que añadir un módulo nuevo no requiere tocar código del
motor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from factory.domain.errors import ValidationError
from factory.domain.value_objects import SemVer, is_slug


class ModuleCategory(StrEnum):
    """Agrupación del módulo en el catálogo, usada por el panel de la plataforma."""

    CORE = "core"
    OPERATIONS = "operations"
    COMMERCE = "commerce"
    ENGAGEMENT = "engagement"
    INTELLIGENCE = "intelligence"
    PLATFORM = "platform"


@dataclass(frozen=True, slots=True)
class ModuleTable:
    """Tabla que el módulo añade al esquema del proyecto generado."""

    name: str
    columns: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True, slots=True)
class ModuleEndpoint:
    """Endpoint REST que el módulo publica en el backend generado."""

    method: str
    path: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class ModulePage:
    """Pantalla que el módulo añade al frontend generado."""

    route: str
    title: str
    icon: str = "square"


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Definición declarativa e inmutable de un módulo instalable."""

    key: str
    name: str
    description: str
    category: ModuleCategory
    version: SemVer
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    conflicts_with: tuple[str, ...] = field(default_factory=tuple)
    tables: tuple[ModuleTable, ...] = field(default_factory=tuple)
    endpoints: tuple[ModuleEndpoint, ...] = field(default_factory=tuple)
    pages: tuple[ModulePage, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)
    env_vars: tuple[str, ...] = field(default_factory=tuple)
    python_packages: tuple[str, ...] = field(default_factory=tuple)
    npm_packages: tuple[str, ...] = field(default_factory=tuple)
    removable: bool = True

    def __post_init__(self) -> None:
        if not is_slug(self.key):
            raise ValidationError(f"La clave del módulo debe ser un slug: {self.key!r}")
        if self.key in self.depends_on:
            raise ValidationError(f"El módulo {self.key!r} no puede depender de sí mismo")
        overlap = set(self.depends_on) & set(self.conflicts_with)
        if overlap:
            raise ValidationError(
                f"El módulo {self.key!r} declara {sorted(overlap)} como dependencia y "
                "conflicto a la vez"
            )

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(table.name for table in self.tables)

    def is_compatible_with(self, dependency: ModuleManifest) -> bool:
        """Un módulo es compatible con su dependencia si comparten versión mayor."""
        return self.version.major == 0 or dependency.version.major <= self.version.major

    def summary(self) -> dict[str, object]:
        """Vista compacta para el catálogo del panel."""
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "category": str(self.category),
            "version": str(self.version),
            "depends_on": list(self.depends_on),
            "conflicts_with": list(self.conflicts_with),
            "tables": [table.name for table in self.tables],
            "endpoints": len(self.endpoints),
            "pages": [{"route": p.route, "title": p.title, "icon": p.icon} for p in self.pages],
            "permissions": list(self.permissions),
            "env_vars": list(self.env_vars),
            "removable": self.removable,
        }
