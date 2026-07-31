"""Sondas de vida y disponibilidad."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from factory import __version__
from factory.interfaces.http.deps import ContainerDep

router = APIRouter(tags=["sistema"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Sonda de vida: responde mientras el proceso esté en pie."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready(container: ContainerDep) -> dict[str, Any]:
    """Sonda de disponibilidad: comprueba las dependencias externas."""
    checks: dict[str, str] = {}

    try:
        async with container.database.session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — el detalle va al informe, no al log
        checks["database"] = f"error: {exc}"

    if container.redis is None:
        checks["redis"] = "no configurado"
    else:
        try:
            await container.redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc}"

    checks["llm"] = container.settings.llm_provider
    ready_now = all(not value.startswith("error") for value in checks.values())
    return {"status": "ok" if ready_now else "degraded", "checks": checks}
