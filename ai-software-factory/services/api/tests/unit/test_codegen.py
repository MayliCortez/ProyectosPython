"""Generación de código: los artefactos son válidos, completos y deterministas."""

from __future__ import annotations

import ast
import io
import json
import zipfile

import pytest

from factory.catalog.catalog import get_catalog
from factory.codegen.blueprint import Blueprint
from factory.codegen.bundler import bundle_artifacts
from factory.codegen.renderers import (
    render_backend,
    render_ci,
    render_database,
    render_deployment,
    render_docs,
    render_frontend,
    render_tests,
)
from factory.domain.entities import Project
from factory.domain.entities.specification import (
    DataEntity,
    DataField,
    Endpoint,
    Specification,
)
from factory.domain.value_objects import Artifact


@pytest.fixture
def blueprint() -> Blueprint:
    project = Project.create(
        organization_id="org", name="Gimnasio Titán", prompt="Sistema para un gimnasio"
    )
    specification = Specification(
        project_id=project.id,
        requirements_id="req",
        entities=[
            DataEntity(
                name="Member",
                description="Socio del gimnasio",
                fields=(
                    DataField(name="full_name"),
                    DataField(name="email", type="email", unique=True),
                    DataField(name="joined_on", type="date"),
                    DataField(name="is_active", type="boolean", required=False),
                ),
            ),
            DataEntity(
                name="Booking",
                description="Reserva de clase",
                fields=(
                    DataField(name="member_id", type="integer", references="Member"),
                    DataField(name="starts_at", type="datetime"),
                    DataField(name="price", type="decimal", required=False),
                ),
            ),
        ],
        endpoints=[Endpoint(method="GET", path="/members", summary="Listar socios")],
        modules=["users", "login", "dashboard"],
        pages=["/"],
    )
    catalog = get_catalog()
    return Blueprint(
        project=project,
        specification=specification,
        modules=tuple(catalog.get(key) for key in specification.modules),
    )


def _by_path(artifacts: list[Artifact]) -> dict[str, Artifact]:
    return {artifact.path: artifact for artifact in artifacts}


class TestBackend:
    def test_todo_el_python_generado_compila(self, blueprint: Blueprint) -> None:
        for artifact in render_backend(blueprint):
            if artifact.path.endswith(".py"):
                ast.parse(artifact.content, filename=artifact.path)

    def test_hay_un_router_por_entidad(self, blueprint: Blueprint) -> None:
        paths = _by_path(render_backend(blueprint))
        assert "backend/app/routers/member.py" in paths
        assert "backend/app/routers/booking.py" in paths

    def test_el_arranque_monta_todos_los_routers(self, blueprint: Blueprint) -> None:
        main = _by_path(render_backend(blueprint))["backend/app/main.py"].content
        assert "member.router" in main
        assert "booking.router" in main
        assert "/health" in main

    def test_los_modelos_reflejan_los_campos(self, blueprint: Blueprint) -> None:
        models = _by_path(render_backend(blueprint))["backend/app/models.py"].content
        assert "class Member(Base)" in models
        assert '__tablename__ = "members"' in models
        assert "unique=True" in models
        assert 'ForeignKey("members.id"' in models

    def test_las_dependencias_de_los_modulos_llegan_a_requirements(
        self, blueprint: Blueprint
    ) -> None:
        requirements = _by_path(render_backend(blueprint))["backend/requirements.txt"].content
        assert "fastapi>=0.115" in requirements
        # El módulo `login` declara pyjwt.
        assert "pyjwt" in requirements


class TestBaseDeDatos:
    def test_las_tablas_se_crean_en_orden_de_dependencia(self, blueprint: Blueprint) -> None:
        schema = _by_path(render_database(blueprint))["database/schema.sql"].content
        assert schema.index("CREATE TABLE IF NOT EXISTS members") < schema.index(
            "CREATE TABLE IF NOT EXISTS bookings"
        )

    def test_las_claves_foraneas_se_indexan(self, blueprint: Blueprint) -> None:
        schema = _by_path(render_database(blueprint))["database/schema.sql"].content
        assert "idx_bookings_member_id" in schema

    def test_la_migracion_inicial_compila(self, blueprint: Blueprint) -> None:
        migration = _by_path(render_database(blueprint))[
            "backend/migrations/versions/0001_initial.py"
        ]
        ast.parse(migration.content)


