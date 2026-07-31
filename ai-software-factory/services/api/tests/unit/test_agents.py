"""Agentes, pipeline y orquestador."""

from __future__ import annotations

import pytest

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.orchestrator import Orchestrator
from factory.agents.pipeline import Pipeline, PipelineStage, default_pipeline
from factory.agents.registry import AgentRegistry, default_registry
from factory.catalog.catalog import get_catalog
from factory.domain.entities import Build, Conversation, MessageRole, Project
from factory.domain.errors import AgentExecutionError, ValidationError
from factory.infrastructure.events import InMemoryEventBus
from factory.infrastructure.llm.fake import FakeLLMClient, detect_profile


@pytest.fixture
def project() -> Project:
    return Project.create(
        organization_id="org",
        name="Gimnasio Titán",
        prompt="Necesito un sistema para un gimnasio con reservas de clases",
    )


@pytest.fixture
def conversation(project: Project) -> Conversation:
    entity = Conversation(project_id=project.id)
    entity.add_message(MessageRole.USER, project.prompt)
    return entity


@pytest.fixture
def context(project: Project, conversation: Conversation) -> AgentContext:
    return AgentContext(
        project=project,
        conversation=conversation,
        llm=FakeLLMClient(answer_questions=True),
        catalog=get_catalog(),
    )


class _Stub(Agent):
    """Agente de prueba cuyas dependencias se declaran por instancia."""

    key = "stub"
    name = "Agente de prueba"

    def __init__(self, key: str, requires: tuple[str, ...], produces: tuple[str, ...]) -> None:
        self.key = key
        self.name = key
        self.requires = requires
        self.produces = produces
        self.calls = 0

    async def run(self, context: AgentContext) -> AgentResult:
        self.calls += 1
        return AgentResult(produced=dict.fromkeys(self.produces, True))


class _Failing(_Stub):
    async def run(self, context: AgentContext) -> AgentResult:
        raise RuntimeError("fallo simulado")


class TestProveedorDeterminista:
    def test_detecta_el_dominio_por_vocabulario(self) -> None:
        assert detect_profile("necesito un gimnasio con socios").domain.value == "gym"
        assert detect_profile("una tienda online con carrito").domain.value == "ecommerce"
        assert detect_profile("algo indefinido").domain.value == "generic"

    async def test_dos_ejecuciones_devuelven_lo_mismo(self) -> None:
        cliente = FakeLLMClient()
        primero = await cliente.complete_json(
            system="s", prompt="un gimnasio", schema={}, schema_name="requirements"
        )
        segundo = await cliente.complete_json(
            system="s", prompt="un gimnasio", schema={}, schema_name="requirements"
        )
        assert primero.data == segundo.data


class TestAgentes:
    async def test_el_analista_detecta_dominio_e_historias(self, context: AgentContext) -> None:
        agente = default_registry().get("requirements_analyst")
        resultado = await agente.execute(context)
        requisitos = resultado.produced["requirements"]

        assert str(requisitos.business_domain) == "gym"
        assert len(requisitos.stories) >= 3
        assert "reservas" in requisitos.suggested_modules

    async def test_el_analista_pregunta_lo_que_falta(
        self, project: Project, conversation: Conversation
    ) -> None:
        context = AgentContext(
            project=project,
            conversation=conversation,
            llm=FakeLLMClient(answer_questions=False),
            catalog=get_catalog(),
        )
        await default_registry().get("requirements_analyst").execute(context)
        assert conversation.has_blocking_questions

    async def test_el_arquitecto_resuelve_las_dependencias_de_modulos(
        self, context: AgentContext
    ) -> None:
        registry = default_registry()
        analisis = await registry.get("requirements_analyst").execute(context)
        analisis.merge_into(context)
        resultado = await registry.get("software_architect").execute(context)

        modulos = resultado.produced["architecture"].modules
        assert "users" in modulos
        # `reservas` depende de `agenda`, que el instalador debe arrastrar.
        assert modulos.index("agenda") < modulos.index("reservas")

    async def test_un_agente_sin_sus_requisitos_falla(self, context: AgentContext) -> None:
        with pytest.raises(AgentExecutionError, match="Faltan productos previos"):
            await default_registry().get("software_architect").execute(context)

    async def test_los_errores_se_normalizan_a_error_de_agente(self, context: AgentContext) -> None:
        with pytest.raises(AgentExecutionError, match="fallo simulado"):
            await _Failing("roto", (), ("x",)).execute(context)


