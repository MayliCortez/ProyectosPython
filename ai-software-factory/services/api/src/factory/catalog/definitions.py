"""Definición del catálogo estándar de módulos reutilizables.

Añadir un módulo nuevo consiste en declarar aquí su manifiesto: el instalador, los
generadores de código y el panel lo recogen automáticamente.
"""

from __future__ import annotations

from factory.catalog.manifest import (
    ModuleCategory,
    ModuleEndpoint,
    ModuleManifest,
    ModulePage,
    ModuleTable,
)
from factory.domain.value_objects import SemVer

_V1 = SemVer(1, 0, 0)


def _m(**kwargs: object) -> ModuleManifest:
    """Atajo tipado para declarar manifiestos sin repetir la versión."""
    kwargs.setdefault("version", _V1)
    return ModuleManifest(**kwargs)  # type: ignore[arg-type]


USERS = _m(
    key="users",
    name="Usuarios",
    description="Gestión de cuentas, perfiles y estados de usuario. Base de todo el resto.",
    category=ModuleCategory.CORE,
    tables=(
        ModuleTable(
            "users",
            ("id", "email", "password_hash", "full_name", "is_active", "created_at"),
            "Cuentas del sistema",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/users", "Listar usuarios"),
        ModuleEndpoint("POST", "/users", "Crear usuario"),
        ModuleEndpoint("GET", "/users/{id}", "Detalle de usuario"),
        ModuleEndpoint("PATCH", "/users/{id}", "Actualizar usuario"),
        ModuleEndpoint("DELETE", "/users/{id}", "Desactivar usuario"),
    ),
    pages=(ModulePage("/usuarios", "Usuarios", "users"),),
    permissions=("users.read", "users.write"),
    removable=False,
)

LOGIN = _m(
    key="login",
    name="Login",
    description="Autenticación con JWT, registro, recuperación de contraseña y sesión.",
    category=ModuleCategory.CORE,
    depends_on=("users",),
    tables=(
        ModuleTable("sessions", ("id", "user_id", "token_hash", "expires_at"), "Sesiones activas"),
    ),
    endpoints=(
        ModuleEndpoint("POST", "/auth/register", "Registro"),
        ModuleEndpoint("POST", "/auth/login", "Inicio de sesión"),
        ModuleEndpoint("POST", "/auth/refresh", "Renovar token"),
        ModuleEndpoint("POST", "/auth/logout", "Cerrar sesión"),
        ModuleEndpoint("GET", "/auth/me", "Usuario actual"),
    ),
    pages=(ModulePage("/login", "Iniciar sesión", "log-in"),),
    env_vars=("JWT_SECRET", "JWT_TTL_MINUTES"),
    python_packages=("pyjwt",),
    removable=False,
)

ROLES = _m(
    key="roles",
    name="Roles y permisos",
    description="Control de acceso por rol y permisos granulares sobre cada recurso.",
    category=ModuleCategory.CORE,
    depends_on=("users",),
    tables=(
        ModuleTable("roles", ("id", "name", "description"), "Roles disponibles"),
        ModuleTable("permissions", ("id", "code", "description"), "Permisos atómicos"),
        ModuleTable("role_permissions", ("role_id", "permission_id"), "Asignación de permisos"),
        ModuleTable("user_roles", ("user_id", "role_id"), "Roles por usuario"),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/roles", "Listar roles"),
        ModuleEndpoint("POST", "/roles", "Crear rol"),
        ModuleEndpoint("PUT", "/roles/{id}/permissions", "Asignar permisos"),
        ModuleEndpoint("POST", "/users/{id}/roles", "Asignar rol a usuario"),
    ),
    pages=(ModulePage("/roles", "Roles", "shield"),),
    permissions=("roles.read", "roles.write"),
)

DASHBOARD = _m(
    key="dashboard",
    name="Dashboard",
    description="Panel de inicio con métricas, indicadores y accesos rápidos.",
    category=ModuleCategory.CORE,
    depends_on=("login",),
    endpoints=(ModuleEndpoint("GET", "/dashboard/metrics", "Métricas del panel"),),
    pages=(ModulePage("/", "Inicio", "layout-dashboard"),),
    npm_packages=("recharts",),
)

INVENTORY = _m(
    key="inventory",
    name="Inventario",
    description="Productos, existencias, movimientos de stock y alertas de mínimos.",
    category=ModuleCategory.OPERATIONS,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "products",
            ("id", "sku", "name", "description", "price", "cost", "is_active"),
            "Catálogo de productos",
        ),
        ModuleTable("warehouses", ("id", "name", "address"), "Almacenes"),
        ModuleTable(
            "stock_levels", ("product_id", "warehouse_id", "quantity", "min_quantity"), "Stock"
        ),
        ModuleTable(
            "stock_movements",
            ("id", "product_id", "warehouse_id", "quantity", "reason", "created_at"),
            "Movimientos de stock",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/products", "Listar productos"),
        ModuleEndpoint("POST", "/products", "Crear producto"),
        ModuleEndpoint("GET", "/stock", "Consultar existencias"),
        ModuleEndpoint("POST", "/stock/movements", "Registrar movimiento"),
    ),
    pages=(
        ModulePage("/inventario", "Inventario", "package"),
        ModulePage("/inventario/movimientos", "Movimientos", "arrow-left-right"),
    ),
    permissions=("inventory.read", "inventory.write"),
)

