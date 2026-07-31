"""Puerta unica de salida a la red.

Todo el trafico externo del motor pasa por aca. Sirve para dos cosas:

1. Contar llamadas. El criterio de aceptacion dice "segunda corrida con el
   mismo guion: cero llamadas de red", y eso hay que poder medirlo, no
   suponerlo.
2. Cortar la red de raiz con TF_SIN_RED=1. Si una segunda corrida completa
   con la red cortada, el cacheo funciona de verdad.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field

from .errores import ErrorThumbforge

TIEMPO_LIMITE = 60.0


class ErrorSinRed(ErrorThumbforge):
    """Se intento salir a la red con TF_SIN_RED=1."""


@dataclass
class Contador:
    """Cuantas llamadas salieron, por destino."""

    total: int = 0
    por_destino: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def registrar(self, destino: str) -> None:
        with self._lock:
            self.total += 1
            self.por_destino[destino] = self.por_destino.get(destino, 0) + 1

    def reiniciar(self) -> None:
        with self._lock:
            self.total = 0
            self.por_destino.clear()


LLAMADAS = Contador()


def sin_red() -> bool:
    return os.environ.get("TF_SIN_RED", "").strip() not in ("", "0", "false", "no")


def exigir_red(destino: str) -> None:
    """Contabiliza una salida y la bloquea si el modo offline esta activo."""
    if sin_red():
        raise ErrorSinRed(
            f"TF_SIN_RED=1 y algo intento hablar con '{destino}'. "
            f"En modo sin red el motor solo puede usar lo que ya esta en .cache/. "
            f"Si esto pasa en una segunda corrida del mismo guion, hay un cacheo faltante."
        )
    LLAMADAS.registrar(destino)


def cliente(destino: str, **kwargs):
    """httpx.Client que ya conto la llamada. Usar como context manager."""
    import httpx

    exigir_red(destino)
    kwargs.setdefault("timeout", TIEMPO_LIMITE)
    kwargs.setdefault("follow_redirects", True)
    return httpx.Client(**kwargs)