class TestCoherenciaDeNombres:
    """Todo lo generado debe coincidir en cómo se llama cada tabla.

    Es la clase de fallo más cara del generador: si el DDL crea `membershipplans`
    y la clave foránea apunta a `membership_plans`, el proyecto entregado no
    arranca. Estas pruebas cruzan las cuatro fuentes que nombran una tabla.
    """

    @pytest.fixture
    def compuesta(self) -> Blueprint:
        project = Project.create(organization_id="org", name="Gimnasio")
        specification = Specification(
            project_id=project.id,
            requirements_id="req",
            entities=[
                DataEntity(name="MembershipPlan", fields=(DataField(name="name"),)),
                DataEntity(
                    name="Membership",
                    fields=(
                        DataField(name="plan_id", type="integer", references="MembershipPlan"),
                    ),
                ),
            ],
        )
        return Blueprint(project=project, specification=specification)

    def test_el_ddl_y_la_clave_foranea_usan_el_mismo_nombre(self, compuesta: Blueprint) -> None:
        schema = _by_path(render_database(compuesta))["database/schema.sql"].content
        assert "CREATE TABLE IF NOT EXISTS membership_plans" in schema
        assert "REFERENCES membership_plans(id)" in schema
        assert "membershipplans" not in schema

    def test_el_modelo_orm_coincide_con_el_ddl(self, compuesta: Blueprint) -> None:
        models = _by_path(render_backend(compuesta))["backend/app/models.py"].content
        assert '__tablename__ = "membership_plans"' in models
        assert 'ForeignKey("membership_plans.id"' in models

    def test_la_migracion_coincide_con_el_ddl(self, compuesta: Blueprint) -> None:
        migration = _by_path(render_database(compuesta))[
            "backend/migrations/versions/0001_initial.py"
        ].content
        assert '"membership_plans"' in migration
        assert 'sa.ForeignKey("membership_plans.id"' in migration

    def test_las_rutas_rest_usan_el_mismo_nombre(self, compuesta: Blueprint) -> None:
        router = _by_path(render_backend(compuesta))[
            "backend/app/routers/membership_plan.py"
        ].content
        assert 'prefix="/membership_plans"' in router


class TestFrontend:
    def test_package_json_es_json_valido(self, blueprint: Blueprint) -> None:
        manifest = json.loads(_by_path(render_frontend(blueprint))["frontend/package.json"].content)
        assert manifest["name"] == "gimnasio-titan"
        assert "next" in manifest["dependencies"]

    def test_hay_una_pagina_por_entidad(self, blueprint: Blueprint) -> None:
        paths = _by_path(render_frontend(blueprint))
        assert "frontend/src/app/members/page.tsx" in paths
        assert "frontend/src/app/bookings/page.tsx" in paths

    def test_los_tipos_reflejan_la_especificacion(self, blueprint: Blueprint) -> None:
        types = _by_path(render_frontend(blueprint))["frontend/src/lib/types.ts"].content
        assert "export interface Member" in types
        assert "is_active: boolean | null;" in types

    def test_la_navegacion_incluye_las_paginas_de_los_modulos(self, blueprint: Blueprint) -> None:
        sidebar = _by_path(render_frontend(blueprint))["frontend/src/components/sidebar.tsx"]
        assert "/members" in sidebar.content


