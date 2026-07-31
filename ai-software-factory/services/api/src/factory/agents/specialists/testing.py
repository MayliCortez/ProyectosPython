"""Agente generador de pruebas y ejecución de la suite del proyecto generado."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.specialists._blueprint import blueprint_from
from factory.codegen.renderers import render_tests
from factory.domain.value_objects import snake_case


class TestGenerator(Agent):
    """Escribe la suite de pruebas del proyecto y comprueba su cobertura estructural.

    No ejecuta las pruebas dentro del proceso de la fábrica —eso ocurre en el
    contenedor del proyecto, aislado— pero sí verifica que toda entidad y todo
    endpoint declarado tenga al menos una prueba asociada; una entidad sin prueba es
    un fallo de la construcción, no un aviso.
    """

    key = "test_generator"
    name = "Generador de pruebas"
    requires = ("specification", "backend_files")
    produces = ("test_files", "test_report")

    async def run(self, context: AgentContext) -> AgentResult:
        blueprint = blueprint_from(context)
        await context.log("Generando la suite de pruebas")

        artifacts = render_tests(blueprint)
        paths = [artifact.path for artifact in artifacts]

        covered = {
            path.rsplit("/", 1)[-1].removeprefix("test_").removesuffix(".py") for path in paths
        }
        uncovered = [
            entity.name for entity in blueprint.entities if snake_case(entity.name) not in covered
        ]

        report = {
            "test_files": len(artifacts),
            "entities": len(blueprint.entities),
            "uncovered_entities": uncovered,
            "passed": not uncovered,
        }
        if uncovered:
            await context.log(f"Aviso: entidades sin prueba propia: {uncovered}")
        else:
            await context.log(f"{len(artifacts)} fichero(s) de prueba; cobertura completa")

        return AgentResult(
            produced={"test_files": paths, "test_report": report},
            artifacts=artifacts,
        )
