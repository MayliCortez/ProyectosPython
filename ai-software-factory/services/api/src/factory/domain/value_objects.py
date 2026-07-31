"""Objetos de valor: inmutables, sin identidad y validados en la construcción."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from factory.domain.errors import ValidationError

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def new_id() -> str:
    """Identificador único para entidades nuevas."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Instante actual en UTC, siempre con zona horaria explícita."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Email:
    """Correo electrónico normalizado."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValidationError(f"Correo electrónico inválido: {self.value!r}")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Slug:
    """Identificador legible y estable, apto para rutas y nombres de contenedor."""

    value: str

    def __post_init__(self) -> None:
        normalized = slugify(self.value)
        if not normalized:
            raise ValidationError(f"No se puede derivar un slug de {self.value!r}")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


def slugify(text: str) -> str:
    """Convierte texto libre en un slug (`Sistema de Gimnasio` → `sistema-de-gimnasio`)."""
    lowered = text.strip().lower()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return re.sub(r"-{2,}", "-", cleaned)[:64]


def is_slug(value: str) -> bool:
    """Indica si el texto ya está en forma de slug."""
    return bool(_SLUG_RE.match(value))


def snake_case(name: str) -> str:
    """`MembershipPlan` → `membership_plan`.

    Es la única forma de derivar nombres de módulo, fichero y prueba a partir del
    nombre de una entidad; todo el motor la comparte para que el generador y el
    revisor no discrepen sobre cómo se llama un fichero.
    """
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index and not name[index - 1].isupper():
            out.append("_")
        out.append(char.lower())
    return re.sub(r"_{2,}", "_", "".join(out).replace("-", "_").replace(" ", "_"))


def table_name_for(entity_name: str) -> str:
    """`MembershipPlan` → `membership_plans`.

    Fuente única del nombre de tabla. Es crítico que lo sea: el modelo ORM, el DDL,
    las rutas REST y las claves foráneas se derivan todos de aquí, y si dos de ellos
    pluralizaran distinto el esquema generado no arrancaría.
    """
    base = snake_case(entity_name)
    if base.endswith(("s", "x", "z")):
        return f"{base}es"
    if base.endswith("y"):
        return f"{base[:-1]}ies"
    return f"{base}s"


@dataclass(frozen=True, slots=True)
class SemVer:
    """Versión semántica reducida (mayor.menor.parche)."""

    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, value: str) -> SemVer:
        parts = value.strip().split(".")
        if len(parts) > 3 or not all(part.isdigit() for part in parts) or not parts[0]:
            raise ValidationError(f"Versión semántica inválida: {value!r}")
        numbers = [int(part) for part in parts] + [0] * (3 - len(parts))
        return cls(*numbers)

    def is_compatible_with(self, other: SemVer) -> bool:
        """Compatibilidad al estilo caret: misma versión mayor y no anterior."""
        return self.major == other.major and (self.minor, self.patch) >= (
            other.minor,
            other.patch,
        )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class BusinessDomain(StrEnum):
    """Dominio de negocio detectado por el analista de requisitos."""

    GYM = "gym"
    RETAIL = "retail"
    RESTAURANT = "restaurant"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    LOGISTICS = "logistics"
    REAL_ESTATE = "real_estate"
    PROFESSIONAL_SERVICES = "professional_services"
    ECOMMERCE = "ecommerce"
    GENERIC = "generic"


@dataclass(frozen=True, slots=True)
class TechStack:
    """Pila tecnológica elegida por el arquitecto para un proyecto generado."""

    backend: str = "fastapi"
    frontend: str = "nextjs"
    database: str = "postgresql"
    cache: str = "redis"
    runtime: str = "docker"

    def as_dict(self) -> dict[str, str]:
        return {
            "backend": self.backend,
            "frontend": self.frontend,
            "database": self.database,
            "cache": self.cache,
            "runtime": self.runtime,
        }


@dataclass(frozen=True, slots=True)
class Artifact:
    """Fichero generado por un agente, referenciado por ruta relativa."""

    path: str
    content: str
    language: str = "text"

    def __post_init__(self) -> None:
        path = self.path.strip().lstrip("/")
        if not path:
            raise ValidationError("La ruta del artefacto no puede estar vacía")
        if ".." in path.split("/"):
            raise ValidationError(f"Ruta de artefacto insegura: {self.path!r}")
        object.__setattr__(self, "path", path)

    @property
    def size_bytes(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class ClarifyingQuestion:
    """Pregunta que el analista necesita responder antes de especificar."""

    id: str
    text: str
    rationale: str = ""
    options: tuple[str, ...] = field(default_factory=tuple)
    required: bool = True

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValidationError("La pregunta de aclaración no puede estar vacía")