class TestPipeline:
    def test_el_pipeline_estandar_es_valido(self) -> None:
        default_pipeline().validate(default_registry())

    def test_los_once_agentes_estan_en_el_pipeline(self) -> None:
        etapas = {stage.agent_key for stage in default_pipeline().stages}
        assert etapas == default_registry().keys()
        assert len(etapas) == 11

    def test_una_etapa_sin_su_dependencia_falla(self) -> None:
        registry = AgentRegistry([_Stub("a", ("inexistente",), ("x",))])
        pipeline = Pipeline(stages=(PipelineStage("uno", "a"),))
        with pytest.raises(ValidationError, match="requiere"):
            pipeline.validate(registry)

    def test_etapa_duplicada_falla(self) -> None:
        registry = AgentRegistry([_Stub("a", (), ("x",))])
        pipeline = Pipeline(stages=(PipelineStage("uno", "a"), PipelineStage("uno", "a")))
        with pytest.raises(ValidationError, match="duplicada"):
            pipeline.validate(registry)

    def test_las_etapas_independientes_caen_en_el_mismo_nivel(self) -> None:
        niveles = default_pipeline().execution_levels(default_registry())
        por_nivel = [{stage.name for stage in nivel} for nivel in niveles]
        paralelo = next(nivel for nivel in por_nivel if "backend" in nivel)
        assert {"backend", "frontend", "despliegue"} <= paralelo

    def test_el_analisis_va_primero_y_el_mantenimiento_al_final(self) -> None:
        niveles = default_pipeline().execution_levels(default_registry())
        assert niveles[0][0].name == "analisis"
        assert "mantenimiento" in {stage.name for stage in niveles[-1]}


class TestOrquestador:
    def _orchestrator(self, events: InMemoryEventBus) -> Orchestrator:
        return Orchestrator(default_registry(), default_pipeline(), emit=events.publish)

    async def test_ejecucion_completa_genera_el_proyecto(
        self, project: Project, conversation: Conversation, context: AgentContext
    ) -> None:
        events = InMemoryEventBus()
        build = Build(project_id=project.id)

        report = await self._orchestrator(events).run(
            project=project, conversation=conversation, build=build, context=context
        )

        assert report.succeeded, report.error
        assert build.progress == 1.0
        assert len(context.artifacts) > 30
        assert "docker-compose.yml" in context.artifacts
        assert "backend/app/main.py" in context.artifacts
        assert "README.md" in context.artifacts

    async def test_emite_progreso_de_cada_etapa(
        self, project: Project, conversation: Conversation, context: AgentContext
    ) -> None:
        events = InMemoryEventBus()
        build = Build(project_id=project.id)
        await self._orchestrator(events).run(
            project=project, conversation=conversation, build=build, context=context
        )

        nombres = [event.name for event in events.events_for(project.id)]
        assert "build.started" in nombres
        assert "build.succeeded" in nombres
        assert nombres.count("build.stage_started") == len(default_pipeline().stages)

    async def test_se_detiene_si_faltan_respuestas_del_usuario(
        self, project: Project, conversation: Conversation
    ) -> None:
        context = AgentContext(
            project=project,
            conversation=conversation,
            llm=FakeLLMClient(answer_questions=False),
            catalog=get_catalog(),
        )
        events = InMemoryEventBus()
        build = Build(project_id=project.id)

        report = await self._orchestrator(events).run(
            project=project, conversation=conversation, build=build, context=context
        )

        assert report.awaiting_clarification
        assert not report.succeeded
        assert "requirements.clarification_requested" in [
            event.name for event in events.events_for(project.id)
        ]

    async def test_un_fallo_obligatorio_detiene_la_construccion(
        self, project: Project, conversation: Conversation, context: AgentContext
    ) -> None:
        registry = AgentRegistry([_Stub("ok", (), ("x",)), _Failing("roto", ("x",), ("y",))])
        pipeline = Pipeline(stages=(PipelineStage("uno", "ok"), PipelineStage("dos", "roto")))
        events = InMemoryEventBus()
        build = Build(project_id=project.id)

        report = await Orchestrator(registry, pipeline, emit=events.publish).run(
            project=project, conversation=conversation, build=build, context=context
        )

        assert not report.succeeded
        assert report.failed_stage == "dos"
        assert build.status.value == "failed"
        assert "build.failed" in [event.name for event in events.events_for(project.id)]

    async def test_una_etapa_opcional_que_falla_solo_se_salta(
        self, project: Project, conversation: Conversation, context: AgentContext
    ) -> None:
        registry = AgentRegistry([_Stub("ok", (), ("x",)), _Failing("roto", ("x",), ("y",))])
        pipeline = Pipeline(
            stages=(
                PipelineStage("uno", "ok"),
                PipelineStage("dos", "roto", optional=True),
            )
        )
        build = Build(project_id=project.id)

        report = await Orchestrator(registry, pipeline).run(
            project=project, conversation=conversation, build=build, context=context
        )

        assert report.succeeded
        assert report.skipped == ["dos"]
