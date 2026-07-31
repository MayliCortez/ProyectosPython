"""Proveedor de IA determinista.

No es un simulacro de juguete: reproduce el contrato completo de `LLMClient` con
salidas coherentes por dominio de negocio. Sirve para tres cosas:

1. ejecutar la suite de pruebas del pipeline completo sin red ni coste,
2. demostrar la plataforma en entornos sin clave de API,
3. dar un comportamiento de reserva estable cuando el proveedor real falla.

Cada respuesta depende solo del prompt y del esquema, así que dos ejecuciones
idénticas producen exactamente el mismo proyecto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from factory.application.ports.llm import LLMResponse
from factory.domain.value_objects import BusinessDomain, table_name_for


@dataclass(frozen=True, slots=True)
class DomainProfile:
    """Plantilla de conocimiento para un dominio de negocio concreto."""

    domain: BusinessDomain
    keywords: tuple[str, ...]
    summary: str
    modules: tuple[str, ...]
    questions: tuple[tuple[str, str, tuple[str, ...]], ...] = field(default_factory=tuple)
    stories: tuple[tuple[str, str, str, tuple[str, ...], int], ...] = field(default_factory=tuple)
    entities: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def _field(
    name: str,
    type_: str = "string",
    *,
    required: bool = True,
    unique: bool = False,
    references: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "required": required,
        "unique": unique,
        "references": references,
        "description": "",
    }


GYM = DomainProfile(
    domain=BusinessDomain.GYM,
    keywords=("gimnasio", "gym", "fitness", "entrenamiento", "socios", "musculacion"),
    summary=(
        "Sistema de gestión para un gimnasio: alta y seguimiento de socios, planes de "
        "membresía con control de vigencia, reserva de clases dirigidas con aforo, "
        "registro de asistencia y cobro periódico de cuotas."
    ),
    modules=(
        "users",
        "login",
        "roles",
        "dashboard",
        "agenda",
        "reservas",
        "billing",
        "pagos",
        "notificaciones",
        "reportes",
    ),
    questions=(
        (
            "q-membresias",
            "¿Qué tipos de membresía se ofrecen y con qué periodicidad se cobran?",
            ("Mensual", "Trimestral", "Anual", "Sesión suelta"),
        ),
        (
            "q-aforo",
            "¿Las clases dirigidas tienen aforo limitado y lista de espera?",
            ("Aforo con lista de espera", "Solo aforo", "Sin límite"),
        ),
        (
            "q-pagos",
            "¿Se cobrará online con pasarela de pago o el cobro es presencial?",
            ("Pasarela online", "Presencial", "Ambos"),
        ),
    ),
    stories=(
        (
            "HU-01",
            "recepcionista",
            "dar de alta a un socio con sus datos y su plan de membresía",
            (
                "El alta exige nombre, contacto y plan",
                "El sistema calcula la fecha de vencimiento a partir del plan",
                "Un correo duplicado se rechaza con un mensaje claro",
            ),
            1,
        ),
        (
            "HU-02",
            "socio",
            "reservar una plaza en una clase dirigida desde mi móvil",
            (
                "Solo se pueden reservar clases con plazas libres",
                "La reserva se puede cancelar hasta 2 horas antes",
                "Una membresía vencida impide reservar",
            ),
            1,
        ),
        (
            "HU-03",
            "entrenador",
            "pasar lista de los asistentes a mi clase",
            (
                "La lista muestra a los socios con reserva confirmada",
                "La asistencia queda registrada con fecha y hora",
            ),
            1,
        ),
        (
            "HU-04",
            "administrador",
            "consultar los ingresos y las bajas del mes",
            (
                "El informe se filtra por rango de fechas",
                "Se puede exportar a CSV",
            ),
            2,
        ),
        (
            "HU-05",
            "socio",
            "recibir un aviso antes de que caduque mi membresía",
            ("El aviso se envía 7 días antes del vencimiento",),
            2,
        ),
    ),
    entities=(
        {
            "name": "Member",
            "description": "Socio del gimnasio",
            "fields": [
                _field("full_name"),
                _field("email", "email", unique=True),
                _field("phone", required=False),
                _field("birth_date", "date", required=False),
                _field("joined_on", "date"),
                _field("is_active", "boolean"),
            ],
        },
        {
            "name": "MembershipPlan",
            "description": "Plan de membresía comercializable",
            "fields": [
                _field("name", unique=True),
                _field("price", "decimal"),
                _field("duration_days", "integer"),
                _field("class_credits", "integer", required=False),
            ],
        },
        {
            "name": "Membership",
            "description": "Membresía contratada por un socio",
            "fields": [
                _field("member_id", "integer", references="Member"),
                _field("plan_id", "integer", references="MembershipPlan"),
                _field("starts_on", "date"),
                _field("expires_on", "date"),
                _field("status"),
            ],
        },
        {
            "name": "Trainer",
            "description": "Entrenador que imparte clases",
            "fields": [
                _field("full_name"),
                _field("email", "email", unique=True),
                _field("specialty", required=False),
            ],
        },
        {
            "name": "ClassSession",
            "description": "Clase dirigida programada",
            "fields": [
                _field("title"),
                _field("trainer_id", "integer", references="Trainer"),
                _field("starts_at", "datetime"),
                _field("duration_minutes", "integer"),
                _field("capacity", "integer"),
            ],
        },
        {
            "name": "Booking",
            "description": "Reserva de un socio en una clase",
            "fields": [
                _field("member_id", "integer", references="Member"),
                _field("session_id", "integer", references="ClassSession"),
                _field("status"),
                _field("cancelled_at", "datetime", required=False),
            ],
        },
        {
            "name": "Attendance",
            "description": "Asistencia registrada en una clase",
            "fields": [
                _field("member_id", "integer", references="Member"),
                _field("session_id", "integer", references="ClassSession"),
                _field("checked_in_at", "datetime"),
            ],
        },
    ),
)

RETAIL = DomainProfile(
    domain=BusinessDomain.ECOMMERCE,
    keywords=("tienda", "ecommerce", "venta", "productos", "carrito", "pedidos", "comercio"),
    summary=(
        "Plataforma de comercio: catálogo de productos con existencias, carrito, "
        "checkout con pasarela de pago y seguimiento de pedidos."
    ),
    modules=(
        "users",
        "login",
        "roles",
        "dashboard",
        "inventory",
        "tienda",
        "billing",
        "pagos",
        "crm",
        "notificaciones",
        "reportes",
    ),
    questions=(
        (
            "q-catalogo",
            "¿El catálogo necesita variantes de producto (talla, color)?",
            ("Sí", "No"),
        ),
        (
            "q-envios",
            "¿Se gestionan envíos con seguimiento o la entrega es en tienda?",
            ("Envío con seguimiento", "Recogida en tienda", "Ambos"),
        ),
    ),
    stories=(
        (
            "HU-01",
            "cliente",
            "buscar productos y añadirlos al carrito",
            ("La búsqueda filtra por nombre y categoría", "El carrito persiste entre sesiones"),
            1,
        ),
        (
            "HU-02",
            "cliente",
            "pagar mi pedido con tarjeta",
            ("El pago se confirma antes de crear el pedido", "Se emite factura automáticamente"),
            1,
        ),
        (
            "HU-03",
            "responsable de almacén",
            "ver las existencias y reponer los productos bajo mínimos",
            ("Un producto sin stock no se puede comprar",),
            1,
        ),
    ),
    entities=(
        {
            "name": "Category",
            "description": "Categoría del catálogo",
            "fields": [_field("name", unique=True), _field("slug", unique=True)],
        },
        {
            "name": "Product",
            "description": "Producto a la venta",
            "fields": [
                _field("sku", unique=True),
                _field("name"),
                _field("description", "text", required=False),
                _field("price", "decimal"),
                _field("stock", "integer"),
                _field("category_id", "integer", references="Category"),
                _field("is_active", "boolean"),
            ],
        },
        {
            "name": "Customer",
            "description": "Cliente de la tienda",
            "fields": [
                _field("full_name"),
                _field("email", "email", unique=True),
                _field("phone", required=False),
                _field("address", "text", required=False),
            ],
        },
        {
            "name": "Order",
            "description": "Pedido realizado",
            "fields": [
                _field("customer_id", "integer", references="Customer"),
                _field("total", "decimal"),
                _field("status"),
                _field("placed_at", "datetime"),
            ],
        },
        {
            "name": "OrderLine",
            "description": "Línea de un pedido",
            "fields": [
                _field("order_id", "integer", references="Order"),
                _field("product_id", "integer", references="Product"),
                _field("quantity", "integer"),
                _field("unit_price", "decimal"),
            ],
        },
    ),
)

RESTAURANT = DomainProfile(
    domain=BusinessDomain.RESTAURANT,
    keywords=("restaurante", "bar", "cafeteria", "mesas", "carta", "comandas", "menu"),
    summary=(
        "Gestión para hostelería: carta, reservas de mesa con control de aforo, "
        "comandas por mesa y facturación."
    ),
    modules=(
        "users",
        "login",
        "roles",
        "dashboard",
        "agenda",
        "reservas",
        "inventory",
        "billing",
        "reportes",
    ),
    questions=(
        (
            "q-turnos",
            "¿Se trabaja con turnos fijos de reserva o con horario continuo?",
            ("Turnos fijos", "Horario continuo"),
        ),
    ),
    stories=(
        (
            "HU-01",
            "cliente",
            "reservar una mesa indicando fecha, hora y número de comensales",
            ("No se admiten reservas por encima del aforo", "La reserva se confirma por correo"),
            1,
        ),
        (
            "HU-02",
            "camarero",
            "tomar la comanda de una mesa y enviarla a cocina",
            ("La comanda queda asociada a la mesa y al turno",),
            1,
        ),
    ),
    entities=(
        {
            "name": "Table",
            "description": "Mesa del local",
            "fields": [_field("code", unique=True), _field("seats", "integer"), _field("zone")],
        },
        {
            "name": "MenuItem",
            "description": "Plato o bebida de la carta",
            "fields": [
                _field("name"),
                _field("price", "decimal"),
                _field("category"),
                _field("is_available", "boolean"),
            ],
        },
        {
            "name": "Reservation",
            "description": "Reserva de mesa",
            "fields": [
                _field("table_id", "integer", references="Table"),
                _field("customer_name"),
                _field("phone", required=False),
                _field("starts_at", "datetime"),
                _field("party_size", "integer"),
                _field("status"),
            ],
        },
        {
            "name": "OrderTicket",
            "description": "Comanda de una mesa",
            "fields": [
                _field("table_id", "integer", references="Table"),
                _field("opened_at", "datetime"),
                _field("total", "decimal"),
                _field("status"),
            ],
        },
    ),
)

GENERIC = DomainProfile(
    domain=BusinessDomain.GENERIC,
    keywords=(),
    summary=(
        "Aplicación de gestión con autenticación, panel de administración y "
        "mantenimiento de los registros del negocio."
    ),
    modules=("users", "login", "roles", "dashboard", "notificaciones", "reportes"),
    questions=(
        (
            "q-entidades",
            "¿Cuáles son los registros principales que gestionará el sistema?",
            (),
        ),
        (
            "q-usuarios",
            "¿Qué perfiles de usuario deben existir y qué puede hacer cada uno?",
            (),
        ),
    ),
    stories=(
        (
            "HU-01",
            "administrador",
            "gestionar los registros del sistema desde un panel",
            ("Se pueden crear, consultar, editar y eliminar registros",),
            1,
        ),
        (
            "HU-02",
            "usuario",
            "iniciar sesión de forma segura",
            ("Las credenciales inválidas no revelan si el correo existe",),
            1,
        ),
    ),
    entities=(
        {
            "name": "Record",
            "description": "Registro principal del sistema",
            "fields": [
                _field("title"),
                _field("description", "text", required=False),
                _field("status"),
                _field("owner_email", "email", required=False),
            ],
        },
    ),
)

_PROFILES: tuple[DomainProfile, ...] = (GYM, RETAIL, RESTAURANT, GENERIC)


#: Secciones del prompt que describen lo que el usuario pide, en orden de preferencia.
_FOCUS_TAGS = ("peticion_usuario", "requisitos", "entidades")


def focus_section(text: str) -> str:
    """Aísla la parte del prompt que describe el problema del usuario.

    Los prompts incluyen material de referencia —el catálogo de módulos completo, por
    ejemplo— cuyo vocabulario ahogaría al de la petición real si se contara todo por
    igual. Los agentes delimitan cada sección, así que aquí basta con quedarse con la
    primera sección relevante que aparezca.
    """
    for tag in _FOCUS_TAGS:
        opening, closing = f"<{tag}>", f"</{tag}>"
        if opening in text and closing in text:
            return text.split(opening, 1)[1].split(closing, 1)[0]
    return text


def detect_profile(text: str) -> DomainProfile:
    """Elige el perfil cuyo vocabulario aparece más veces en la petición."""
    lowered = focus_section(text).lower()
    best = GENERIC
    best_score = 0
    for profile in _PROFILES:
        score = sum(lowered.count(keyword) for keyword in profile.keywords)
        if score > best_score:
            best, best_score = profile, score
    return best


class FakeLLMClient:
    """Implementación determinista de `LLMClient` guiada por perfiles de dominio."""

    def __init__(self, *, answer_questions: bool = False) -> None:
        #: Cuando es `True` no se emiten preguntas de aclaración, de modo que el
        #: pipeline llega hasta el final en un solo paso (útil en pruebas y demos).
        self.answer_questions = answer_questions
        #: Registro de llamadas, para poder afirmar sobre ellas en las pruebas.
        self.calls: list[tuple[str, str]] = []

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(("complete", prompt[:120]))
        profile = detect_profile(prompt)
        text = (
            "# Guía de inicio\n\n"
            f"{profile.summary}\n\n"
            "## Puesta en marcha\n\n"
            "1. Copia `.env.example` a `.env` y revisa los secretos.\n"
            "2. Ejecuta `./install.sh`.\n"
            "3. Abre http://localhost:3000 para el panel y "
            "http://localhost:8000/docs para la API.\n\n"
            "## Siguientes pasos\n\n"
            "- Crea el primer usuario administrador desde `/auth/register`.\n"
            "- Revisa `docs/DATA_MODEL.md` antes de modificar el esquema.\n"
        )
        return LLMResponse(text=text, model="fake", output_tokens=len(text) // 4)

    async def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append((schema_name, prompt[:120]))
        profile = detect_profile(prompt)
        builders = {
            "requirements": self._requirements,
            "architecture": self._architecture,
            "schema_design": self._schema_design,
            "api_design": self._api_design,
            "code_review": self._code_review,
            "maintenance_plan": self._maintenance,
        }
        builder = builders.get(schema_name)
        data = builder(profile, prompt) if builder else {}
        return LLMResponse(text="", data=data, model="fake", output_tokens=64)

    # ── Constructores por esquema ─────────────────────────────────────────────

    def _requirements(self, profile: DomainProfile, prompt: str) -> dict[str, Any]:
        already_answered = "<respuestas_usuario>" in prompt
        questions = (
            []
            if (self.answer_questions or already_answered)
            else [
                {
                    "id": question_id,
                    "text": text,
                    "rationale": "Determina el alcance funcional del sistema.",
                    "options": list(options),
                    "required": True,
                }
                for question_id, text, options in profile.questions
            ]
        )
        return {
            "business_domain": str(profile.domain),
            "summary": profile.summary,
            "stories": [
                {
                    "id": story_id,
                    "role": role,
                    "goal": goal,
                    "benefit": "",
                    "acceptance_criteria": list(criteria),
                    "priority": priority,
                }
                for story_id, role, goal, criteria, priority in profile.stories
            ],
            "questions": questions,
            "constraints": [
                "La interfaz debe estar en español",
                "El sistema debe funcionar en navegador y móvil",
            ],
            "out_of_scope": ["Integración con sistemas contables externos"],
            "suggested_modules": list(profile.modules),
        }

    def _architecture(self, profile: DomainProfile, prompt: str) -> dict[str, Any]:
        return {
            "modules": list(profile.modules),
            "pages": ["/", "/configuracion"],
            "rationale": (
                "Se elige una pila FastAPI + Next.js sobre PostgreSQL por ser la "
                "combinación con mejor equilibrio entre velocidad de entrega y "
                "capacidad de evolución para este dominio."
            ),
            "tech_stack": {
                "backend": "fastapi",
                "frontend": "nextjs",
                "database": "postgresql",
                "cache": "redis",
            },
        }

    def _schema_design(self, profile: DomainProfile, prompt: str) -> dict[str, Any]:
        return {"entities": [dict(entity) for entity in profile.entities]}

    def _api_design(self, profile: DomainProfile, prompt: str) -> dict[str, Any]:
        # El contrato se deriva de las entidades que llegan en el prompt, no del
        # perfil: en esta etapa el modelo trabaja sobre el modelo de datos ya fijado.
        names = _entity_names(prompt) or [str(entity["name"]) for entity in profile.entities]
        endpoints: list[dict[str, Any]] = []
        for name in names:
            entity = {"name": name}
            resource = table_name_for(str(entity["name"]))
            endpoints.append(
                {
                    "method": "GET",
                    "path": f"/{resource}",
                    "summary": f"Listar {resource}",
                    "entity": entity["name"],
                    "auth_required": True,
                }
            )
            endpoints.append(
                {
                    "method": "POST",
                    "path": f"/{resource}",
                    "summary": f"Crear {entity['name']}",
                    "entity": entity["name"],
                    "auth_required": True,
                }
            )
        return {"endpoints": endpoints}

    def _code_review(self, profile: DomainProfile, prompt: str) -> dict[str, Any]:
        return {
            "verdict": "aprobado_con_reservas",
            "findings": [
                {
                    "severity": "media",
                    "file": "backend/app/dependencies.py",
                    "message": (
                        "La autorización se limita a validar el token; conviene añadir "
                        "comprobación de permisos por recurso antes de exponer la API."
                    ),
                    "suggestion": "Aplicar el módulo de roles en los routers sensibles.",
                },
                {
                    "severity": "baja",
                    "file": ".env.example",
                    "message": "Los secretos de ejemplo deben regenerarse antes de desplegar.",
                    "suggestion": "Documentar la rotación de secretos en el runbook.",
                },
            ],
        }

    def _maintenance(self, profile: DomainProfile, prompt: str) -> dict[str, Any]:
        return {
            "checks": [
                {
                    "name": "Sonda de vida del backend",
                    "frequency": "cada minuto",
                    "action": "Reiniciar el contenedor si /health falla 3 veces seguidas.",
                },
                {
                    "name": "Copia de seguridad de la base de datos",
                    "frequency": "diaria",
                    "action": "Volcado a almacenamiento externo con retención de 30 días.",
                },
                {
                    "name": "Revisión de dependencias",
                    "frequency": "mensual",
                    "action": "Aplicar actualizaciones de seguridad y volver a pasar las pruebas.",
                },
            ],
            "runbook": (
                "Ante un incidente: revisar `docker compose logs backend`, comprobar la "
                "conectividad con PostgreSQL y Redis, y restaurar la última copia si hay "
                "corrupción de datos. Los despliegues se revierten volviendo a la etiqueta "
                "de imagen anterior."
            ),
        }


def _entity_names(prompt: str) -> list[str]:
    """Extrae los nombres de entidad de la sección `<entidades>` del prompt."""
    if "<entidades>" not in prompt:
        return []
    block = prompt.split("<entidades>", 1)[1].split("</entidades>", 1)[0]
    return re.findall(r"^- (\w+) \(", block, flags=re.MULTILINE)
