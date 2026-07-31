"""Proyecto: la entidad raíz del ciclo de vida de generación."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from factory.domain.errors import InvalidTransitionError, ValidationError
from factory.domain.value_objects import (
    BusinessDomain,
    Slug,
    TechStack,
    new_id,
    utcnow,
)


class ProjectStatus(StrEnum):
    """Estados por los que pasa un proyecto desde la idea hasta el despliegue."""

    DRAFT = "draft"
    GATHERING_REQUIREMENTS = "gathering_requirements"
    SPECIFIED = "specified"
    BUILDING = "building"
    BUILT = "built"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ARCHIVED = "archived"


#: Transiciones permitidas. Cualquier otra combinación es un error de negocio.
_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.DRAFT: frozenset({ProjectStatus.GATHERING_REQUIREMENTS, ProjectStatus.ARCHIVED}),
    ProjectStatus.GATHERING_REQUIREMENTS: frozenset(
        {ProjectStatus.SPECIFIED, ProjectStatus.FAILED, ProjectStatus.ARCHIVED}
    ),
    ProjectStatus.SPECIFIED: frozenset(
        {
            ProjectStatus.BUILDING,
            ProjectStatus.GATHERING_REQUIREMENTS,
            ProjectStatus.ARCHIVED,
        }
    ),
    ProjectStatus.BUILDING: frozenset({ProjectStatus.BUILT, ProjectStatus.FAILED}),
    ProjectStatus.BUILT: frozenset(
        {
            ProjectStatus.DEPLOYING,
            ProjectStatus.BUILDING,
            ProjectStatus.SPECIFIED,
            ProjectStatus.ARCHIVED,
        }
    ),
    ProjectStatus.DEPLOYING: frozenset({ProjectStatus.DEPLOYED, ProjectStatus.FAILED}),
    ProjectStatus.DEPLOYED: frozenset(
        {
            ProjectStatus.BUILDING,
            ProjectStatus.DEPLOYING,
            ProjectStatus.SPECIFIED,
            ProjectStatus.ARCHIVED,
        }
    ),
    # Desde un fallo se puede reintentar la especificación o la construcción.
    ProjectStatus.FAILED: frozenset(
        {
            ProjectStatus.GATHERING_REQUIREMENTS,
            ProjectStatus.SPECIFIED,
            ProjectStatus.BUILDING,
            ProjectStatus.ARCHIVED,
        }
    ),
    ProjectStatus.ARCHIVED: frozenset(),
}


@dataclass(slots=True)
class Project:
    """Un software en construcción: su estado, su pila y sus módulos activos."""

    organization_id: str
    name: str
    slug: Slug
    prompt: str = ""
    business_domain: BusinessDomain = BusinessDomain.GENERIC
    status: ProjectStatus = ProjectStatus.DRAFT
    tech_stack: TechStack = field(default_factory=TechStack)
    module_keys: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    live_url: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("El proyecto necesita un nombre")

    @classmethod
    def create(
        cls,
        *,
        organization_id: str,
        name: str,
        prompt: str = "",
        created_by: str | None = None,
    ) -> Project:
        """Crea un proyecto en borrador a partir del nombre y la petición inicial."""
        return cls(
            organization_id=organization_id,
            name=name.strip(),
            slug=Slug(name),
            prompt=prompt.strip(),
            created_by=created_by,
        )

    # ── Máquina de estados ────────────────────────────────────────────────────

    def can_transition_to(self, target: ProjectStatus) -> bool:
        return target in _TRANSITIONS[self.status]

    def transition_to(self, target: ProjectStatus) -> None:
        """Aplica una transición validada; deja constancia en `updated_at`."""
        if target == self.status:
            return
        if not self.can_transition_to(target):
            raise InvalidTransitionError("Project", self.status, target)
        self.status = target
        self.touch()

    def touch(self) -> None:
        self.updated_at = utcnow()

    # ── Módulos ───────────────────────────────────────────────────────────────

    @property
    def is_editable(self) -> bool:
        """Un proyecto en curso de construcción o despliegue no admite cambios."""
        return self.status not in {
            ProjectStatus.BUILDING,
            ProjectStatus.DEPLOYING,
            ProjectStatus.ARCHIVED,
        }

    def set_modules(self, keys: list[str]) -> None:
        """Reemplaza el conjunto de módulos activos (ya resuelto por el instalador).

        La entidad solo garantiza que no haya duplicados. Quién puede cambiarlos y
        cuándo es una política del caso de uso: `ModuleService` la aplica, mientras
        que el arquitecto los fija legítimamente durante la construcción.
        """
        self.module_keys = list(dict.fromkeys(keys))
        self.touch()

    def mark_deployed(self, url: str) -> None:
        """Registra la URL funcional entregada al usuario."""
        self.transition_to(ProjectStatus.DEPLOYED)
        self.live_url = url
