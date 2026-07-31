"""Traducción de los errores de dominio a respuestas HTTP."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from factory.domain.errors import (
    AgentExecutionError,
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger(__name__)

#: Cada error de negocio tiene un código HTTP y solo uno.
_STATUS_BY_ERROR: tuple[tuple[type[DomainError], int], ...] = (
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN),
    (ConflictError, status.HTTP_409_CONFLICT),
    # 422 se escribe numérico: Starlette renombró la constante y avisa por el alias.
    (ValidationError, 422),
    (AgentExecutionError, status.HTTP_502_BAD_GATEWAY),
)


def status_for(error: DomainError) -> int:
    for error_type, code in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return code
    return status.HTTP_400_BAD_REQUEST


def register_error_handlers(app: FastAPI) -> None:
    """Instala los manejadores para que ningún error de dominio escape como 500."""

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        code = status_for(exc)
        if code >= 500:
            logger.error("Error de dominio en %s: %s", request.url.path, exc.message)
        return JSONResponse(
            status_code=code,
            content={"code": exc.code, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado en %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "internal_error",
                "message": "Se ha producido un error inesperado",
                "details": {},
            },
        )
