"""Reglas del dominio: objetos de valor, máquinas de estados e invariantes."""

from __future__ import annotations

import pytest

from factory.domain.entities import Build, BuildStage, BuildStatus, Project, ProjectStatus
from factory.domain.entities.conversation import Conversation, MessageRole
from factory.domain.entities.specification import (
    DataEntity,
    DataField,
    Endpoint,
    Specification,
)
from factory.domain.entities.user import User, UserRole
from factory.domain.errors import (
    InvalidTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from factory.domain.value_objects import (
    Artifact,
    ClarifyingQuestion,
    Email,
    SemVer,
    Slug,
    slugify,
)


class TestValueObjects:
    def test_email_se_normaliza(self) -> None:
        assert str(Email("  Persona@Example.COM ")) == "persona@example.com"

    @pytest.mark.parametrize("value", ["sin-arroba", "a@b", "@example.com", "a b@c.com"])
    def test_email_invalido_falla(self, value: str) -> None:
        with pytest.raises(ValidationError):
            Email(value)

    def test_slug_traduce_acentos_y_espacios(self) -> None:
        assert str(Slug("Sistema de Gestión Académica")) == "sistema-de-gestion-academica"

    def test_slug_vacio_falla(self) -> None:
        with pytest.raises(ValidationError):
            Slug("!!!")

    def test_slugify_colapsa_separadores(self) -> None:
        assert slugify("  Hola   ---  Mundo  ") == "hola-mundo"

    def test_semver_compatibilidad_por_version_mayor(self) -> None:
        assert SemVer(1, 3, 0).is_compatible_with(SemVer(1, 2, 9))
        assert not SemVer(2, 0, 0).is_compatible_with(SemVer(1, 9, 9))
        assert not SemVer(1, 1, 0).is_compatible_with(SemVer(1, 2, 0))

    @pytest.mark.parametrize("value", ["", "1.2.3.4", "a.b", "1.x"])
    def test_semver_invalida_falla(self, value: str) -> None:
        with pytest.raises(ValidationError):
            SemVer.parse(value)

    def test_artefacto_rechaza_rutas_con_salto_de_directorio(self) -> None:
        with pytest.raises(ValidationError):
            Artifact(path="../../etc/passwd", content="x")

    def test_artefacto_normaliza_barra_inicial(self) -> None:
        assert Artifact(path="/app/main.py", content="x").path == "app/main.py"


class TestProject:
    def test_creacion_deriva_slug_y_deja_borrador(self) -> None:
        project = Project.create(organization_id="org", name="Gimnasio Titán")
        assert str(project.slug) == "gimnasio-titan"
        assert project.status is ProjectStatus.DRAFT

    def test_transicion_valida(self) -> None:
        project = Project.create(organization_id="org", name="X")
        project.transition_to(ProjectStatus.GATHERING_REQUIREMENTS)
        assert project.status is ProjectStatus.GATHERING_REQUIREMENTS

    def test_transicion_invalida_falla(self) -> None:
        project = Project.create(organization_id="org", name="X")
        with pytest.raises(InvalidTransitionError):
            project.transition_to(ProjectStatus.DEPLOYED)

    def test_transicion_a_si_mismo_no_hace_nada(self) -> None:
        project = Project.create(organization_id="org", name="X")
        project.transition_to(ProjectStatus.DRAFT)
        assert project.status is ProjectStatus.DRAFT

    def test_archivado_es_terminal(self) -> None:
        project = Project.create(organization_id="org", name="X")
        project.transition_to(ProjectStatus.ARCHIVED)
        with pytest.raises(InvalidTransitionError):
            project.transition_to(ProjectStatus.GATHERING_REQUIREMENTS)

    def test_is_editable_marca_los_estados_en_curso(self) -> None:
        project = Project.create(organization_id="org", name="X")
        assert project.is_editable

        project.transition_to(ProjectStatus.GATHERING_REQUIREMENTS)
        project.transition_to(ProjectStatus.SPECIFIED)
        project.transition_to(ProjectStatus.BUILDING)
        # El arquitecto sí fija módulos aquí; la restricción es del caso de uso.
        assert not project.is_editable
        project.set_modules(["users"])
        assert project.module_keys == ["users"]

    def test_modulos_sin_duplicados_y_en_orden(self) -> None:
        project = Project.create(organization_id="org", name="X")
        project.set_modules(["users", "login", "users"])
        assert project.module_keys == ["users", "login"]


class TestConversation:
    def test_responder_retira_la_pregunta_pendiente(self) -> None:
        conversation = Conversation(project_id="p1")
        conversation.ask([ClarifyingQuestion(id="q1", text="¿Cuántos socios?")])
        assert conversation.has_blocking_questions

        conversation.answer("q1", "Unos 500")
        assert not conversation.has_blocking_questions
        assert conversation.answers["q1"] == "Unos 500"

    def test_responder_pregunta_desconocida_falla(self) -> None:
        conversation = Conversation(project_id="p1")
        with pytest.raises(ValidationError):
            conversation.answer("inexistente", "respuesta")

    def test_no_se_duplican_preguntas(self) -> None:
        conversation = Conversation(project_id="p1")
        question = ClarifyingQuestion(id="q1", text="¿Aforo?")
        conversation.ask([question])
        conversation.ask([question])
        assert len(conversation.pending_questions) == 1

    def test_el_prompt_solo_recoge_mensajes_del_usuario(self) -> None:
        conversation = Conversation(project_id="p1")
        conversation.add_message(MessageRole.USER, "Quiero un gimnasio")
        conversation.add_message(MessageRole.ASSISTANT, "De acuerdo")
        conversation.add_message(MessageRole.USER, "Con reservas")
        assert conversation.user_prompt == "Quiero un gimnasio\n\nCon reservas"

    def test_mensaje_vacio_falla(self) -> None:
        conversation = Conversation(project_id="p1")
        with pytest.raises(ValidationError):
            conversation.add_message(MessageRole.USER, "   ")


class TestBuild:
    def _build(self) -> Build:
        return Build(
            project_id="p1",
            stages=[
                BuildStage(name="a", agent="agent_a"),
                BuildStage(name="b", agent="agent_b"),
            ],
        )

    def test_progreso_avanza_con_las_etapas(self) -> None:
        build = self._build()
        assert build.progress == 0.0
        build.stage("a").succeed()
        assert build.progress == 0.5
        build.stage("b").skip()
        assert build.progress == 1.0

    def test_ciclo_de_vida_completo(self) -> None:
        build = self._build()
        build.start()
        assert build.status is BuildStatus.RUNNING
        build.succeed(bundle_key="k")
        assert build.status is BuildStatus.SUCCEEDED
        assert build.is_terminal

    def test_no_se_puede_iniciar_dos_veces(self) -> None:
        build = self._build()
        build.start()
        with pytest.raises(InvalidTransitionError):
            build.start()

    def test_cancelar_salta_las_etapas_pendientes(self) -> None:
        build = self._build()
        build.start()
        build.cancel()
        assert all(stage.status.value == "skipped" for stage in build.stages)

    def test_artefactos_de_igual_ruta_se_reemplazan(self) -> None:
        build = self._build()
        build.add_artifacts([Artifact("a.py", "uno")])
        build.add_artifacts([Artifact("a.py", "dos"), Artifact("b.py", "tres")])
        assert len(build.artifacts) == 2
        assert next(a for a in build.artifacts if a.path == "a.py").content == "dos"


class TestSpecification:
    def test_valida_referencias_entre_entidades(self) -> None:
        specification = Specification(
            project_id="p1",
            requirements_id="r1",
            entities=[
                DataEntity(name="Member", fields=(DataField(name="full_name"),)),
                DataEntity(
                    name="Booking",
                    fields=(DataField(name="member_id", type="integer", references="Member"),),
                ),
            ],
        )
        specification.validate()

    def test_referencia_desconocida_falla(self) -> None:
        specification = Specification(
            project_id="p1",
            requirements_id="r1",
            entities=[
                DataEntity(
                    name="Booking",
                    fields=(DataField(name="member_id", type="integer", references="Fantasma"),),
                )
            ],
        )
        with pytest.raises(ValidationError, match="Fantasma"):
            specification.validate()

    def test_entidades_duplicadas_fallan(self) -> None:
        entity = DataEntity(name="Member", fields=(DataField(name="a"),))
        specification = Specification(
            project_id="p1", requirements_id="r1", entities=[entity, entity]
        )
        with pytest.raises(ValidationError, match="duplicadas"):
            specification.validate()

    @pytest.mark.parametrize(
        ("nombre", "tabla"),
        [("Member", "members"), ("Class", "classes"), ("Category", "categories")],
    )
    def test_pluralizacion_de_tablas(self, nombre: str, tabla: str) -> None:
        assert DataEntity(name=nombre, fields=(DataField(name="x"),)).table_name == tabla

    def test_endpoint_rechaza_metodo_no_soportado(self) -> None:
        with pytest.raises(ValidationError):
            Endpoint(method="TRACE", path="/x")

    def test_endpoint_exige_ruta_absoluta(self) -> None:
        with pytest.raises(ValidationError):
            Endpoint(method="GET", path="members")


class TestUser:
    def test_jerarquia_de_roles(self) -> None:
        assert UserRole.OWNER.can(UserRole.VIEWER)
        assert not UserRole.VIEWER.can(UserRole.ADMIN)

    def test_rol_insuficiente_falla(self) -> None:
        user = User(organization_id="org", email=Email("a@b.com"), password_hash="x")
        user.role = UserRole.VIEWER
        with pytest.raises(PermissionDeniedError):
            user.require_role(UserRole.ADMIN)

    def test_organizacion_ajena_falla(self) -> None:
        user = User(organization_id="org-1", email=Email("a@b.com"), password_hash="x")
        with pytest.raises(PermissionDeniedError):
            user.require_same_organization("org-2")
