"""Agente de mantenimiento: plan de operación del sistema entregado."""

from __future__ import annotations

from typing import Any

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.prompts import MAINTENANCE_AGENT, MAINTENANCE_SCHEMA
from factory.domain.value_objects import Artifact


class MaintenanceAgent(Agent):
    """Cierra el ciclo: qué vigilar, con qué frecuencia y cómo reaccionar."""

    key = "maintenance_agent"
    name = "Agente de mantenimiento"
    requires = ("specification", "review", "deploy_files")
    produces = ("maintenance_plan",)

    async def run(self, context: AgentContext) -> AgentResult:
        specification = context.get("specification")
        review = context.get("review")
        await context.log("Redactando el plan de mantenimiento")

        response = await context.llm.complete_json(
            system=MAINTENANCE_AGENT,
            prompt=(
                f"Proyecto: {context.project.name}\n"
                f"Módulos: {', '.join(specification.modules)}\n"
                f"Veredicto de la revisión: {review['verdict']}\n"
                f"Hallazgos abiertos: {len(review['findings'])}"
            ),
            schema=MAINTENANCE_SCHEMA,
            schema_name="maintenance_plan",
        )

        plan: dict[str, Any] = {
            "checks": list(response.data.get("checks", [])),
            "runbook": str(response.data.get("runbook", "")),
        }
        await context.log(f"{len(plan['checks'])} comprobación(es) programadas")
        return AgentResult(
            produced={"maintenance_plan": plan},
            artifacts=[Artifact("docs/MANTENIMIENTO.md", self._document(plan), "markdown")],
        )

    def _document(self, plan: dict[str, Any]) -> str:
        lines = ["# Plan de mantenimiento", ""]
        if plan["checks"]:
            lines += ["| Comprobación | Frecuencia | Acción |", "|---|---|---|"]
            for check in plan["checks"]:
                lines.append(
                    f"| {check.get('name', '—')} | {check.get('frequency', '—')} | "
                    f"{check.get('action', '—')} |"
                )
            lines.append("")
        if plan["runbook"]:
            lines += ["## Runbook", "", plan["runbook"], ""]
        return "\n".join(lines)