BILLING = _m(
    key="billing",
    name="Facturación",
    description="Facturas, líneas de detalle, impuestos, vencimientos y estados de cobro.",
    category=ModuleCategory.COMMERCE,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "invoices",
            ("id", "number", "customer_id", "issued_at", "due_at", "total", "status"),
            "Facturas emitidas",
        ),
        ModuleTable(
            "invoice_lines",
            ("id", "invoice_id", "description", "quantity", "unit_price", "tax_rate"),
            "Líneas de factura",
        ),
        ModuleTable("taxes", ("id", "name", "rate"), "Impuestos aplicables"),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/invoices", "Listar facturas"),
        ModuleEndpoint("POST", "/invoices", "Emitir factura"),
        ModuleEndpoint("GET", "/invoices/{id}/pdf", "Descargar PDF"),
        ModuleEndpoint("POST", "/invoices/{id}/void", "Anular factura"),
    ),
    pages=(ModulePage("/facturacion", "Facturación", "receipt"),),
    permissions=("billing.read", "billing.write"),
    python_packages=("reportlab",),
)

CRM = _m(
    key="crm",
    name="CRM",
    description="Clientes, contactos, oportunidades y seguimiento del embudo de ventas.",
    category=ModuleCategory.COMMERCE,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "customers", ("id", "name", "email", "phone", "tax_id", "created_at"), "Clientes"
        ),
        ModuleTable("contacts", ("id", "customer_id", "name", "role", "email"), "Contactos"),
        ModuleTable(
            "opportunities",
            ("id", "customer_id", "title", "amount", "stage", "owner_id", "closes_at"),
            "Oportunidades",
        ),
        ModuleTable(
            "activities", ("id", "customer_id", "type", "notes", "created_at"), "Interacciones"
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/customers", "Listar clientes"),
        ModuleEndpoint("POST", "/customers", "Crear cliente"),
        ModuleEndpoint("GET", "/opportunities", "Embudo de ventas"),
        ModuleEndpoint("PATCH", "/opportunities/{id}", "Mover de etapa"),
    ),
    pages=(
        ModulePage("/clientes", "Clientes", "contact"),
        ModulePage("/oportunidades", "Oportunidades", "trending-up"),
    ),
    permissions=("crm.read", "crm.write"),
)

