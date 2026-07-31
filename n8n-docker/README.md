# n8n Local con Docker

Setup completo de **n8n Community Edition** (gratuito) con Docker Compose y PostgreSQL.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) instalado
- [Docker Compose](https://docs.docker.com/compose/install/) instalado (viene incluido con Docker Desktop)

## Inicio rapido

### 1. Configurar variables de entorno

```bash
cd n8n-docker
cp .env.example .env
```

Edita el archivo `.env` y cambia las passwords por unas seguras.

### 2. Levantar los servicios

```bash
docker compose up -d
```

### 3. Acceder a n8n

Abre tu navegador en: **http://localhost:5678**

La primera vez te pedira crear una cuenta de propietario (email + password). Esta cuenta es la que usaras para entrar a n8n.

## Comandos utiles

| Comando | Descripcion |
|---------|-------------|
| `docker compose up -d` | Iniciar n8n en segundo plano |
| `docker compose down` | Detener n8n |
| `docker compose down -v` | Detener y borrar todos los datos |
| `docker compose logs -f n8n` | Ver logs de n8n en tiempo real |
| `docker compose logs -f postgres` | Ver logs de PostgreSQL |
| `docker compose restart n8n` | Reiniciar solo n8n |
| `docker compose pull` | Actualizar a la ultima version de n8n |
| `docker compose up -d --force-recreate` | Recrear contenedores (despues de actualizar) |

## Estructura

```
n8n-docker/
├── docker-compose.yml    # Definicion de servicios (n8n + PostgreSQL)
├── .env                  # Variables de entorno (NO se sube a git)
├── .env.example          # Plantilla de variables de entorno
├── .gitignore            # Ignora .env y local-files/
├── local-files/          # Carpeta compartida con n8n (para leer/escribir archivos)
└── README.md             # Este archivo
```

## Que incluye

- **n8n Community Edition**: Plataforma de automatizacion gratuita y open source
- **PostgreSQL 16**: Base de datos para persistencia (tus workflows se guardan aqui)
- **Volumenes Docker**: Los datos persisten aunque reinicies los contenedores

## Carpeta local-files

La carpeta `local-files/` esta montada dentro del contenedor de n8n en `/files`. Puedes usarla para:

- Leer archivos CSV, JSON, etc. desde tus workflows
- Guardar archivos generados por n8n
- Compartir datos entre tu maquina y n8n

## Personalizar el puerto

Si el puerto 5678 esta ocupado, cambia `N8N_PORT` en tu archivo `.env`:

```
N8N_PORT=5679
```

Y accede en: `http://localhost:5679`

## Personalizar la zona horaria

Cambia `GENERIC_TIMEZONE` en tu archivo `.env`. Ejemplos:

- `America/Mexico_City`
- `America/Bogota`
- `America/Argentina/Buenos_Aires`
- `Europe/Madrid`

Lista completa: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

## Backup y restauracion

### Exportar workflows

Desde n8n puedes exportar workflows individuales o todos a la vez en formato JSON.

### Backup de la base de datos

```bash
docker compose exec postgres pg_dump -U n8n_user n8n_db > backup_n8n.sql
```

### Restaurar base de datos

```bash
cat backup_n8n.sql | docker compose exec -T postgres psql -U n8n_user n8n_db
```

## Actualizar n8n

```bash
docker compose pull
docker compose up -d --force-recreate
```

## Resolver problemas

### n8n no inicia
Revisa los logs: `docker compose logs -f n8n`

### Error de conexion a PostgreSQL
Verifica que PostgreSQL este corriendo: `docker compose ps`

### Perdi mi password de n8n
Detén todo y borra los volumenes para empezar de cero:
```bash
docker compose down -v
docker compose up -d
```
