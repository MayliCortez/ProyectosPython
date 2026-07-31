"""Agente diseñador de APIs: ensambla la especificación técnica definitiva."""

from __future__ import annotations

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.products import ArchitectureDecision
from factory.agents.prompts import API_DESIGN_SCHEMA, API_DESIGNER
from factory.domain.entities.specification import (
    DataEntity,
    Endpoint,
    RequirementsDocument,
    Specification,
)


class ApiDesigner(Agent):
    """Define los endpoints y cierra la especificación que consumen los generadores."""

    key = "api_designer"
    name = "Generador de APIs"
    requires = ("requirements", "architecture", "entities")
    produces = ("endpoints", "specification")

    async def run(self, context: AgentContext) -> AgentResult:
        requirements: RequirementsDocument = context.get("requirements")
        architecture: ArchitectureDecision = context.get("architecture")
        entities: list[DataEntity] = context.get("entities")
        await context.log("Diseñando el contrato de la API")

        model = "\n".join(
            f"- {entity.name} ({entity.table_name}): " + ", ".join(f.name for f in entity.fields)
            for entity in entities
        )
        response = await context.llm.complete_json(
            system=API_DESIGNER,
            prompt=(
                f"<entidades>\n{model}\n</entidades>\n\n"
                "<historias>\n"
                + "\n".join(f"- {story}" for story in requirements.stories)
                + "\n</historias>"
            ),
            schema=API_DESIGN_SCHEMA,
            schema_name="api_design",
        )

        endpoints = [
            Endpoint(
                method=str(item["method"]),
                path=str(item["path"]),
                summary=str(item.get("summary", "")),
                entity=str(item["entity"]) if item.get("entity") else None,
                auth_required=bool(item.get("auth_required", True)),
            )
            for item in response.data.get("endpoints", [])
        ]
        endpoints = self._ensure_crud(entities, endpoints)
        endpoints = self._add_module_endpoints(context, endpoints)

        specification = Specification(
            project_id=context.project.id,
            requirements_id=requirements.id,
            tech_stack=architecture.tech_stack,
            entities=entities,
            endpoints=endpoints,
            modules=list(architecture.modules),
            pages=list(architecture.pages),
            notes={"rationale": architecture.rationale},
        )
        specification.validate()

        await context.log(f"{len(endpoints)} endpoint(s) definidos")
        return AgentResult(produced={"endpoints": endpoints, "specification": specification})

    def _ensure_crud(self, entities: list[DataEntity], endpoints: list[Endpoint]) -> list[Endpoint]:
        """Garantiza el CRUD completo de cada entidad aunque el modelo lo omita."""
        existing = {(endpoint.method, endpoint.path) for endpoint in endpoints}
        complete = list(endpoints)
        for entity in entities:
            resource = entity.table_name
            required = [
                ("GET", f"/{resource}", f"Listar {resource}"),
                ("POST", f"/{resource}", f"Crear {entity.name}"),
                ("GET", f"/{resource}/{{id}}", f"Obtener {entity.name}"),
                ("PATCH", f"/{resource}/{{id}}", f"Actualizar {entity.name}"),
                ("DELETE", f"/{resource}/{{id}}", f"Eliminar {entity.name}"),
            ]
            for method, path, summary in required:
                if (method, path) not in existing:
                    complete.append(
                        Endpoint(method=method, path=path, summary=summary, entity=entity.name)
                    )
                    existing.add((method, path))
        return complete

    def _add_module_endpoints(
        self, context: AgentContext, endpoints: list[Endpoint]
    ) -> list[Endpoint]:
        """Incorpora los endpoints que declaran los módulos instalados."""
        existing = {(endpoint.method, endpoint.path) for endpoint in endpoints}
        complete = list(endpoints)
        for key in context.project.module_keys:
            manifest = context.catalog.try_get(key)
            if manifest is None:
                continue
            for module_endpoint in manifest.endpoints:
                identity = (module_endpoint.method, module_endpoint.path)
                if identity in existing:
                    continue
                complete.append(
                    Endpoint(
                        method=module_endpoint.method,
                        path=module_endpoint.path,
                        summary=module_endpoint.summary,
                        auth_required=not module_endpoint.path.startswith("/auth/"),
                    )
                )
                existing.add(identity)
        return complete
