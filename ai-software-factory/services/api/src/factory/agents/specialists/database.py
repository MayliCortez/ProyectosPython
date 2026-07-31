"""Agente diseñador de base de datos: entidades, campos y relaciones."""

from __future__ import annotations

from typing import Any

from factory.agents.base import Agent, AgentContext, AgentResult
from factory.agents.products import ArchitectureDecision
from factory.agents.prompts import DATABASE_DESIGNER, SCHEMA_DESIGN_SCHEMA
from factory.domain.entities.specification import DataEntity, DataField, RequirementsDocument
from factory.domain.errors import AgentExecutionError


class DatabaseDesigner(Agent):
    """Convierte las historias de usuario en un modelo de datos normalizado."""

    key = "database_designer"
    name = "Diseñador de base de datos"
    requires = ("requirements", "architecture")
    produces = ("entities",)

    async def run(self, context: AgentContext) -> AgentResult:
        requirements: RequirementsDocument = context.get("requirements")
        architecture: ArchitectureDecision = context.get("architecture")
        await context.log("Diseñando el modelo de datos")

        module_tables = [
            f"- {manifest.key}: {', '.join(manifest.table_names) or 'sin tablas'}"
            for manifest in (context.catalog.get(key) for key in architecture.modules)
        ]
        response = await context.llm.complete_json(
            system=DATABASE_DESIGNER,
            prompt=(
                f"<requisitos>\n{requirements.to_markdown()}\n</requisitos>\n\n"
                "<tablas_ya_existentes>\n"
                "Las aportan los módulos instalados; no las repitas.\n"
                + "\n".join(module_tables)
                + "\n</tablas_ya_existentes>"
            ),
            schema=SCHEMA_DESIGN_SCHEMA,
            schema_name="schema_design",
        )

        entities = [self._build_entity(item) for item in response.data.get("entities", [])]
        entities = self._drop_duplicates(entities)
        if not entities:
            raise AgentExecutionError(self.key, "El diseño no produjo ninguna entidad")

        self._validate_references(entities)
        await context.log(
            f"{len(entities)} entidad(es): {', '.join(entity.name for entity in entities)}"
        )
        return AgentResult(produced={"entities": entities})

    def _build_entity(self, item: dict[str, Any]) -> DataEntity:
        raw_fields: list[dict[str, Any]] = list(item.get("fields") or [])
        fields = tuple(
            DataField(
                name=str(field_item["name"]),
                type=str(field_item.get("type", "string")),
                required=bool(field_item.get("required", True)),
                unique=bool(field_item.get("unique", False)),
                references=(
                    str(field_item["references"]) if field_item.get("references") else None
                ),
                description=str(field_item.get("description", "")),
            )
            for field_item in raw_fields
            # `id` y `created_at` los añade el generador; ignorarlos evita duplicados.
            if str(field_item["name"]) not in {"id", "created_at"}
        )
        return DataEntity(
            name=str(item["name"]),
            fields=fields,
            description=str(item.get("description", "")),
        )

    def _drop_duplicates(self, entities: list[DataEntity]) -> list[DataEntity]:
        """La primera aparición gana; evita que el modelo repita una entidad."""
        seen: dict[str, DataEntity] = {}
        for entity in entities:
            seen.setdefault(entity.name, entity)
        return list(seen.values())

    def _validate_references(self, entities: list[DataEntity]) -> None:
        known = {entity.name for entity in entities}
        for entity in entities:
            for data_field in entity.fields:
                if data_field.references and data_field.references not in known:
                    raise AgentExecutionError(
                        self.key,
                        f"{entity.name}.{data_field.name} referencia la entidad "
                        f"inexistente {data_field.references!r}",
                    )
