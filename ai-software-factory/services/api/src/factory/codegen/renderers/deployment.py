"""Genera los artefactos de despliegue: Docker, compose, entorno y scripts."""

from __future__ import annotations

from factory.codegen.blueprint import Blueprint
from factory.domain.value_objects import Artifact

_DEFAULT_ENV_VALUES: dict[str, str] = {
    "DATABASE_URL": "postgresql+asyncpg://app:app@postgres:5432/app",
    "REDIS_URL": "redis://redis:6379/0",
    "ENVIRONMENT": "production",
    "SECRET_KEY": "cambia-esto",
    "JWT_SECRET": "cambia-esto",
    "JWT_TTL_MINUTES": "720",
    "LOG_LEVEL": "INFO",
    "API_RATE_LIMIT_PER_MINUTE": "120",
}


def render_deployment(blueprint: Blueprint) -> list[Artifact]:
    """Dockerfile por servicio, compose, variables de entorno y script de instalación."""
    return [
        _backend_dockerfile(blueprint),
        _frontend_dockerfile(),
        _compose(blueprint),
        _env_example(blueprint),
        _install_script(blueprint),
        _dockerignore(),
    ]


def _backend_dockerfile(blueprint: Blueprint) -> Artifact:
    body = f"""# Backend de {blueprint.name}
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends build-essential curl \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \\
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
    return Artifact("backend/Dockerfile", body, "dockerfile")


def _frontend_dockerfile() -> Artifact:
    body = """FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER node
EXPOSE 3000
CMD ["node", "server.js"]
"""
    return Artifact("frontend/Dockerfile", body, "dockerfile")


def _compose(blueprint: Blueprint) -> Artifact:
    body = f"""name: {blueprint.slug}

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  backend:
    build: ./backend
    env_file: .env
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000"
    ports:
      - "8000:8000"
    depends_on:
      postgres: {{condition: service_healthy}}
      redis: {{condition: service_healthy}}

  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  postgres-data:
  redis-data:
"""
    return Artifact("docker-compose.yml", body, "yaml")


def _env_example(blueprint: Blueprint) -> Artifact:
    lines = [f"# Variables de entorno de {blueprint.name}", ""]
    for var in blueprint.env_vars:
        lines.append(f"{var}={_DEFAULT_ENV_VALUES.get(var, '')}")
    lines.append("")
    return Artifact(".env.example", "\n".join(lines), "text")


def _install_script(blueprint: Blueprint) -> Artifact:
    body = f"""#!/usr/bin/env bash
# Instalación de {blueprint.name}
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker es necesario para continuar." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Se ha creado .env a partir de .env.example — revisa los secretos antes de exponerlo."
fi

echo "Construyendo imágenes…"
docker compose build

echo "Levantando servicios…"
docker compose up -d

echo "Esperando a que el backend responda…"
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo
    echo "  {blueprint.name} está en marcha"
    echo "  API : http://localhost:8000/docs"
    echo "  Web : http://localhost:3000"
    exit 0
  fi
  sleep 2
done

echo "El backend no respondió a tiempo. Revisa: docker compose logs backend" >&2
exit 1
"""
    return Artifact("install.sh", body, "bash")


def _dockerignore() -> Artifact:
    body = """node_modules
.next
__pycache__
*.pyc
.venv
.env
.git
tests
"""
    return Artifact(".dockerignore", body, "text")
