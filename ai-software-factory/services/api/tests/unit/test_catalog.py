"""Catálogo de módulos: integridad del grafo y garantías del instalador."""

from __future__ import annotations

import pytest

from factory.catalog.catalog import ModuleCatalog, get_catalog
from factory.catalog.installer import ModuleInstaller
from factory.catalog.manifest import ModuleCategory, ModuleManifest
from factory.domain.errors import ModuleDependencyError, NotFoundError, ValidationError
from factory.domain.value_objects import SemVer


@pytest.fixture
def catalog() -> ModuleCatalog:
    return get_catalog()


@pytest.fixture
def installer(catalog: ModuleCatalog) -> ModuleInstaller:
    return ModuleInstaller(catalog)


def _manifest(key: str, *, depends: tuple[str, ...] = (), major: int = 1) -> ModuleManifest:
    return ModuleManifest(
        key=key,
        name=key.title(),
        description=f"Módulo {key}",
        category=ModuleCategory.CORE,
        version=SemVer(major, 0, 0),
        depends_on=depends,
    )


class TestCatalogo:
    def test_el_catalogo_estandar_trae_los_diecinueve_modulos(self, catalog: ModuleCatalog) -> None:
        assert len(catalog.all()) == 19

    def test_todas_las_dependencias_existen(self, catalog: ModuleCatalog) -> None:
        keys = catalog.keys()
        for manifest in catalog.all():
            assert set(manifest.depends_on) <= keys, manifest.key

    def test_modulo_inexistente_falla(self, catalog: ModuleCatalog) -> None:
        with pytest.raises(NotFoundError):
            catalog.get("no-existe")

    def test_busqueda_por_texto(self, catalog: ModuleCatalog) -> None:
        assert any(m.key == "pagos" for m in catalog.search("pago"))

    def test_dependientes_de_un_modulo(self, catalog: ModuleCatalog) -> None:
        dependientes = {m.key for m in catalog.dependents_of("users")}
        assert "login" in dependientes

    def test_clave_duplicada_falla(self) -> None:
        with pytest.raises(ValidationError, match="duplicado"):
            ModuleCatalog([_manifest("a"), _manifest("a")])

    def test_dependencia_inexistente_falla(self) -> None:
        with pytest.raises(ValidationError, match="inexistentes"):
            ModuleCatalog([_manifest("a", depends=("fantasma",))])

    def test_ciclo_de_dependencias_falla(self) -> None:
        with pytest.raises(ValidationError, match="Ciclo"):
            ModuleCatalog([_manifest("a", depends=("b",)), _manifest("b", depends=("a",))])

    def test_manifiesto_no_puede_depender_de_si_mismo(self) -> None:
        with pytest.raises(ValidationError):
            _manifest("a", depends=("a",))


class TestInstalacion:
    def test_arrastra_las_dependencias(self, installer: ModuleInstaller) -> None:
        plan = installer.plan_install([], ["reservas"])
        # reservas → agenda → users
        assert set(plan.resulting) >= {"reservas", "agenda", "users"}
        assert plan.warnings

    def test_el_orden_es_topologico(self, installer: ModuleInstaller) -> None:
        plan = installer.plan_install([], ["tienda"])
        orden = list(plan.resulting)
        assert orden.index("users") < orden.index("inventory")
        assert orden.index("billing") < orden.index("pagos")
        assert orden.index("pagos") < orden.index("tienda")

    def test_instalar_lo_ya_instalado_no_cambia_nada(self, installer: ModuleInstaller) -> None:
        primero = installer.plan_install([], ["users"])
        segundo = installer.plan_install(list(primero.resulting), ["users"])
        assert segundo.added == ()
        assert segundo.is_noop

    def test_modulo_inexistente_falla(self, installer: ModuleInstaller) -> None:
        with pytest.raises(NotFoundError):
            installer.plan_install([], ["modulo-fantasma"])

    def test_la_salida_es_estable(self, installer: ModuleInstaller) -> None:
        primero = installer.plan_install([], ["tienda", "crm"])
        segundo = installer.plan_install([], ["crm", "tienda"])
        assert primero.resulting == segundo.resulting

    def test_conflicto_declarado_falla(self) -> None:
        catalog = ModuleCatalog(
            [
                _manifest("base"),
                ModuleManifest(
                    key="alfa",
                    name="Alfa",
                    description="",
                    category=ModuleCategory.CORE,
                    version=SemVer(1),
                    conflicts_with=("beta",),
                ),
                _manifest("beta"),
            ]
        )
        with pytest.raises(ModuleDependencyError, match="incompatible"):
            ModuleInstaller(catalog).plan_install([], ["alfa", "beta"])


class TestEliminacion:
    def test_no_se_elimina_algo_de_lo_que_otros_dependen(self, installer: ModuleInstaller) -> None:
        instalados = list(installer.plan_install([], ["reservas"]).resulting)
        with pytest.raises(ModuleDependencyError, match="dependen"):
            installer.plan_remove(instalados, ["agenda"])

    def test_cascada_elimina_a_los_dependientes(self, installer: ModuleInstaller) -> None:
        instalados = list(installer.plan_install([], ["reservas"]).resulting)
        plan = installer.plan_remove(instalados, ["agenda"], cascade=True)
        assert "reservas" in plan.removed
        assert "agenda" in plan.removed
        assert "users" in plan.resulting

    def test_los_modulos_del_nucleo_no_se_eliminan(self, installer: ModuleInstaller) -> None:
        instalados = list(installer.plan_install([], ["login"]).resulting)
        with pytest.raises(ModuleDependencyError, match="núcleo"):
            installer.plan_remove(instalados, ["users"])

    def test_eliminar_lo_no_instalado_falla(self, installer: ModuleInstaller) -> None:
        with pytest.raises(ModuleDependencyError, match="no está instalado"):
            installer.plan_remove(["users"], ["crm"])

    def test_eliminar_una_hoja_no_afecta_al_resto(self, installer: ModuleInstaller) -> None:
        instalados = list(installer.plan_install([], ["reservas", "crm"]).resulting)
        plan = installer.plan_remove(instalados, ["crm"])
        assert plan.removed == ("crm",)
        assert "reservas" in plan.resulting
        assert "agenda" in plan.resulting


class TestActualizacion:
    def test_actualizacion_compatible(self, installer: ModuleInstaller) -> None:
        instalados = list(installer.plan_install([], ["crm"]).resulting)
        plan = installer.plan_upgrade(instalados, "crm", SemVer(1, 2, 0))
        assert set(plan.resulting) == set(instalados)

    def test_salto_de_version_mayor_falla(self, installer: ModuleInstaller) -> None:
        instalados = list(installer.plan_install([], ["crm"]).resulting)
        with pytest.raises(ModuleDependencyError, match="no es compatible"):
            installer.plan_upgrade(instalados, "crm", SemVer(2, 0, 0))

    def test_actualizar_lo_no_instalado_falla(self, installer: ModuleInstaller) -> None:
        with pytest.raises(ModuleDependencyError, match="no está instalado"):
            installer.plan_upgrade(["users"], "crm", SemVer(1, 1, 0))
