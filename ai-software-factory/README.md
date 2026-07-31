# AI Software Factory

Plataforma SaaS que convierte una conversación en lenguaje natural en una aplicación
completa: analiza el requerimiento, pregunta lo que falta, genera una especificación
técnica, construye el código, ejecuta pruebas, empaqueta con Docker y prepara el
despliegue.

```
Usuario  ──chat──▶  Analista ─▶ Arquitecto ─▶ BD ─▶ API ─▶ Backend ─▶ Frontend
                                                                        │
                        Documentación ◀─ Revisor ◀─ Pruebas ◀───────────┘
                                                │
                                          Despliegue ─▶ URL funcional ─▶ Mantenimiento
```

## Estructura del repositorio

| Ruta | Descripción |
|------|-------------|
| `services/api` | Backend Python + FastAPI con arquitectura limpia (dominio / aplicación / infraestructura / interfaces) |
| `services/api/src/factory/agents` | Los 11 agentes especializados y el orquestador |
| `services/api/src/factory/catalog` | Catálogo de 19 módulos reutilizables (instalar / actualizar / eliminar) |
| `services/api/src/factory/codegen` | Motor de generación de código y artefactos de despliegue |
| `apps/web` | Frontend Next.js 15 + TypeScript + Tailwind (panel, editor, despliegues, chat) |
| `docker-compose.yml` | Postgres, Redis, MinIO (S3), API, worker y web |

## Arranque rápido

```bash
cp .env.example .env
make up            # levanta toda la plataforma con Docker
make migrate       # aplica migraciones de base de datos
```

- API: http://localhost:8000 — documentación OpenAPI en `/docs`
- Web: http://localhost:3000
- MinIO (S3): http://localhost:9001

### Demostración en un minuto

Genera un proyecto completo sin Docker, sin red y sin clave de API:

```bash
cd services/api && python scripts/demo.py --salida ./generado
```

Recorre el pipeline entero —análisis, arquitectura, modelo de datos, contrato de API,
backend, frontend, pruebas, revisión, documentación, despliegue y mantenimiento— y deja
en `./generado` una aplicación de 65 ficheros con su `docker-compose.yml`, su pipeline de
CI y su propia suite de pruebas:

```bash
cd generado/gimnasio-titan/backend && pytest -q   # 37 pruebas del proyecto generado
```

### Desarrollo local sin Docker

```bash
make install       # instala dependencias de API y web
make dev-api       # uvicorn con recarga en caliente
make dev-web       # next dev
make test          # pytest + typecheck
```

## Configuración

Todas las variables viven en `.env` (ver `.env.example`). Las esenciales:

| Variable | Descripción |
|----------|-------------|
| `FACTORY_DATABASE_URL` | Cadena de conexión a PostgreSQL |
| `FACTORY_REDIS_URL` | Redis para colas, caché y bus de eventos |
| `FACTORY_JWT_SECRET` | Secreto de firma de tokens (obligatorio en producción) |
| `FACTORY_ANTHROPIC_API_KEY` | Clave de la API de Claude para el motor de IA |
| `FACTORY_LLM_PROVIDER` | `anthropic` o `fake` (determinista, para pruebas y demos sin coste) |
| `FACTORY_S3_*` | Endpoint, bucket y credenciales del almacenamiento compatible con S3 |

Sin `FACTORY_ANTHROPIC_API_KEY` la plataforma arranca igualmente con el proveedor
`fake`: los agentes producen artefactos deterministas, lo que permite ejecutar la
suite completa de pruebas y demostraciones sin llamadas de red.

## Flujo de generación

1. `POST /api/v1/projects` crea el proyecto y abre una conversación.
2. `POST /api/v1/conversations/{id}/messages` envía el requerimiento en lenguaje natural.
3. El **Analista de requisitos** detecta el dominio y devuelve preguntas de aclaración.
4. Al responderlas se genera el **documento de requisitos** y la **especificación técnica**.
5. `POST /api/v1/projects/{id}/build` encola la construcción; el progreso se emite por
   WebSocket en `/ws/projects/{id}`.
6. El resultado queda como *bundle* en el almacenamiento S3, listo para desplegar con
   `POST /api/v1/projects/{id}/deployments`.

## Documentación

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — decisiones de diseño, límites de capas y escalabilidad.
- `services/api/src/factory/catalog/definitions.py` — catálogo de módulos y sus dependencias.

## Licencia

MIT.
