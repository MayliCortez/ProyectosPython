"""Genera la documentación del proyecto: README, API y modelo de datos."""

from __future__ import annotations

from factory.codegen.blueprint import Blueprint
from factory.domain.value_objects import Artifact


def render_docs(blueprint: Blueprint) -> list[Artifact]:
    """README de arranque, referencia de la API y diagrama del modelo de datos."""
    return [_readme(blueprint), _api_reference(blueprint), _data_model(blueprint)]


def _readme(blueprint: Blueprint) -> Artifact:
    modules = (
        "\n".join(f"- **{module.name}** — {module.description}" for module in blueprint.modules)
        or "- Sin módulos adicionales"
    )
    entities = (
        "\n".join(
            f"- `{entity.table_name}` — {entity.description or entity.name}"
            for entity in blueprint.entities
        )
        or "- Sin entidades"
    )
    body = f"""# {blueprint.name}

{blueprint.project.prompt or "Aplicación generada con AI Software Factory."}

## Arranque

```bash
cp .env.example .env
./install.sh
```

- API: http://localhost:8000/docs
- Web: http://localhost:3000

## Pila tecnológica

| Capa | Tecnología |
|------|------------|
| Backend | {blueprint.tech_stack.backend} |
| Frontend | {blueprint.tech_stack.frontend} |
| Base de datos | {blueprint.tech_stack.database} |
| Caché | {blueprint.tech_stack.cache} |
| Ejecución | {blueprint.tech_stack.runtime} |

## Módulos instalados

{modules}

## Entidades

{entities}

## Estructura

```
backend/          API FastAPI (modelos, esquemas, routers, migraciones)
frontend/         Aplicación Next.js con App Router
database/         Esquema SQL y datos iniciales
docs/             Referencia de la API y modelo de datos
docker-compose.yml
install.sh
```

## Documentación

- [`docs/API.md`](docs/API.md) — referencia de endpoints
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — entidades y relaciones
"""
    return Artifact("README.md", body, "markdown")


def _api_reference(blueprint: Blueprint) -> Artifact:
    lines = [
        f"# API de {blueprint.name}",
        "",
        "Prefijo base: `/api/v1`. La especificación OpenAPI viva está en `/docs`.",
        "",
        "| Método | Ruta | Descripción | Autenticación |",
        "|--------|------|-------------|---------------|",
    ]
    for endpoint in blueprint.endpoints:
        auth = "Sí" if endpoint.auth_required else "No"
        lines.append(
            f"| `{endpoint.method}` | `/api/v1{endpoint.path}` | "
            f"{endpoint.summary or '—'} | {auth} |"
        )
    lines += [
        "",
        "## Códigos de error",
        "",
        "| Código | Significado |",
        "|--------|-------------|",
        "| 400 | Carga útil inválida |",
        "| 401 | Falta el token o ha caducado |",
        "| 403 | El usuario no tiene permiso sobre el recurso |",
        "| 404 | El recurso no existe |",
        "| 422 | La validación del esquema falló |",
        "",
    ]
    return Artifact("docs/API.md", "\n".join(lines), "markdown")


def _data_model(blueprint: Blueprint) -> Artifact:
    lines = [f"# Modelo de datos de {blueprint.name}", ""]
    for entity in blueprint.entities:
        lines += [
            f"## {entity.name} (`{entity.table_name}`)",
            "",
            entity.description or "",
            "",
            "| Campo | Tipo | Obligatorio | Notas |",
            "|-------|------|-------------|-------|",
            "| `id` | integer | Sí | Clave primaria |",
        ]
        for data_field in entity.fields:
            if data_field.name == "id":
                continue
            notes = []
            if data_field.unique:
                notes.append("único")
            if data_field.references:
                notes.append(f"→ `{data_field.references}`")
            if data_field.description:
                notes.append(data_field.description)
            lines.append(
                f"| `{data_field.name}` | {data_field.type} | "
                f"{'Sí' if data_field.required else 'No'} | {', '.join(notes) or '—'} |"
            )
        lines += ["| `created_at` | datetime | Sí | Fecha de alta |", ""]

    relations = [
        f"  {entity.name} --> {f.references}"
        for entity in blueprint.entities
        for f in entity.fields
        if f.references
    ]
    if relations:
        lines += ["## Relaciones", "", "```mermaid", "graph TD", *relations, "```", ""]
    return Artifact("docs/DATA_MODEL.md", "\n".join(lines), "markdown")