CALENDAR = _m(
    key="agenda",
    name="Agenda",
    description="Calendario de eventos, disponibilidad de recursos y recordatorios.",
    category=ModuleCategory.OPERATIONS,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "events",
            ("id", "title", "starts_at", "ends_at", "owner_id", "resource_id", "notes"),
            "Eventos del calendario",
        ),
        ModuleTable("resources", ("id", "name", "type", "capacity"), "Recursos reservables"),
        ModuleTable(
            "availability_rules",
            ("id", "resource_id", "weekday", "start_time", "end_time"),
            "Franjas de disponibilidad",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/events", "Listar eventos"),
        ModuleEndpoint("POST", "/events", "Crear evento"),
        ModuleEndpoint("GET", "/availability", "Consultar disponibilidad"),
    ),
    pages=(ModulePage("/agenda", "Agenda", "calendar"),),
    permissions=("agenda.read", "agenda.write"),
)

RESERVATIONS = _m(
    key="reservas",
    name="Reservas",
    description="Reserva de recursos con confirmación, cancelación y control de aforo.",
    category=ModuleCategory.OPERATIONS,
    depends_on=("agenda",),
    tables=(
        ModuleTable(
            "reservations",
            ("id", "resource_id", "customer_id", "starts_at", "ends_at", "status", "party_size"),
            "Reservas",
        ),
        ModuleTable(
            "reservation_policies",
            ("id", "resource_id", "min_notice_minutes", "max_party_size", "cancellation_hours"),
            "Políticas de reserva",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/reservations", "Listar reservas"),
        ModuleEndpoint("POST", "/reservations", "Crear reserva"),
        ModuleEndpoint("POST", "/reservations/{id}/cancel", "Cancelar reserva"),
        ModuleEndpoint("POST", "/reservations/{id}/confirm", "Confirmar reserva"),
    ),
    pages=(ModulePage("/reservas", "Reservas", "calendar-check"),),
    permissions=("reservations.read", "reservations.write"),
)

CHAT = _m(
    key="chat",
    name="Chat",
    description="Mensajería interna en tiempo real por canales y mensajes directos.",
    category=ModuleCategory.ENGAGEMENT,
    depends_on=("users", "notificaciones"),
    tables=(
        ModuleTable("channels", ("id", "name", "is_private", "created_at"), "Canales"),
        ModuleTable("channel_members", ("channel_id", "user_id", "joined_at"), "Miembros"),
        ModuleTable(
            "chat_messages", ("id", "channel_id", "user_id", "body", "created_at"), "Mensajes"
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/channels", "Listar canales"),
        ModuleEndpoint("POST", "/channels/{id}/messages", "Enviar mensaje"),
        ModuleEndpoint("GET", "/channels/{id}/messages", "Historial"),
    ),
    pages=(ModulePage("/chat", "Chat", "message-square"),),
    permissions=("chat.read", "chat.write"),
)

NOTIFICATIONS = _m(
    key="notificaciones",
    name="Notificaciones",
    description="Avisos in-app, correo y webhooks con preferencias por usuario.",
    category=ModuleCategory.ENGAGEMENT,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "notifications",
            ("id", "user_id", "channel", "title", "body", "read_at", "created_at"),
            "Notificaciones",
        ),
        ModuleTable(
            "notification_preferences",
            ("user_id", "channel", "enabled"),
            "Preferencias de canal",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/notifications", "Bandeja de notificaciones"),
        ModuleEndpoint("POST", "/notifications/{id}/read", "Marcar como leída"),
        ModuleEndpoint("PUT", "/notifications/preferences", "Actualizar preferencias"),
    ),
    pages=(ModulePage("/notificaciones", "Notificaciones", "bell"),),
    env_vars=("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"),
)

REPORTS = _m(
    key="reportes",
    name="Reportes",
    description="Informes configurables con filtros, agregaciones y exportación a CSV/PDF.",
    category=ModuleCategory.INTELLIGENCE,
    depends_on=("dashboard",),
    tables=(
        ModuleTable(
            "report_definitions",
            ("id", "name", "query", "parameters", "created_by"),
            "Definiciones de informe",
        ),
        ModuleTable(
            "report_runs",
            ("id", "report_id", "parameters", "output_key", "created_at"),
            "Ejecuciones",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/reports", "Listar informes"),
        ModuleEndpoint("POST", "/reports/{id}/run", "Ejecutar informe"),
        ModuleEndpoint("GET", "/reports/runs/{id}/export", "Exportar resultado"),
    ),
    pages=(ModulePage("/reportes", "Reportes", "bar-chart-3"),),
    permissions=("reports.read", "reports.run"),
)

AI = _m(
    key="ia",
    name="IA",
    description="Asistente conversacional, búsqueda semántica y resúmenes sobre los datos.",
    category=ModuleCategory.INTELLIGENCE,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "ai_conversations",
            ("id", "user_id", "title", "created_at"),
            "Conversaciones del asistente",
        ),
        ModuleTable(
            "ai_messages", ("id", "conversation_id", "role", "content", "tokens"), "Mensajes"
        ),
        ModuleTable("embeddings", ("id", "entity", "entity_id", "vector"), "Índice semántico"),
    ),
    endpoints=(
        ModuleEndpoint("POST", "/ai/chat", "Conversar con el asistente"),
        ModuleEndpoint("POST", "/ai/search", "Búsqueda semántica"),
        ModuleEndpoint("POST", "/ai/summarize", "Resumir un registro"),
    ),
    pages=(ModulePage("/asistente", "Asistente", "sparkles"),),
    env_vars=("ANTHROPIC_API_KEY", "AI_MODEL"),
    python_packages=("anthropic",),
)

