"""Tablas y colores para la terminal, sin dependencias.

Se evita rich a proposito: cada MB cuenta para el objetivo de 600 MB y para
la via de reparto por tarball.
"""

from __future__ import annotations

import os
import sys
import unicodedata

OK = "OK"
AVISO = "AVISO"
ERROR = "ERROR"

_COLORES = {OK: "\033[32m", AVISO: "\033[33m", ERROR: "\033[31m"}
_RESET = "\033[0m"


def color_activo() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TF_FORZAR_COLOR"):
        return True
    return sys.stdout.isatty()


def estado(texto: str) -> str:
    if not color_activo() or texto not in _COLORES:
        return texto
    return f"{_COLORES[texto]}{texto}{_RESET}"


def _ancho(texto: str) -> int:
    """Ancho visual aproximado: descuenta combinantes, cuenta anchos dobles."""
    total = 0
    for ch in texto:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def _rellenar(texto: str, ancho: int) -> str:
    return texto + " " * max(0, ancho - _ancho(texto))


def tabla(encabezados: list[str], filas: list[list[str]]) -> str:
    """Tabla de ancho fijo. La columna de estado se colorea al imprimir."""
    cols = len(encabezados)
    anchos = [_ancho(h) for h in encabezados]
    for fila in filas:
        for i in range(cols):
            anchos[i] = max(anchos[i], _ancho(str(fila[i])))

    sep = "  "
    lineas = [sep.join(_rellenar(h, anchos[i]) for i, h in enumerate(encabezados)).rstrip()]
    lineas.append(sep.join("-" * a for a in anchos))
    for fila in filas:
        celdas = []
        for i in range(cols):
            texto = str(fila[i])
            relleno = _rellenar(texto, anchos[i])
            if texto in _COLORES:
                relleno = estado(texto) + relleno[len(texto):]
            celdas.append(relleno)
        lineas.append(sep.join(celdas).rstrip())
    return "\n".join(lineas)


def titulo(texto: str) -> str:
    return f"\n{texto}\n{'=' * _ancho(texto)}"
