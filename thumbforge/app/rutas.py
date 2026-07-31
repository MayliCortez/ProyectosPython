"""Resolucion de rutas. Los cuatro directorios de trabajo son volumenes:
el codigo nunca escribe fuera de ellos, y actualizar la app no borra nada.
"""

from __future__ import annotations

import os
from pathlib import Path

# Raiz del paquete instalado (dentro del contenedor: /app).
RAIZ_APP = Path(__file__).resolve().parent.parent

VOLUMENES = ("perfiles", "data", "salida", "cache")

_ENV = {
    "perfiles": "TF_PERFILES_DIR",
    "data": "TF_DATA_DIR",
    "salida": "TF_SALIDA_DIR",
    "cache": "TF_CACHE_DIR",
}

_DEFECTO = {
    "perfiles": "perfiles",
    "data": "data",
    "salida": "salida",
    "cache": ".cache",
}


def dir_volumen(nombre: str) -> Path:
    """Directorio de un volumen, override por variable de entorno."""
    if nombre not in _ENV:
        raise KeyError(f"volumen desconocido: {nombre}")
    valor = os.environ.get(_ENV[nombre])
    if valor:
        return Path(valor).expanduser().resolve()
    return (RAIZ_APP / _DEFECTO[nombre]).resolve()


def dir_perfiles() -> Path:
    return dir_volumen("perfiles")


def dir_data() -> Path:
    return dir_volumen("data")


def dir_salida() -> Path:
    return dir_volumen("salida")


def dir_cache() -> Path:
    return dir_volumen("cache")
