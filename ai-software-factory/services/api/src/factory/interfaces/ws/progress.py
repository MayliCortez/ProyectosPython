"""WebSocket de progreso en tiempo real.

El socket no consulta la base de datos: se suscribe al canal del proyecto en el bus
de eventos. Como el bus está respaldado por Redis, un cliente conectado a cualquier
réplica de la API recibe los eventos que publique cualquier worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from factory.container import Container
from factory.domain.errors import DomainError

logger = logging.getLogger(__name__)

router = APIRouter()

#: Cadencia del latido que mantiene viva la conexión a través de proxies.
_HEARTBEAT_SECONDS = 25


@router.websocket("/ws/projects/{project_id}")
async def project_progress(websocket: WebSocket, project_id: str) -> None:
    """Emite los eventos del proyecto mientras el cliente esté conectado.

    El token se pasa como parámetro de consulta (`?token=…`) porque el navegador no
    permite cabeceras personalizadas al abrir un WebSocket.
    """
    container: Container = websocket.app.state.container
    token = websocket.query_params.get("token", "")

    try:
        user = await container.auth.user_from_token(token)
        project = await container.projects.get(user=user, project_id=project_id)
    except DomainError as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=exc.message)
        return

    await websocket.accept()
    await websocket.send_json(
        {
            "event": "connection.established",
            "project_id": project_id,
            "payload": {"status": project.status, "live_url": project.live_url},
        }
    )

    heartbeat = asyncio.create_task(_heartbeat(websocket))
    try:
        async for event in container.events.subscribe(project_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.debug("Cliente desconectado del proyecto %s", project_id)
    except Exception:
        logger.exception("Error en el WebSocket del proyecto %s", project_id)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def _heartbeat(websocket: WebSocket) -> None:
    """Mantiene la conexión viva frente a proxies con tiempo de inactividad corto."""
    while True:
        await asyncio.sleep(_HEARTBEAT_SECONDS)
        await websocket.send_json({"event": "heartbeat", "payload": {}})
