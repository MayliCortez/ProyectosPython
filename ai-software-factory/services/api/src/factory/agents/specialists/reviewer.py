"""Agente revisor: contrasta lo generado con lo especificado."""

from __future__ import annotations

from typing import Any

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.prompts import CODE_REVIEWER, REVIEW_SCHEMA
from factory.domain.entities.specification import Specification
from factory.domain.errors import AgentExecutionError
from factory.domain.value_objects import Artifact, snake_case


class CodeReviewer(Agent):
    """Revisa la construcción y bloquea la entrega si hay hallazgos graves.

    Combina dos fuentes: comprobaciones estructurales deterministas (cada entidad
    tiene modelo, router y prueba) y la revisión del modelo. Las primeras nunca dan
    falsos negativos; la segunda aporta criterio sobre lo que las reglas no ven.
    """

    key = "code_reviewer"
    name = "Revisor de código"
    requires = ("specification", "backend_files", "frontend_files", "test_files")
    produces = ("review",)

    async def run(self, context: AgentContext) -> AgentResult:
        specification: Specification = context.get("specification")
        await context.log("Revisando el código generado")

        structural = self._structural_findings(context, specification)
        response = await context.llm.complete_json(
            system=CODE_REVIEWER,
            prompt=self._prompt(context, specification),
            schema=REVIEW_SCHEMA,
            schema_name="code_review",
        )
        findings: list[dict[str, Any]] = [
            *structural,
            *[dict(item) for item in response.data.get("findings", [])],
        ]

        blocking = [item for item in findings if item.get("severity") == "alta"]
        verdict = "rechazado" if blocking else ("aprobado_con_reservas" if findings else "aprobado")
        review = {
            "verdict": verdict,
            "findings": findings,
            "blocking": len(blocking),
        }

        if blocking:
            await context.log(f"Revisión con {len(blocking)} hallazgo(s) de severidad alta")
            raise AgentExecutionError(
                self.key,
                "La revisión encontró problemas bloqueantes: "
                + "; ".join(str(item.get("message", "")) for item in blocking[:3]),
            )

        await context.log(f"Revisión: {verdict} ({len(findings)} hallazgo/s)")
        return AgentResult(
            produced={"review": review},
            artifacts=[Artifact("docs/REVISION.md", self._document(review), "markdown")],
        )

    def _structural_findings(
        self, context: AgentContext, specification: Specification
    ) -> list[dict[str, Any]]:
        """Comprobaciones que no dependen del criterio del modelo."""
        paths = set(context.artifacts)
        findings: list[dict[str, Any]] = []

        for entity in specification.entities:
            module = snake_case(entity.name)
            expected = {
                f"backend/app/routers/{module}.py": "router",
                f"backend/tests/test_{module}.py": "prueba",
            }
            for path, kind in expected.items():
                if path not in paths:
                    findings.append(
                        {
                            "severity": "alta",
                            "file": path,
                            "message": f"Falta el {kind} de la entidad {entity.name}",
                        }
                    )
        for required in ("backend/app/main.py", "backend/app/models.py", "docker-compose.yml"):
            if required not in paths:
                findings.append(
                    {
                        "severity": "alta",
                        "file": required,
                        "message": "Fichero imprescindible ausente en la construcción",
                    }
                )
        return findings

    def _prompt(self, context: AgentContext, specification: Specification) -> str:
        inventory = "\n".join(f"- {path}" for path in sorted(context.artifacts))
        entities = ", ".join(entity.name for entity in specification.entities)
        return (
            f"Entidades especificadas: {entities}\n"
            f"Endpoints especificados: {len(specification.endpoints)}\n"
            f"Módulos instalados: {', '.join(specification.modules)}\n\n"
            f"Ficheros generados:\n{inventory}"
        )

    def _document(self, review: dict[str, Any]) -> str:
        lines = [
            "# Informe de revisión",
            "",
            f"**Veredicto:** {review['verdict']}",
            "",
        ]
        findings = review["findings"]
        if not findings:
            lines.append("No se han encontrado hallazgos.")
            return "\n".join(lines) + "\n"

        lines += ["| Severidad | Fichero | Hallazgo |", "|-----------|---------|----------|"]
        for item in findings:
            lines.append(
                f"| {item.get('severity', '—')} | `{item.get('file', '—')}` | "
                f"{item.get('message', '')} |"
            )
        return "\n".join(lines) + "\n"
