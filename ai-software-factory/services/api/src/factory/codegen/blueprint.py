"""Blueprint: la entrada única de todos los renderizadores.

Reúne en una sola estructura inmutable lo que necesitan los generadores (proyecto,
especificación y módulos ya resueltos) para que cada renderizador sea una función pura
`Blueprint -> list[Artifact]`, trivialmente testeable.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from factory.catalog.manifest import ModuleManifest
from factory.domain.entities import Project
from factory.domain.entities.specification import DataEntity, Endpoint, Specification
from factory.domain.value_objects import TechStack


@dataclass(frozen=True)
class Blueprint:
    """Instantánea consistente de lo que hay que generar."""

    project: Project
    specification: Specification
    modules: tuple[ModuleManifest, ...] = ()

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def slug(self) -> str:
        return str(self.project.slug)

    @property
    def package(self) -> str:
        """Nombre de paquete Python válido derivado del slug."""
        package = self.slug.replace("-", "_")
        return f"app_{package}" if package[0].isdigit() else package

    @property
    def tech_stack(self) -> TechStack:
        return self.specification.tech_stack

    @property
    def entities(self) -> list[DataEntity]:
        return list(self.specification.entities)

    @property
    def endpoints(self) -> list[Endpoint]:
        return list(self.specification.endpoints)

    @cached_property
    def module_keys(self) -> tuple[str, ...]:
        return tuple(module.key for module in self.modules)

    def has_module(self, key: str) -> bool:
        return key in self.module_keys

    @cached_property
    def python_packages(self) -> tuple[str, ...]:
        """Dependencias Python exigidas por los módulos activos, sin duplicados."""
        packages: list[str] = []
        for module in self.modules:
            packages.extend(module.python_packages)
        return tuple(sorted(set(packages)))

    @cached_property
    def npm_packages(self) -> tuple[str, ...]:
        packages: list[str] = []
        for module in self.modules:
            packages.extend(module.npm_packages)
        return tuple(sorted(set(packages)))

    @cached_property
    def env_vars(self) -> tuple[str, ...]:
        """Variables de entorno que el proyecto generado necesita definir."""
        base = ["DATABASE_URL", "REDIS_URL", "SECRET_KEY", "ENVIRONMENT"]
        for module in self.modules:
            base.extend(module.env_vars)
        return tuple(dict.fromkeys(base))

    @cached_property
    def pages(self) -> tuple[tuple[str, str, str], ...]:
        """Rutas del frontend: `(ruta, título, icono)`, con las de los módulos incluidas."""
        pages: list[tuple[str, str, str]] = []
        for module in self.modules:
            for page in module.pages:
                pages.append((page.route, page.title, page.icon))
        for route in self.specification.pages:
            title = route.strip("/").replace("-", " ").title() or "Inicio"
            candidate = (route, title, "square")
            if all(existing[0] != route for existing in pages):
                pages.append(candidate)
        return tuple(dict.fromkeys(pages))
