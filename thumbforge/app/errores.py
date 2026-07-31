"""Errores del motor. Todos llevan mensaje accionable en castellano."""

from __future__ import annotations


class ErrorThumbforge(Exception):
    """Base. La CLI la atrapa y la imprime sin traceback."""


class ErrorPerfil(ErrorThumbforge):
    """El perfil no existe, no parsea o le falta algo obligatorio."""


class ErrorPolitica(ErrorThumbforge):
    """Un concepto viola una politica dura del perfil."""

    def __init__(self, mensaje: str, violaciones=None):
        super().__init__(mensaje)
        self.violaciones = list(violaciones or [])


class ErrorProveedor(ErrorThumbforge):
    """Fallo hablando con una API externa."""
