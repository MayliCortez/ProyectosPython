"""Estado de instalación de un módulo reutilizable dentro de un proyecto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from factory.domain.errors import InvalidTransitionError
from factory.domain.value_objects import SemVer, new_id, utcnow


class ModuleState(StrEnum):
    INSTALLED = "installed"
    OUTDATED = "outdated"
    REMOVING = "removing"
    REMOVED = "removed"


@dataclass(slots=True)
class ModuleInstallation:
    """Módulo activo en un proyecto, con su versión y su configuración."""

    project_id: str
    module_key: str
    version: SemVer
    state: ModuleState = ModuleState.INSTALLED
    config: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    installed_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def upgrade_to(self, version: SemVer) -> None:
        """Actualiza la versión instalada; solo hacia adelante."""
        if (version.major, version.minor, version.patch) <= (
            self.version.major,
            self.version.minor,
            self.version.patch,
        ):
            raise InvalidTransitionError("ModuleInstallation", str(self.version), str(version))
        self.version = version
        self.state = ModuleState.INSTALLED
        self.updated_at = utcnow()

    def mark_outdated(self) -> None:
        if self.state is ModuleState.INSTALLED:
            self.state = ModuleState.OUTDATED
            self.updated_at = utcnow()

    def mark_removed(self) -> None:
        self.state = ModuleState.REMOVED
        self.updated_at = utcnow()

    @property
    def is_active(self) -> bool:
        return self.state in {ModuleState.INSTALLED, ModuleState.OUTDATED}
