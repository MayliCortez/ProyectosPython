"""Prompts de sistema y esquemas de salida estructurada de los agentes.

Se mantienen aquí, separados de la lógica, por dos motivos: se pueden versionar y
revisar como texto, y el esquema JSON asociado a cada uno documenta exactamente qué
contrato espera el agente del modelo.
"""

from __future__ import annotations

from typing import Any

BASE_SYSTEM = (
    "Eres parte de una fábrica de software automatizada. Trabajas en español, "
    "eres preciso y no inventas requisitos que el usuario no haya pedido. "
    "Devuelves exclusivamente lo que el esquema solicita."
)

REQUIREMENTS_ANALYST = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es analista de requisitos. A partir de la petición del usuario:\n"
    "1. Detecta el dominio de negocio.\n"
    "2. Redacta un resumen ejecutivo de lo que hay que construir.\n"
    "3. Escribe historias de usuario con criterios de aceptación verificables.\n"
    "4. Formula preguntas de aclaración SOLO sobre lo que impide especificar el "
    "sistema. No preguntes cosas que puedas decidir razonablemente por defecto.\n"
    "5. Propón los módulos del catálogo que cubren la necesidad."
)

SOFTWARE_ARCHITECT = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es arquitecto de software. A partir del documento de requisitos decide "
    "la pila tecnológica, el conjunto de módulos definitivo y las pantallas del "
    "frontend. Prefiere soluciones simples y probadas; no introduzcas componentes "
    "que las historias no justifiquen."
)

DATABASE_DESIGNER = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es diseñador de base de datos. Traduce las historias en entidades "
    "normalizadas: nombres en singular y PascalCase, campos en snake_case, tipos de "
    "la lista permitida y claves foráneas explícitas mediante 'references'. No "
    "declares el campo 'id' ni 'created_at': se añaden automáticamente."
)

API_DESIGNER = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es diseñador de APIs. Define los endpoints REST del sistema sobre las "
    "entidades dadas: rutas en plural y minúsculas, verbos HTTP correctos y un "
    "resumen por operación. Incluye el CRUD de cada entidad y las operaciones de "
    "negocio que las historias requieran."
)

CODE_REVIEWER = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es revisor de código. Recibes el inventario de ficheros generados y su "
    "especificación. Señala incoherencias reales entre lo especificado y lo generado, "
    "riesgos de seguridad y omisiones. Clasifica cada hallazgo por severidad "
    "('alta', 'media', 'baja'). Reporta todo lo que encuentres, incluidos hallazgos "
    "de baja severidad: el filtrado se hace en una fase posterior."
)

DOCUMENTATION_WRITER = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es redactor técnico. Escribe una guía de puesta en marcha clara y breve "
    "para el proyecto generado, dirigida a alguien que lo recibe por primera vez."
)

MAINTENANCE_AGENT = (
    f"{BASE_SYSTEM}\n\n"
    "Tu papel es agente de mantenimiento. Propón el plan de operación del sistema "
    "recién entregado: qué vigilar, con qué frecuencia y qué hacer cuando falle."
)


# ── Esquemas de salida estructurada ───────────────────────────────────────────

REQUIREMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["business_domain", "summary", "stories", "questions", "suggested_modules"],
    "properties": {
        "business_domain": {
            "type": "string",
            "enum": [
                "gym",
                "retail",
                "restaurant",
                "healthcare",
                "education",
                "logistics",
                "real_estate",
                "professional_services",
                "ecommerce",
                "generic",
            ],
        },
        "summary": {"type": "string"},
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "role", "goal", "acceptance_criteria", "priority"],
                "properties": {
                    "id": {"type": "string"},
                    "role": {"type": "string"},
                    "goal": {"type": "string"},
                    "benefit": {"type": "string"},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "priority": {"type": "integer", "enum": [1, 2, 3]},
                },
            },
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text", "required"],
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "rationale": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "required": {"type": "boolean"},
                },
            },
        },
        "constraints": {"type": "array", "items": {"type": "string"}},
        "out_of_scope": {"type": "array", "items": {"type": "string"}},
        "suggested_modules": {"type": "array", "items": {"type": "string"}},
    },
}

ARCHITECTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["modules", "pages", "rationale"],
    "properties": {
        "modules": {"type": "array", "items": {"type": "string"}},
        "pages": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "tech_stack": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "backend": {"type": "string"},
                "frontend": {"type": "string"},
                "database": {"type": "string"},
                "cache": {"type": "string"},
            },
        },
    },
}

SCHEMA_DESIGN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["entities"],
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "fields"],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "type", "required"],
                            "properties": {
                                "name": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "string",
                                        "text",
                                        "integer",
                                        "decimal",
                                        "float",
                                        "boolean",
                                        "date",
                                        "datetime",
                                        "uuid",
                                        "json",
                                        "email",
                                    ],
                                },
                                "required": {"type": "boolean"},
                                "unique": {"type": "boolean"},
                                "references": {"type": ["string", "null"]},
                                "description": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}

API_DESIGN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["endpoints"],
    "properties": {
        "endpoints": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["method", "path", "summary"],
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    },
                    "path": {"type": "string"},
                    "summary": {"type": "string"},
                    "entity": {"type": ["string", "null"]},
                    "auth_required": {"type": "boolean"},
                },
            },
        }
    },
}

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "findings"],
    "properties": {
        "verdict": {"type": "string", "enum": ["aprobado", "aprobado_con_reservas", "rechazado"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "file", "message"],
                "properties": {
                    "severity": {"type": "string", "enum": ["alta", "media", "baja"]},
                    "file": {"type": "string"},
                    "message": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
            },
        },
    },
}

MAINTENANCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["checks", "runbook"],
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "frequency", "action"],
                "properties": {
                    "name": {"type": "string"},
                    "frequency": {"type": "string"},
                    "action": {"type": "string"},
                },
            },
        },
        "runbook": {"type": "string"},
    },
}