STORE = _m(
    key="tienda",
    name="Tienda online",
    description="Escaparate, carrito, checkout y seguimiento de pedidos.",
    category=ModuleCategory.COMMERCE,
    depends_on=("inventory", "pagos"),
    tables=(
        ModuleTable("carts", ("id", "customer_id", "status", "created_at"), "Carritos"),
        ModuleTable("cart_items", ("cart_id", "product_id", "quantity", "unit_price"), "Líneas"),
        ModuleTable(
            "orders",
            ("id", "customer_id", "total", "status", "shipping_address", "created_at"),
            "Pedidos",
        ),
        ModuleTable("order_items", ("order_id", "product_id", "quantity", "unit_price"), "Detalle"),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/catalog", "Escaparate público"),
        ModuleEndpoint("POST", "/cart/items", "Añadir al carrito"),
        ModuleEndpoint("POST", "/checkout", "Finalizar compra"),
        ModuleEndpoint("GET", "/orders", "Mis pedidos"),
    ),
    pages=(
        ModulePage("/tienda", "Tienda", "shopping-bag"),
        ModulePage("/pedidos", "Pedidos", "truck"),
    ),
    permissions=("store.read", "store.manage"),
)

PAYMENTS = _m(
    key="pagos",
    name="Pasarelas de pago",
    description="Cobros con Stripe o PayPal, reembolsos y conciliación por webhook.",
    category=ModuleCategory.COMMERCE,
    depends_on=("billing",),
    tables=(
        ModuleTable(
            "payments",
            ("id", "invoice_id", "provider", "provider_ref", "amount", "status", "created_at"),
            "Cobros",
        ),
        ModuleTable(
            "refunds", ("id", "payment_id", "amount", "reason", "created_at"), "Reembolsos"
        ),
        ModuleTable(
            "payment_webhooks",
            ("id", "provider", "event_type", "payload", "processed_at"),
            "Webhooks",
        ),
    ),
    endpoints=(
        ModuleEndpoint("POST", "/payments/intent", "Crear intención de pago"),
        ModuleEndpoint("POST", "/payments/webhook", "Webhook del proveedor"),
        ModuleEndpoint("POST", "/payments/{id}/refund", "Reembolsar"),
    ),
    pages=(ModulePage("/pagos", "Pagos", "credit-card"),),
    env_vars=("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
    python_packages=("stripe",),
    permissions=("payments.read", "payments.write"),
)

MULTI_TENANT = _m(
    key="multiempresa",
    name="Multiempresa",
    description="Varias empresas en la misma instancia con datos y usuarios aislados.",
    category=ModuleCategory.PLATFORM,
    depends_on=("users", "roles"),
    tables=(
        ModuleTable("companies", ("id", "name", "slug", "settings", "created_at"), "Empresas"),
        ModuleTable("company_members", ("company_id", "user_id", "role_id"), "Pertenencia"),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/companies", "Listar empresas"),
        ModuleEndpoint("POST", "/companies", "Crear empresa"),
        ModuleEndpoint("POST", "/companies/{id}/switch", "Cambiar de empresa activa"),
    ),
    pages=(ModulePage("/empresas", "Empresas", "building-2"),),
    permissions=("companies.read", "companies.manage"),
)

PUBLIC_API = _m(
    key="api-publica",
    name="API pública",
    description="Claves de API, límites de uso y documentación OpenAPI para terceros.",
    category=ModuleCategory.PLATFORM,
    depends_on=("login",),
    tables=(
        ModuleTable(
            "api_keys",
            ("id", "user_id", "name", "key_hash", "scopes", "last_used_at", "revoked_at"),
            "Claves de API",
        ),
        ModuleTable(
            "api_usage", ("id", "api_key_id", "endpoint", "count", "window_start"), "Consumo"
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/api-keys", "Listar claves"),
        ModuleEndpoint("POST", "/api-keys", "Emitir clave"),
        ModuleEndpoint("DELETE", "/api-keys/{id}", "Revocar clave"),
    ),
    pages=(ModulePage("/api", "API pública", "key"),),
    env_vars=("API_RATE_LIMIT_PER_MINUTE",),
    permissions=("api_keys.manage",),
)

AUDIT = _m(
    key="auditoria",
    name="Auditoría",
    description="Rastro inmutable de quién cambió qué, cuándo y desde dónde.",
    category=ModuleCategory.PLATFORM,
    depends_on=("users",),
    tables=(
        ModuleTable(
            "audit_entries",
            ("id", "actor_id", "action", "entity", "entity_id", "diff", "ip", "created_at"),
            "Entradas de auditoría",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/audit", "Consultar auditoría"),
        ModuleEndpoint("GET", "/audit/{entity}/{id}", "Historial de un registro"),
    ),
    pages=(ModulePage("/auditoria", "Auditoría", "history"),),
    permissions=("audit.read",),
)

LOGS = _m(
    key="logs",
    name="Logs",
    description="Registro estructurado de la aplicación con búsqueda y niveles.",
    category=ModuleCategory.PLATFORM,
    tables=(
        ModuleTable(
            "app_logs",
            ("id", "level", "logger", "message", "context", "created_at"),
            "Registro de aplicación",
        ),
    ),
    endpoints=(
        ModuleEndpoint("GET", "/logs", "Consultar logs"),
        ModuleEndpoint("GET", "/logs/stream", "Seguir logs en vivo"),
    ),
    pages=(ModulePage("/logs", "Logs", "scroll-text"),),
    env_vars=("LOG_LEVEL",),
    permissions=("logs.read",),
)


#: Catálogo estándar entregado con la plataforma.
STANDARD_MODULES: tuple[ModuleManifest, ...] = (
    USERS,
    LOGIN,
    ROLES,
    DASHBOARD,
    INVENTORY,
    BILLING,
    CRM,
    CALENDAR,
    RESERVATIONS,
    CHAT,
    NOTIFICATIONS,
    REPORTS,
    AI,
    STORE,
    PAYMENTS,
    MULTI_TENANT,
    PUBLIC_API,
    AUDIT,
    LOGS,
)
