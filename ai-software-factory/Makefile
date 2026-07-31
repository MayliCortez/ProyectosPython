.DEFAULT_GOAL := help
API := services/api
WEB := apps/web

help: ## Muestra esta ayuda
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependencias de API y web
	cd $(API) && python -m pip install -e ".[dev]"
	cd $(WEB) && npm install

dev-api: ## API con recarga en caliente
	cd $(API) && uvicorn factory.interfaces.http.app:create_app --factory --reload --port 8000

dev-worker: ## Worker de la cola de trabajos
	cd $(API) && python -m factory.infrastructure.queue.worker

dev-web: ## Frontend Next.js en modo desarrollo
	cd $(WEB) && npm run dev

demo: ## Genera un proyecto de ejemplo de principio a fin
	cd $(API) && python scripts/demo.py --salida ./generado

test: ## Ejecuta la suite de pruebas del backend
	cd $(API) && pytest -q

test-cov: ## Pruebas con informe de cobertura
	cd $(API) && pytest --cov=factory --cov-report=term-missing

lint: ## Formato y análisis estático
	cd $(API) && ruff check src tests && ruff format --check src tests
	cd $(API) && mypy src

lint-layers: ## Verifica que el dominio no importe capas externas
	@! grep -rnE '^from factory\.(infrastructure|interfaces|agents|codegen)' $(API)/src/factory/domain \
		|| (echo "El dominio no puede importar capas externas" && exit 1)
	@echo "Límites de capas correctos"

typecheck-web: ## Comprueba tipos del frontend
	cd $(WEB) && npm run typecheck

build-web: ## Compila el frontend para producción
	cd $(WEB) && npm run build

migrate: ## Aplica migraciones de base de datos
	cd $(API) && alembic upgrade head

migration: ## Crea una migración nueva: make migration m="mensaje"
	cd $(API) && alembic revision --autogenerate -m "$(m)"

up: ## Levanta toda la plataforma con Docker
	docker compose up -d --build

down: ## Detiene la plataforma
	docker compose down

logs: ## Sigue los logs de la API y el worker
	docker compose logs -f api worker

clean: ## Limpia artefactos locales
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(API)/.pytest_cache $(API)/.mypy_cache $(API)/.ruff_cache $(WEB)/.next

.PHONY: help install demo dev-api dev-worker dev-web test test-cov lint lint-layers \
        typecheck-web build-web migrate migration up down logs clean
