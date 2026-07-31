"""Cache en disco.

Criterio de aceptacion: la segunda corrida con el mismo guion no hace ni una
llamada de red. Para que eso se cumpla, TODO lo que sale a internet -metadata,
anotaciones, conceptos, imagenes descargadas o generadas- entra y sale por
aca, con una clave derivada del contenido de la entrada.

La cache es un volumen: se puede borrar entera sin perder trabajo, solo se
paga de nuevo lo que costo traerlo.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .rutas import dir_cache


def huella(*partes: Any) -> str:
    """sha256 estable de cualquier combinacion de datos serializables.

    `sort_keys` no es decorativo: sin el, dos diccionarios equivalentes dan
    claves distintas y la segunda corrida vuelve a salir a la red.
    """
    h = hashlib.sha256()
    for parte in partes:
        if isinstance(parte, (dict, list, tuple)):
            h.update(json.dumps(parte, sort_keys=True, ensure_ascii=False,
                                default=str).encode("utf-8"))
        elif isinstance(parte, bytes):
            h.update(parte)
        else:
            h.update(str(parte).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


@dataclass
class Estadisticas:
    aciertos: int = 0
    fallos: int = 0

    @property
    def total(self) -> int:
        return self.aciertos + self.fallos

    def __str__(self) -> str:
        return f"{self.aciertos} acierto(s), {self.fallos} fallo(s) de cache"


class Cache:
    """Cache por espacios. Cada modulo usa el suyo: 'videos', 'anotaciones',
    'conceptos', 'imagenes'."""

    def __init__(self, raiz: Path | None = None):
        self.raiz = Path(raiz) if raiz else dir_cache()
        self.stats = Estadisticas()
        self.desactivada = os.environ.get("TF_SIN_CACHE", "").strip() not in (
            "", "0", "false", "no")

    # --- rutas -------------------------------------------------------------
    def ruta(self, espacio: str, clave: str, sufijo: str = ".json") -> Path:
        # Dos niveles de subdirectorio: 65k archivos en una sola carpeta
        # hacen lenta hasta la lista de directorio.
        return self.raiz / espacio / clave[:2] / f"{clave}{sufijo}"

    # --- json --------------------------------------------------------------
    def leer_json(self, espacio: str, clave: str) -> Any | None:
        if self.desactivada:
            return None
        ruta = self.ruta(espacio, clave)
        if not ruta.is_file():
            return None
        try:
            return json.loads(ruta.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def guardar_json(self, espacio: str, clave: str, valor: Any) -> None:
        ruta = self.ruta(espacio, clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # Escritura atomica: un ctrl-C a mitad no deja un JSON truncado que
        # despues se lea como cache valida.
        tmp = ruta.with_suffix(ruta.suffix + ".parcial")
        tmp.write_text(json.dumps(valor, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(ruta)

    # --- bytes -------------------------------------------------------------
    def leer_bytes(self, espacio: str, clave: str, sufijo: str = ".bin") -> bytes | None:
        if self.desactivada:
            return None
        ruta = self.ruta(espacio, clave, sufijo)
        try:
            return ruta.read_bytes() if ruta.is_file() else None
        except OSError:
            return None

    def guardar_bytes(self, espacio: str, clave: str, datos: bytes,
                      sufijo: str = ".bin") -> Path:
        ruta = self.ruta(espacio, clave, sufijo)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_suffix(ruta.suffix + ".parcial")
        tmp.write_bytes(datos)
        tmp.replace(ruta)
        return ruta

    # --- memoizacion -------------------------------------------------------
    def memo(self, espacio: str, clave: str, productor: Callable[[], Any]) -> Any:
        """Devuelve lo cacheado, o llama a `productor` y lo cachea.

        El productor es lo unico que puede salir a la red.
        """
        cacheado = self.leer_json(espacio, clave)
        if cacheado is not None:
            self.stats.aciertos += 1
            return cacheado
        self.stats.fallos += 1
        valor = productor()
        if valor is not None:
            self.guardar_json(espacio, clave, valor)
        return valor

    def memo_bytes(self, espacio: str, clave: str, productor: Callable[[], bytes],
                   sufijo: str = ".bin") -> bytes:
        cacheado = self.leer_bytes(espacio, clave, sufijo)
        if cacheado is not None:
            self.stats.aciertos += 1
            return cacheado
        self.stats.fallos += 1
        datos = productor()
        self.guardar_bytes(espacio, clave, datos, sufijo)
        return datos

    # --- mantenimiento -----------------------------------------------------
    def tamano_bytes(self) -> int:
        if not self.raiz.is_dir():
            return 0
        return sum(f.stat().st_size for f in self.raiz.rglob("*") if f.is_file())

    def espacios(self) -> list[str]:
        if not self.raiz.is_dir():
            return []
        return sorted(d.name for d in self.raiz.iterdir() if d.is_dir())
