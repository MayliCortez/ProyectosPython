"""Utilidades compartidas por los renderizadores."""

from __future__ import annotations

from factory.domain.entities.specification import DataEntity, DataField
from factory.domain.value_objects import snake_case

#: Tipo de la especificación → (anotación Python, columna SQLAlchemy, tipo SQL, tipo TS).
_TYPES: dict[str, tuple[str, str, str, str]] = {
    "string": ("str", "String(255)", "VARCHAR(255)", "string"),
    "text": ("str", "Text", "TEXT", "string"),
    "integer": ("int", "Integer", "INTEGER", "number"),
    "decimal": ("Decimal", "Numeric(12, 2)", "NUMERIC(12,2)", "number"),
    "float": ("float", "Float", "DOUBLE PRECISION", "number"),
    "boolean": ("bool", "Boolean", "BOOLEAN", "boolean"),
    "date": ("date", "Date", "DATE", "string"),
    "datetime": ("datetime", "DateTime(timezone=True)", "TIMESTAMPTZ", "string"),
    "uuid": ("str", "String(36)", "UUID", "string"),
    "json": ("dict", "JSON", "JSONB", "Record<string, unknown>"),
    "email": ("str", "String(320)", "VARCHAR(320)", "string"),
}
_FALLBACK = _TYPES["string"]


def python_type(field: DataField) -> str:
    """Anotación Python del campo, opcional si no es obligatorio."""
    base = _TYPES.get(field.type, _FALLBACK)[0]
    return base if field.required else f"{base} | None"


def sqlalchemy_type(field: DataField) -> str:
    return _TYPES.get(field.type, _FALLBACK)[1]


def sql_type(field: DataField) -> str:
    return _TYPES.get(field.type, _FALLBACK)[2]


def typescript_type(field: DataField) -> str:
    base = _TYPES.get(field.type, _FALLBACK)[3]
    return base if field.required else f"{base} | null"


def python_imports_for(entities: list[DataEntity]) -> list[str]:
    """Importaciones estándar necesarias según los tipos usados."""
    used = {f.type for entity in entities for f in entity.fields}
    imports: list[str] = []
    if used & {"date", "datetime"}:
        parts = sorted(used & {"date", "datetime"})
        imports.append(f"from datetime import {', '.join(parts)}")
    if "decimal" in used:
        imports.append("from decimal import Decimal")
    return imports


#: Reexportada desde el dominio: generadores y revisor deben coincidir en los nombres.
snake = snake_case


def indent(text: str, spaces: int = 4) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())


def header(description: str) -> str:
    """Cabecera común de los ficheros generados."""
    return (
        f'"""{description}\n\n'
        "Generado por AI Software Factory. Puedes editarlo: las regeneraciones\n"
        'posteriores respetan los ficheros marcados como personalizados.\n"""'
    )
