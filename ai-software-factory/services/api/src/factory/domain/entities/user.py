"""Organizaciones y usuarios: la raíz multiempresa de todo el modelo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from factory.domain.errors import PermissionDeniedError, ValidationError
from factory.domain.value_objects import Email, Slug, new_id, utcnow


class UserRole(StrEnum):
    """Rol dentro de la organización, de mayor a menor privilegio."""

    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]

    def can(self, required: UserRole) -> bool:
        """Un rol satisface a otro si su rango es igual o superior."""
        return self.rank >= required.rank


_ROLE_RANK: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.DEVELOPER: 1,
    UserRole.ADMIN: 2,
    UserRole.OWNER: 3,
}


@dataclass(slots=True)
class Organization:
    """Tenant. Toda entidad raíz cuelga de una organización."""

    name: str
    slug: Slug
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    max_projects: int = 100

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("La organización necesita un nombre")

    @classmethod
    def create(cls, name: str) -> Organization:
        return cls(name=name.strip(), slug=Slug(name))


@dataclass(slots=True)
class User:
    """Usuario de la plataforma, siempre ligado a una organización."""

    organization_id: str
    email: Email
    password_hash: str
    full_name: str = ""
    role: UserRole = UserRole.DEVELOPER
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    is_active: bool = True

    def require_role(self, required: UserRole) -> None:
        """Lanza si el usuario no alcanza el rol exigido."""
        if not self.role.can(required):
            raise PermissionDeniedError(
                f"Se requiere el rol '{required}' y el usuario tiene '{self.role}'",
                details={"required": str(required), "actual": str(self.role)},
            )

    def require_same_organization(self, organization_id: str) -> None:
        """Lanza si el recurso pertenece a otra organización."""
        if self.organization_id != organization_id:
            raise PermissionDeniedError("El recurso pertenece a otra organización")
