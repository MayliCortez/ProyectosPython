"""Documento de requisitos y especificación técnica derivada."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from factory.domain.errors import ValidationError
from factory.domain.value_objects import (
    BusinessDomain,
    TechStack,
    new_id,
    table_name_for,
    utcnow,
)


@dataclass(frozen=True, slots=True)
class UserStory:
    """Historia de usuario con criterios de aceptación verificables."""

    id: str
    role: str
    goal: str
    benefit: str = ""
    acceptance_criteria: tuple[str, ...] = field(default_factory=tuple)
    priority: int = 2  # 1 = imprescindible, 2 = deseable, 3 = opcional

    def __str__(self) -> str:
        benefit = f" para {self.benefit}" if self.benefit else ""
        return f"Como {self.role} quiero {self.goal}{benefit}"


@dataclass(frozen=True, slots=True)
class DataField:
    """Campo de una entidad de datos del sistema generado."""

    name: str
    type: str = "string"
    required: bool = True
    unique: bool = False
    references: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValidationError(f"Nombre de campo inválido: {self.name!r}")


@dataclass(frozen=True, slots=True)
class DataEntity:
    """Tabla/modelo del dominio del proyecto generado."""

    name: str
    fields: tuple[DataField, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValidationError(f"La entidad {self.name!r} no tiene campos")

    @property
    def table_name(self) -> str:
        """Nombre de tabla en plural (`MembershipPlan` → `membership_plans`)."""
        return table_name_for(self.name)


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Operación REST expuesta por el backend generado."""

    method: str
    path: str
    summary: str = ""
    entity: str | None = None
    auth_required: bool = True

    def __post_init__(self) -> None:
        method = self.method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValidationError(f"Método HTTP no soportado: {self.method!r}")
        object.__setattr__(self, "method", method)
        if not self.path.startswith("/"):
            raise ValidationError(f"La ruta debe empezar por '/': {self.path!r}")


@dataclass(slots=True)
class RequirementsDocument:
    """Salida del analista: qué hay que construir, en lenguaje de negocio."""

    project_id: str
    summary: str
    business_domain: BusinessDomain = BusinessDomain.GENERIC
    stories: list[UserStory] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    suggested_modules: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    @property
    def must_have_stories(self) -> list[UserStory]:
        return [story for story in self.stories if story.priority == 1]

    def to_markdown(self) -> str:
        """Documento legible que se entrega al usuario y se guarda como artefacto."""
        lines = [
            "# Documento de requisitos",
            "",
            f"**Dominio detectado:** {self.business_domain}",
            "",
            "## Resumen",
            "",
            self.summary,
            "",
            "## Historias de usuario",
            "",
        ]
        for story in sorted(self.stories, key=lambda s: s.priority):
            lines.append(f"### {story.id} — {story}")
            if story.acceptance_criteria:
                lines.append("")
                lines.extend(f"- {criterion}" for criterion in story.acceptance_criteria)
            lines.append("")
        if self.constraints:
            lines += ["## Restricciones", ""]
            lines += [f"- {item}" for item in self.constraints] + [""]
        if self.out_of_scope:
            lines += ["## Fuera de alcance", ""]
            lines += [f"- {item}" for item in self.out_of_scope] + [""]
        if self.suggested_modules:
            lines += ["## Módulos propuestos", ""]
            lines += [f"- `{key}`" for key in self.suggested_modules] + [""]
        return "\n".join(lines)


@dataclass(slots=True)
class Specification:
    """Salida del arquitecto: qué hay que construir, en lenguaje técnico."""

    project_id: str
    requirements_id: str
    tech_stack: TechStack = field(default_factory=TechStack)
    entities: list[DataEntity] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        """Comprueba la coherencia interna antes de pasarla a los generadores."""
        names = [entity.name for entity in self.entities]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValidationError(
                f"Entidades duplicadas en la especificación: {sorted(duplicates)}",
                details={"entities": sorted(duplicates)},
            )
        known = set(names)
        for entity in self.entities:
            for data_field in entity.fields:
                if data_field.references and data_field.references not in known:
                    raise ValidationError(
                        f"{entity.name}.{data_field.name} referencia la entidad "
                        f"desconocida {data_field.references!r}",
                        details={"entity": entity.name, "field": data_field.name},
                    )
        for endpoint in self.endpoints:
            if endpoint.entity and endpoint.entity not in known:
                raise ValidationError(
                    f"El endpoint {endpoint.method} {endpoint.path} referencia la "
                    f"entidad desconocida {endpoint.entity!r}"
                )

    def entity(self, name: str) -> DataEntity | None:
        return next((item for item in self.entities if item.name == name), None)

    def next_version(self) -> int:
        return self.version + 1
