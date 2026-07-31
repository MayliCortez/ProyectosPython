# Arquitectura

## Principios

1. **Arquitectura limpia.** El dominio no conoce a nadie. La aplicación define *puertos*
   (interfaces); la infraestructura los implementa. Las interfaces HTTP/WS son un detalle
   de entrega intercambiable.
2. **Todo lo lento va a una cola.** Ninguna petición HTTP espera a un agente de IA.
3. **Los módulos son unidades autónomas.** Instalar, actualizar o eliminar un módulo no
   puede romper el resto: cada uno declara sus dependencias, migraciones y puntos de
   extensión.
4. **Determinismo comprobable.** Todo agente puede ejecutarse con un LLM falso y
   determinista, de modo que el pipeline completo es testeable sin red.

## Capas del backend

```
services/api/src/factory/
├── domain/            ← entidades, objetos de valor, eventos, errores. Cero dependencias.
├── application/       ← casos de uso + puertos (repositorios, LLM, cola, storage, bus)
├── agents/            ← agentes especializados + orquestador (consumen puertos)
├── catalog/           ← catálogo de módulos reutilizables
├── codegen/           ← renderizado de proyectos y artefactos de despliegue
├── infrastructure/    ← SQLAlchemy, Redis, S3, Anthropic, JWT (implementan los puertos)
└── interfaces/        ← FastAPI (REST) y WebSockets
```

Regla de dependencia: las flechas apuntan siempre hacia adentro.
`interfaces → application → domain`, y `infrastructure → application` (implementando sus
puertos). Ningún módulo de `domain` importa nada de las capas exteriores; esto se puede
verificar con `make lint-layers`.

## Servicios separados

| Servicio | Responsabilidad | Escala por |
|----------|-----------------|------------|
| `api` | REST + WebSockets, transaccional y de baja latencia | peticiones/seg |
| `worker` | Ejecución del pipeline de agentes y generación de código | trabajos en cola |
| `postgres` | Estado durable: proyectos, conversaciones, especificaciones, builds | datos |
| `redis` | Cola de trabajos, bus de eventos de progreso, caché | throughput |
| `s3` | Artefactos generados (bundles de proyectos) | almacenamiento |

El motor de IA (`agents/`), el generador de código (`codegen/`) y el servicio de
despliegue (`application/services/deployment_service.py`) son módulos independientes con
sus propios puertos; extraerlos a procesos separados no requiere tocar el dominio.

## Orquestación de agentes

El `Orchestrator` ejecuta un **pipeline** declarativo. Cada `Agent` implementa
`run(context) -> AgentResult` y declara `requires` / `produces`, lo que permite:

- validar el pipeline antes de ejecutarlo (no faltan artefactos de entrada),
- ejecutar en paralelo las etapas sin dependencias entre sí,
- reintentar una etapa concreta sin repetir el pipeline completo,
- emitir progreso por cada etapa hacia el WebSocket.

```
requirements_analyst ─▶ software_architect ─┬▶ database_designer ─▶ api_designer
                                            │                          │
                                            │        ┌─────────────────┴────────────┐
                                            │        ▼                              ▼
                                            │  backend_generator            frontend_generator
                                            │        └──────────────┬───────────────┘
                                            │                       ▼
                                            └──────────────▶ test_generator ─▶ code_reviewer
                                                                                   │
                                                              doc_generator ◀───────┤
                                                                                   ▼
                                                                        deployment_agent
                                                                                   │
                                                                        maintenance_agent
```

## Módulos reutilizables

Un módulo es un `ModuleManifest`: clave, versión, dependencias, tablas, endpoints,
rutas de frontend, permisos y variables de entorno. El `ModuleInstaller` resuelve el
grafo de dependencias en orden topológico y rechaza:

- instalar un módulo cuyas dependencias no están presentes,
- eliminar un módulo del que dependen otros instalados,
- conflictos de versión mayor entre un módulo y sus dependientes.

Esto es lo que garantiza que instalar/eliminar no afecte al resto del sistema.

## Escalabilidad

- **Sin estado en `api`.** Cualquier réplica atiende cualquier petición; el estado de
  sesión es un JWT y el progreso viaja por Redis pub/sub, así que un WebSocket abierto
  contra la réplica A recibe eventos publicados por un worker en el nodo B.
- **Workers horizontales.** La cola es una lista Redis con reclamación por token; añadir
  workers escala linealmente los proyectos concurrentes.
- **Aislamiento por proyecto.** Cada build escribe en su propio prefijo de S3 y su propio
  registro de `builds`; no hay estado compartido entre proyectos.
- **Multiempresa.** Toda fila raíz cuelga de `organization_id`, lo que permite pasar a
  particionado o base por tenant sin cambios de dominio.

## Seguridad

- Contraseñas con PBKDF2-SHA256 y sal por usuario.
- Tokens JWT firmados HS256 con expiración corta y `sub`/`org` en el payload.
- Autorización por pertenencia a organización en cada repositorio consultado.
- El código generado nunca se ejecuta dentro del proceso de la API: se empaqueta y se
  entrega al servicio de despliegue, que lo corre en contenedores aislados.
