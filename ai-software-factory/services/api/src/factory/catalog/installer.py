"""Instalador de módulos: resuelve dependencias y protege la integridad del sistema.

Es la pieza que garantiza el requisito de que instalar, actualizar o eliminar un
módulo no rompa el resto: toda operación se planifica primero y solo se aplica si el
estado resultante sigue siendo consistente.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from factory.catalog.catalog import ModuleCatalog
from factory.catalog.manifest import ModuleManifest
from factory.domain.errors import ModuleDependencyError
from factory.domain.value_objects import SemVer


@dataclass(frozen=True, slots=True)
class InstallPlan:
    """Resultado de planificar una operación sobre el conjunto de módulos."""

    #: Conjunto final de módulos activos, en orden topológico de instalación.
    resulting: tuple[str, ...]
    #: Módulos que se añaden respecto al estado previo.
    added: tuple[str, ...] = field(default_factory=tuple)
    #: Módulos que se retiran respecto al estado previo.
    removed: tuple[str, ...] = field(default_factory=tuple)
    #: Avisos no bloqueantes (por ejemplo, dependencias arrastradas).
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_noop(self) -> bool:
        return not self.added and not self.removed


class ModuleInstaller:
    """Planifica altas, bajas y actualizaciones sobre un conjunto de módulos."""

    def __init__(self, catalog: ModuleCatalog) -> None:
        self._catalog = catalog

    # ── Instalación ───────────────────────────────────────────────────────────

    def plan_install(self, installed: list[str], requested: list[str]) -> InstallPlan:
        """Añade `requested` arrastrando sus dependencias, en orden topológico."""
        current = self._normalize(installed)
        target = set(current)
        pulled: list[str] = []

        for key in requested:
            manifest = self._catalog.get(key)
            for dependency in self._dependency_closure(manifest):
                if dependency not in target:
                    target.add(dependency)
                    if dependency != key:
                        pulled.append(dependency)
            target.add(key)

        self._assert_no_conflicts(target)
        self._assert_versions_compatible(target)

        ordered = self._topological_order(target)
        added = tuple(key for key in ordered if key not in current)
        warnings = (
            (f"Se instalarán además las dependencias: {sorted(set(pulled))}",) if pulled else ()
        )
        return InstallPlan(resulting=ordered, added=added, warnings=warnings)

    # ── Eliminación ───────────────────────────────────────────────────────────

    def plan_remove(
        self, installed: list[str], keys: list[str], *, cascade: bool = False
    ) -> InstallPlan:
        """Retira módulos. Sin `cascade`, rechaza quitar algo de lo que otros dependen."""
        current = self._normalize(installed)
        current_set = set(current)
        to_remove: set[str] = set()

        for key in keys:
            manifest = self._catalog.get(key)
            if key not in current_set:
                raise ModuleDependencyError(
                    f"El módulo {key!r} no está instalado",
                    details={"module": key},
                )
            if not manifest.removable:
                raise ModuleDependencyError(
                    f"El módulo {key!r} es parte del núcleo y no se puede eliminar",
                    details={"module": key},
                )
            to_remove.add(key)

        cascaded: list[str] = []
        if cascade:
            changed = True
            while changed:
                changed = False
                for candidate in current_set - to_remove:
                    manifest = self._catalog.get(candidate)
                    if set(manifest.depends_on) & to_remove:
                        if not manifest.removable:
                            raise ModuleDependencyError(
                                f"No se puede eliminar en cascada: {candidate!r} pertenece al "
                                "núcleo y depende de un módulo a retirar",
                                details={"module": candidate},
                            )
                        to_remove.add(candidate)
                        cascaded.append(candidate)
                        changed = True
        else:
            blockers = {
                candidate: sorted(set(self._catalog.get(candidate).depends_on) & to_remove)
                for candidate in current_set - to_remove
                if set(self._catalog.get(candidate).depends_on) & to_remove
            }
            if blockers:
                raise ModuleDependencyError(
                    "Hay módulos instalados que dependen de los que se quieren eliminar: "
                    f"{sorted(blockers)}",
                    details={"blocked_by": blockers},
                )

        target = current_set - to_remove
        ordered = self._topological_order(target)
        warnings = (f"Se eliminarán en cascada: {sorted(cascaded)}",) if cascaded else ()
        return InstallPlan(
            resulting=ordered,
            removed=tuple(sorted(to_remove)),
            warnings=warnings,
        )

    # ── Actualización ─────────────────────────────────────────────────────────

    def plan_upgrade(self, installed: list[str], key: str, target_version: SemVer) -> InstallPlan:
        """Comprueba que subir de versión no rompe a los módulos dependientes."""
        current = self._normalize(installed)
        if key not in current:
            raise ModuleDependencyError(
                f"El módulo {key!r} no está instalado", details={"module": key}
            )
        manifest = self._catalog.get(key)
        if not target_version.is_compatible_with(manifest.version):
            raise ModuleDependencyError(
                f"La versión {target_version} no es compatible con la publicada "
                f"({manifest.version}) para {key!r}",
                details={"module": key, "target": str(target_version)},
            )
        broken = [
            dependent.key
            for dependent in self._catalog.dependents_of(key)
            if dependent.key in current and dependent.version.major < target_version.major
        ]
        if broken:
            raise ModuleDependencyError(
                f"Actualizar {key!r} a {target_version} rompería a {sorted(broken)}",
                details={"module": key, "breaks": sorted(broken)},
            )
        return InstallPlan(resulting=tuple(current))

    # ── Utilidades ────────────────────────────────────────────────────────────

    def resolve(self, keys: list[str]) -> list[ModuleManifest]:
        """Manifiestos del conjunto pedido, con dependencias y en orden de carga."""
        plan = self.plan_install([], keys)
        return [self._catalog.get(key) for key in plan.resulting]

    def _normalize(self, keys: list[str]) -> tuple[str, ...]:
        """Valida que todas las claves existen y elimina duplicados conservando orden."""
        unique = list(dict.fromkeys(keys))
        for key in unique:
            self._catalog.get(key)
        return tuple(unique)

    def _dependency_closure(self, manifest: ModuleManifest) -> list[str]:
        """Todas las dependencias transitivas de un módulo, incluido él mismo."""
        seen: list[str] = []
        stack = [manifest.key]
        while stack:
            key = stack.pop()
            if key in seen:
                continue
            seen.append(key)
            stack.extend(self._catalog.get(key).depends_on)
        return seen

    def _assert_no_conflicts(self, target: set[str]) -> None:
        for key in target:
            manifest = self._catalog.get(key)
            clashing = set(manifest.conflicts_with) & target
            if clashing:
                raise ModuleDependencyError(
                    f"El módulo {key!r} es incompatible con {sorted(clashing)}",
                    details={"module": key, "conflicts": sorted(clashing)},
                )

    def _assert_versions_compatible(self, target: set[str]) -> None:
        for key in target:
            manifest = self._catalog.get(key)
            for dependency_key in manifest.depends_on:
                dependency = self._catalog.get(dependency_key)
                if not manifest.is_compatible_with(dependency):
                    raise ModuleDependencyError(
                        f"{key!r} v{manifest.version} no es compatible con "
                        f"{dependency_key!r} v{dependency.version}",
                        details={"module": key, "dependency": dependency_key},
                    )

    def _topological_order(self, keys: set[str]) -> tuple[str, ...]:
        """Ordena por dependencias; ante empate, alfabéticamente (salida estable)."""
        ordered: list[str] = []
        placed: set[str] = set()

        def place(key: str) -> None:
            if key in placed:
                return
            for dependency in sorted(self._catalog.get(key).depends_on):
                if dependency in keys:
                    place(dependency)
            placed.add(key)
            ordered.append(key)

        for key in sorted(keys):
            place(key)
        return tuple(ordered)
