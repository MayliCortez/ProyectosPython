"""Genera el pipeline de integración y despliegue continuo del proyecto."""

from __future__ import annotations

from factory.codegen.blueprint import Blueprint
from factory.domain.value_objects import Artifact


def render_ci(blueprint: Blueprint) -> list[Artifact]:
    """Workflow de GitHub Actions y Makefile del proyecto generado."""
    return [_workflow(blueprint), _makefile(blueprint)]


def _workflow(blueprint: Blueprint) -> Artifact:
    body = f"""name: CI/CD

on:
  push:
    branches: [main]
  pull_request:

env:
  IMAGE_NAME: {blueprint.slug}

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: app
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U app"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt pytest pytest-asyncio httpx anyio
      - name: Migraciones
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/app
      - name: Pruebas
        run: pytest -q
        env:
          DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/app

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci || npm install
      - run: npm run typecheck
      - run: npm run build

  deploy:
    needs: [backend, frontend]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}
      - name: Publicar backend
        uses: docker/build-push-action@v6
        with:
          context: ./backend
          push: true
          tags: ghcr.io/${{{{ github.repository }}}}/backend:${{{{ github.sha }}}}
      - name: Publicar frontend
        uses: docker/build-push-action@v6
        with:
          context: ./frontend
          push: true
          tags: ghcr.io/${{{{ github.repository }}}}/frontend:${{{{ github.sha }}}}
"""
    return Artifact(".github/workflows/ci.yml", body, "yaml")


def _makefile(blueprint: Blueprint) -> Artifact:
    body = f"""# {blueprint.name}
.DEFAULT_GOAL := help

help: ## Muestra esta ayuda
\t@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \\
\t\t| awk 'BEGIN{{FS=":.*?## "}}{{printf "  %-12s %s\\n", $$1, $$2}}'

up: ## Levanta la aplicación
\tdocker compose up -d --build

down: ## Detiene la aplicación
\tdocker compose down

logs: ## Sigue los logs del backend
\tdocker compose logs -f backend

migrate: ## Aplica migraciones
\tcd backend && alembic upgrade head

test: ## Ejecuta las pruebas
\tcd backend && pytest -q

.PHONY: help up down logs migrate test
"""
    return Artifact("Makefile", body, "makefile")
