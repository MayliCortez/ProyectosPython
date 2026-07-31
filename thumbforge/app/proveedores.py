"""Registro de proveedores externos.

Declarativo a proposito: `doctor` recorre esta lista para verificar claves y
hacer una llamada de prueba. Agregar un proveedor es agregar una entrada.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

TIEMPO_LIMITE = 12.0


@dataclass
class Proveedor:
    id: str
    nombre: str
    usos: str
    var_entorno: str | None = None
    patron: str | None = None
    formato: str = ""
    requiere_clave: bool = True
    _ping: Callable[[str | None], tuple[bool, str]] | None = None

    # --- clave -------------------------------------------------------------
    def clave(self) -> str | None:
        if not self.var_entorno:
            return None
        valor = os.environ.get(self.var_entorno, "").strip()
        return valor or None

    def configurado(self) -> bool:
        return (not self.requiere_clave) or self.clave() is not None

    def formato_plausible(self) -> tuple[bool, str]:
        clave = self.clave()
        if clave is None:
            return (not self.requiere_clave, "sin clave")
        if not self.patron:
            return True, f"{len(clave)} caracteres"
        if re.fullmatch(self.patron, clave):
            return True, f"formato ok, {len(clave)} caracteres"
        return False, f"no coincide con el formato esperado ({self.formato})"

    # --- llamada de prueba -------------------------------------------------
    def ping(self) -> tuple[bool, str]:
        if self._ping is None:
            return True, "sin prueba definida"
        try:
            return self._ping(self.clave())
        except Exception as exc:  # noqa: BLE001 - doctor reporta, no explota
            return False, f"{type(exc).__name__}: {exc}"


def _cliente():
    import httpx

    return httpx.Client(timeout=TIEMPO_LIMITE, follow_redirects=True)


def _ping_youtube(clave: str | None) -> tuple[bool, str]:
    with _cliente() as c:
        r = c.get(
            "https://www.googleapis.com/youtube/v3/i18nLanguages",
            params={"part": "snippet", "key": clave or ""},
        )
    if r.status_code == 200:
        return True, "YouTube Data API v3 responde"
    if r.status_code == 403:
        return False, "403: clave sin permiso o API v3 no habilitada en el proyecto"
    if r.status_code == 400:
        return False, "400: clave invalida"
    return False, f"HTTP {r.status_code}"


def _ping_anthropic(clave: str | None) -> tuple[bool, str]:
    with _cliente() as c:
        r = c.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": clave or "", "anthropic-version": "2023-06-01"},
            params={"limit": 1},
        )
    if r.status_code == 200:
        return True, "listado de modelos ok (no consume tokens)"
    if r.status_code in (401, 403):
        return False, f"{r.status_code}: clave rechazada"
    return False, f"HTTP {r.status_code}"


def _ping_openai(clave: str | None) -> tuple[bool, str]:
    with _cliente() as c:
        r = c.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {clave or ''}"},
        )
    if r.status_code == 200:
        return True, "listado de modelos ok (no consume tokens)"
    if r.status_code in (401, 403):
        return False, f"{r.status_code}: clave rechazada"
    return False, f"HTTP {r.status_code}"


def _ping_openverse(_: str | None) -> tuple[bool, str]:
    with _cliente() as c:
        r = c.get("https://api.openverse.org/v1/images/",
                  params={"q": "sky", "page_size": 1})
    return (r.status_code == 200), f"HTTP {r.status_code}"


def _ping_commons(_: str | None) -> tuple[bool, str]:
    with _cliente() as c:
        r = c.get("https://commons.wikimedia.org/w/api.php",
                  params={"action": "query", "meta": "siteinfo", "format": "json"},
                  # Wikimedia exige un User-Agent descriptivo con forma de
                  # contacto; sin el responde 403.
                  headers={"User-Agent": "thumbforge/0.1 (https://github.com/MayliCortez/ProyectosPython)"})
    return (r.status_code == 200), f"HTTP {r.status_code}"


PROVEEDORES: list[Proveedor] = [
    Proveedor(
        id="youtube",
        nombre="YouTube Data API v3",
        usos="M1 recolector",
        var_entorno="YOUTUBE_API_KEY",
        patron=r"AIza[0-9A-Za-z_\-]{35}",
        formato="39 caracteres, empieza con AIza",
        _ping=_ping_youtube,
    ),
    Proveedor(
        id="anthropic",
        nombre="Anthropic",
        usos="M2 vision, M4 brief",
        var_entorno="ANTHROPIC_API_KEY",
        patron=r"sk-ant-[A-Za-z0-9_\-]{20,}",
        formato="empieza con sk-ant-",
        _ping=_ping_anthropic,
    ),
    Proveedor(
        id="openai",
        nombre="OpenAI",
        usos="M2 vision, M4 brief, M5 generacion",
        var_entorno="OPENAI_API_KEY",
        patron=r"sk-[A-Za-z0-9_\-]{20,}",
        formato="empieza con sk-",
        _ping=_ping_openai,
    ),
    Proveedor(
        id="openverse",
        nombre="Openverse",
        usos="M5 archivo con licencia abierta",
        requiere_clave=False,
        _ping=_ping_openverse,
    ),
    Proveedor(
        id="commons",
        nombre="Wikimedia Commons",
        usos="M5 archivo con licencia verificable",
        requiere_clave=False,
        _ping=_ping_commons,
    ),
]


def por_id(pid: str) -> Proveedor:
    for p in PROVEEDORES:
        if p.id == pid:
            return p
    raise KeyError(f"proveedor desconocido: {pid}")


def proveedor_llm() -> Proveedor:
    """El que el operador eligio en TF_PROVEEDOR_LLM, con respaldo."""
    preferido = os.environ.get("TF_PROVEEDOR_LLM", "anthropic").strip().lower()
    try:
        p = por_id(preferido)
        if p.configurado():
            return p
    except KeyError:
        pass
    for pid in ("anthropic", "openai"):
        p = por_id(pid)
        if p.configurado():
            return p
    return por_id(preferido if preferido in ("anthropic", "openai") else "anthropic")