class TestPruebasGeneradas:
    def test_las_pruebas_generadas_compilan(self, blueprint: Blueprint) -> None:
        for artifact in render_tests(blueprint):
            ast.parse(artifact.content, filename=artifact.path)

    def test_hay_una_prueba_por_entidad(self, blueprint: Blueprint) -> None:
        paths = _by_path(render_tests(blueprint))
        assert "backend/tests/test_member.py" in paths
        assert "backend/tests/test_booking.py" in paths

    def test_la_carga_util_resuelve_las_claves_foraneas(self, blueprint: Blueprint) -> None:
        """Una entidad con clave foránea crea primero su padre y reutiliza su id."""
        booking = _by_path(render_tests(blueprint))["backend/tests/test_booking.py"].content
        assert 'await client.post(\n        "/api/v1/members"' in booking
        assert 'ids["Member"] = created.json()["id"]' in booking
        assert '"member_id": ids["Member"],' in booking

    def test_una_entidad_sin_dependencias_no_siembra_nada(self, blueprint: Blueprint) -> None:
        member = _by_path(render_tests(blueprint))["backend/tests/test_member.py"].content
        assert "no depende de ninguna otra entidad" in member

    def test_el_humo_comprueba_las_rutas_por_openapi(self, blueprint: Blueprint) -> None:
        smoke = _by_path(render_tests(blueprint))["backend/tests/test_smoke.py"].content
        assert 'app.openapi()["paths"]' in smoke
        assert '"/api/v1/members" in paths' in smoke
        # Toda prueba debe ser asíncrona: la fixture de base de datos lo es.
        assert "def test_" in smoke and "\ndef test_" not in smoke


class TestDespliegue:
    def test_estan_todos_los_artefactos_de_despliegue(self, blueprint: Blueprint) -> None:
        paths = _by_path(render_deployment(blueprint))
        assert {"docker-compose.yml", "backend/Dockerfile", "frontend/Dockerfile"} <= set(paths)
        assert ".env.example" in paths
        assert "install.sh" in paths

    def test_las_variables_de_los_modulos_llegan_al_entorno(self, blueprint: Blueprint) -> None:
        env = _by_path(render_deployment(blueprint))[".env.example"].content
        assert "DATABASE_URL=" in env
        assert "JWT_SECRET=" in env  # lo aporta el módulo `login`

    def test_el_pipeline_de_ci_cubre_backend_frontend_y_despliegue(
        self, blueprint: Blueprint
    ) -> None:
        workflow = _by_path(render_ci(blueprint))[".github/workflows/ci.yml"].content
        assert "backend:" in workflow
        assert "frontend:" in workflow
        assert "deploy:" in workflow


class TestDocumentacion:
    def test_el_readme_describe_el_proyecto(self, blueprint: Blueprint) -> None:
        readme = _by_path(render_docs(blueprint))["README.md"].content
        assert "# Gimnasio Titán" in readme
        assert "install.sh" in readme

    def test_la_referencia_lista_los_endpoints(self, blueprint: Blueprint) -> None:
        api = _by_path(render_docs(blueprint))["docs/API.md"].content
        assert "/api/v1/members" in api

    def test_el_modelo_de_datos_documenta_las_relaciones(self, blueprint: Blueprint) -> None:
        model = _by_path(render_docs(blueprint))["docs/DATA_MODEL.md"].content
        assert "Booking --> Member" in model


class TestEmpaquetado:
    def _artifacts(self, blueprint: Blueprint) -> list[Artifact]:
        return [
            *render_backend(blueprint),
            *render_frontend(blueprint),
            *render_deployment(blueprint),
        ]

    def test_el_zip_contiene_todos_los_ficheros(self, blueprint: Blueprint) -> None:
        artifacts = self._artifacts(blueprint)
        bundle = bundle_artifacts(artifacts, root="proyecto")
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            names = archive.namelist()
        assert len(names) == len(artifacts)
        assert all(name.startswith("proyecto/") for name in names)

    def test_el_empaquetado_es_determinista(self, blueprint: Blueprint) -> None:
        artifacts = self._artifacts(blueprint)
        assert bundle_artifacts(artifacts) == bundle_artifacts(list(reversed(artifacts)))

    def test_los_scripts_conservan_permiso_de_ejecucion(self, blueprint: Blueprint) -> None:
        bundle = bundle_artifacts(render_deployment(blueprint))
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            info = archive.getinfo("install.sh")
        assert (info.external_attr >> 16) & 0o111
