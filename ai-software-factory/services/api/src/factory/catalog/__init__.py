"""Catálogo de módulos reutilizables y su instalador."""

from factory.catalog.catalog import ModuleCatalog, get_catalog
from factory.catalog.installer import InstallPlan, ModuleInstaller
from factory.catalog.manifest import ModuleCategory, ModuleManifest

__all__ = [
    "InstallPlan",
    "ModuleCatalog",
    "ModuleCategory",
    "ModuleInstaller",
    "ModuleManifest",
    "get_catalog",
]
