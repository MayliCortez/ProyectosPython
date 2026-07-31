"""Registro consultable de módulos disponibles."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from factory.catalog.definitions import STANDARD_MODULES
from factory.catalog.manifest import ModuleCategory, ModuleManifest
from factory.domain.errors import NotFoundError, ValidationError


class ModuleCatalog:
    """Índice de manifiestos con validación del grafo de dependencias.

    La validación ocurre en la construcción: un catálogo mal formado (dependencias
    inexistentes, ciclos, conflictos incoherentes) falla al arrancar el proceso y no
    a mitad de una construcción.
    """

    def __init__(self, manifests: Iterable[ModuleManifest]) -> None:
        self._by_key: dict[str, ModuleManifest] = {}
        for manifest in manifests:
            if manifest.key in self._by_key:
                raise ValidationError(f"Módulo duplicado en el catálogo: {manifest.key!r}")
            self._by_key[manifest.key] = manifest
        self._validate_graph()

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get(self, key: str) -> ModuleManifest:
        manifest = self._by_key.get(key)
        if manifest is None:
            raise NotFoundError(f"El módulo {key!r} no existe en el catálogo")
        return manifest

    def try_get(self, key: str) -> ModuleManifest | None:
        return self._by_key.get(key)

    def has(self, key: str) -> bool:
        return key in self._by_key

    def all(self) -> list[ModuleManifest]:
        return sorted(self._by_key.values(), key=lambda m: (m.category, m.key))

    def by_category(self, category: ModuleCategory) -> list[ModuleManifest]:
        return [m for m in self.all() if m.category is category]

    def keys(self) -> set[str]:
        return set(self._by_key)

    def dependents_of(self, key: str) -> list[ModuleManifest]:
        """Módulos que dejarían de funcionar si se elimina `key`."""
        return [m for m in self.all() if key in m.depends_on]

    def search(self, query: str) -> list[ModuleManifest]:
        """Búsqueda sencilla por clave, nombre o descripción."""
        needle = query.strip().lower()
        if not needle:
            return self.all()
        return [
            m
            for m in self.all()
            if needle in m.key or needle in m.name.lower() or needle in m.description.lower()
        ]

    # ── Validación del grafo ──────────────────────────────────────────────────

    def _validate_graph(self) -> None:
        known = set(self._by_key)
        for manifest in self._by_key.values():
            missing = set(manifest.depends_on) - known
            if missing:
                raise ValidationError(
                    f"El módulo {manifest.key!r} depende de módulos inexistentes: "
                    f"{sorted(missing)}",
                    details={"module": manifest.key, "missing": sorted(missing)},
                )
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        """Detecta ciclos con una exploración en profundidad con marcas de color."""
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(key: str, trail: list[str]) -> None:
            if key in visited:
                return
            if key in visiting:
                cycle = " → ".join([*trail, key])
                raise ValidationError(
                    f"Ciclo de dependencias entre módulos: {cycle}",
                    details={"cycle": [*trail, key]},
                )
            visiting.add(key)
            for dependency in self._by_key[key].depends_on:
                walk(dependency, [*trail, key])
            visiting.discard(key)
            visited.add(key)

        for key in self._by_key:
            walk(key, [])


@lru_cache(maxsize=1)
def get_catalog() -> ModuleCatalog:
    """Catálogo estándar de la plataforma, construido una sola vez por proceso."""
    return ModuleCatalog(STANDARD_MODULES)
