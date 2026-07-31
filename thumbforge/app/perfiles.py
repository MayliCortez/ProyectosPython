"""Carga y validacion de perfiles de nicho.

Un perfil es una carpeta. Agregar un canal nuevo es crear una carpeta; el
codigo de este archivo no conoce ningun nicho en particular y no debe
aprender ninguno.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import esquemas
from .errores import ErrorPerfil
from .rutas import dir_perfiles

ARCHIVO_PERFIL = "perfil.yaml"
ARCHIVO_SKIN = "skin.yaml"

# Claves obligatorias de perfil.yaml, en notacion punteada.
CLAVES_PERFIL = (
    "nombre",
    "idioma",
    "politica_base_visual.orden_preferencia",
    "personas_reales.aparecen",
    "copy.max_palabras",
)

CLAVES_SKIN = (
    "lienzo.ancho",
    "lienzo.alto",
    "paleta.texto",
    "tipografia.titular.archivo",
)


def _obtener(datos: dict, ruta: str, defecto: Any = None) -> Any:
    actual: Any = datos
    for parte in ruta.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return defecto
        actual = actual[parte]
    return actual


def normalizar(texto: str) -> str:
    """Minusculas sin acentos. Se usa para comparar copys y alias."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


@dataclass
class Problema:
    """Hallazgo de validacion. `nivel` es OK, AVISO o ERROR."""

    nivel: str
    detalle: str


@dataclass
class Perfil:
    slug: str
    raiz: Path
    datos: dict
    skin: dict
    _fuentes: dict[str, Path] = field(default_factory=dict, repr=False)

    # --- accesos declarativos ---------------------------------------------
    def get(self, ruta: str, defecto: Any = None) -> Any:
        return _obtener(self.datos, ruta, defecto)

    def get_skin(self, ruta: str, defecto: Any = None) -> Any:
        return _obtener(self.skin, ruta, defecto)

    @property
    def nombre(self) -> str:
        return self.datos.get("nombre", self.slug)

    @property
    def idioma(self) -> str:
        return self.datos.get("idioma", "es")

    @property
    def alias(self) -> list[str]:
        valor = self.datos.get("alias") or []
        return [str(a) for a in valor]

    # --- rutas -------------------------------------------------------------
    def ruta(self, relativa: str) -> Path:
        """Resuelve una ruta declarada en el YAML contra la raiz del perfil.

        Las fuentes y los assets se referencian SIEMPRE por ruta de archivo.
        Un nombre de familia tipografica que existe en Windows no existe en
        Debian slim y Pillow no avisa: cae a la default y arruina el render.
        """
        p = Path(relativa)
        if p.is_absolute():
            return p
        return (self.raiz / p).resolve()

    @property
    def dir_corpus(self) -> Path:
        return self.raiz / "corpus"

    @property
    def archivo_videos(self) -> Path:
        return self.dir_corpus / "videos.jsonl"

    @property
    def archivo_anotaciones(self) -> Path:
        return self.dir_corpus / "anotaciones.jsonl"

    @property
    def archivo_reglas(self) -> Path:
        return self.dir_corpus / "reglas.md"

    @property
    def archivo_ctr(self) -> Path:
        return self.dir_corpus / "mi_ctr.csv"

    # --- tipografia --------------------------------------------------------
    def fuentes_declaradas(self) -> dict[str, Path]:
        """{rol: ruta absoluta} para cada tipografia del skin."""
        salida: dict[str, Path] = {}
        tipografia = self.skin.get("tipografia") or {}
        for rol, cfg in tipografia.items():
            if isinstance(cfg, dict) and cfg.get("archivo"):
                salida[rol] = self.ruta(cfg["archivo"])
        return salida

    def fuente(self, rol: str = "titular") -> Path:
        fuentes = self.fuentes_declaradas()
        if rol not in fuentes:
            raise ErrorPerfil(
                f"El perfil '{self.slug}' no declara la tipografia '{rol}' en {ARCHIVO_SKIN}."
            )
        ruta = fuentes[rol]
        if not ruta.is_file():
            raise ErrorPerfil(
                f"La tipografia '{rol}' del perfil '{self.slug}' apunta a {ruta}, que no existe. "
                f"Las fuentes viajan dentro del perfil: copiala a {self.raiz / 'fonts'}."
            )
        return ruta

    def assets_declarados(self) -> dict[str, Path]:
        """{descripcion: ruta} de todo lo que el skin referencia como archivo."""
        encontrados: dict[str, Path] = {}

        def recorrer(nodo: Any, camino: str) -> None:
            if isinstance(nodo, dict):
                for clave, valor in nodo.items():
                    if clave == "archivo" and isinstance(valor, str):
                        encontrados[camino or clave] = self.ruta(valor)
                    else:
                        recorrer(valor, f"{camino}.{clave}" if camino else clave)
            elif isinstance(nodo, list):
                for i, valor in enumerate(nodo):
                    recorrer(valor, f"{camino}[{i}]")

        recorrer(self.skin, "")
        # Las tipografias ya se reportan aparte.
        return {k: v for k, v in encontrados.items() if not k.startswith("tipografia")}

    # --- esquema de anotacion ---------------------------------------------
    def campos_extra_anotacion(self) -> list[str]:
        return [str(c) for c in (self.datos.get("campos_extra_anotacion") or [])]

    def esquema_anotacion(self) -> dict[str, tuple]:
        return esquemas.esquema_anotacion(self.campos_extra_anotacion())

    # --- validacion --------------------------------------------------------
    def validar(self) -> list[Problema]:
        problemas: list[Problema] = []

        for clave in CLAVES_PERFIL:
            if self.get(clave) is None:
                problemas.append(Problema("ERROR", f"{ARCHIVO_PERFIL}: falta '{clave}'"))
        for clave in CLAVES_SKIN:
            if self.get_skin(clave) is None:
                problemas.append(Problema("ERROR", f"{ARCHIVO_SKIN}: falta '{clave}'"))

        orden = self.get("politica_base_visual.orden_preferencia") or []
        desconocidos = [o for o in orden if o not in esquemas.ORIGENES_VISUALES]
        if desconocidos:
            problemas.append(Problema(
                "ERROR",
                f"orden_preferencia tiene origenes desconocidos {desconocidos}; "
                f"validos: {list(esquemas.ORIGENES_VISUALES)}",
            ))

        permitidas = set(self.get("politica_base_visual.generacion_ia_permitida_para") or [])
        prohibidas = set(self.get("politica_base_visual.generacion_ia_prohibida_para") or [])
        solapadas = permitidas & prohibidas
        if solapadas:
            problemas.append(Problema(
                "AVISO",
                f"categorias en permitida y prohibida a la vez {sorted(solapadas)}; "
                "gana la prohibicion",
            ))

        ancho = self.get_skin("lienzo.ancho") or 0
        alto = self.get_skin("lienzo.alto") or 0
        if ancho < 1280 or alto < 720:
            problemas.append(Problema(
                "ERROR", f"lienzo {ancho}x{alto} es menor que el minimo 1280x720"))

        # Fuentes: existen y Pillow puede abrirlas.
        fuentes = self.fuentes_declaradas()
        if not fuentes:
            problemas.append(Problema("ERROR", f"{ARCHIVO_SKIN}: no declara ninguna tipografia"))
        for rol, ruta in fuentes.items():
            if not ruta.is_file():
                problemas.append(Problema("ERROR", f"tipografia '{rol}' no existe: {ruta}"))
                continue
            try:
                from PIL import ImageFont

                ImageFont.truetype(str(ruta), 32)
            except Exception as exc:  # noqa: BLE001 - se reporta, no se propaga
                problemas.append(Problema("ERROR", f"tipografia '{rol}' no carga en Pillow: {exc}"))

        for descripcion, ruta in self.assets_declarados().items():
            if not ruta.is_file():
                problemas.append(Problema("AVISO", f"asset '{descripcion}' no existe: {ruta}"))

        if not self.dir_corpus.is_dir():
            problemas.append(Problema("AVISO", "no existe corpus/; M1 lo crea al recolectar"))

        # Coherencia de politica de personas reales.
        if self.get("personas_reales.aparecen") and self.get("personas_reales.generar_con_ia"):
            if "persona_real" in prohibidas:
                problemas.append(Problema(
                    "ERROR",
                    "personas_reales.generar_con_ia es true pero 'persona_real' esta en "
                    "generacion_ia_prohibida_para; el perfil se contradice",
                ))

        if not problemas:
            problemas.append(Problema("OK", "perfil valido"))
        return problemas


# --- descubrimiento ---------------------------------------------------------
def _leer_yaml(ruta: Path) -> dict:
    try:
        with ruta.open("r", encoding="utf-8") as fh:
            datos = yaml.safe_load(fh)
    except FileNotFoundError:
        raise ErrorPerfil(f"No existe {ruta}")
    except yaml.YAMLError as exc:
        raise ErrorPerfil(f"{ruta} no parsea como YAML: {exc}")
    if datos is None:
        datos = {}
    if not isinstance(datos, dict):
        raise ErrorPerfil(f"{ruta} deberia ser un mapeo, es {type(datos).__name__}")
    return datos


def cargar_perfil_en(raiz: Path) -> Perfil:
    raiz = Path(raiz).resolve()
    datos = _leer_yaml(raiz / ARCHIVO_PERFIL)
    ruta_skin = raiz / ARCHIVO_SKIN
    skin = _leer_yaml(ruta_skin) if ruta_skin.exists() else {}
    return Perfil(slug=raiz.name, raiz=raiz, datos=datos, skin=skin)


def listar_perfiles(base: Path | None = None) -> list[Path]:
    base = base or dir_perfiles()
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if (p / ARCHIVO_PERFIL).is_file())


def cargar_perfil(referencia: str, base: Path | None = None) -> Perfil:
    """Resuelve por slug exacto, alias declarado o prefijo unico."""
    base = base or dir_perfiles()
    candidatos = listar_perfiles(base)
    if not candidatos:
        raise ErrorPerfil(
            f"No hay ningun perfil en {base}. Cada perfil es una carpeta con {ARCHIVO_PERFIL}."
        )

    ref = normalizar(referencia)

    for ruta in candidatos:
        if normalizar(ruta.name) == ref:
            return cargar_perfil_en(ruta)

    perfiles = [cargar_perfil_en(r) for r in candidatos]

    for perfil in perfiles:
        if any(normalizar(a) == ref for a in perfil.alias):
            return perfil

    prefijos = [p for p in perfiles if normalizar(p.slug).startswith(ref)]
    if len(prefijos) == 1:
        return prefijos[0]
    if len(prefijos) > 1:
        raise ErrorPerfil(
            f"'{referencia}' es ambiguo: coincide con {', '.join(p.slug for p in prefijos)}"
        )

    disponibles = ", ".join(
        f"{p.slug}" + (f" (alias: {', '.join(p.alias)})" if p.alias else "") for p in perfiles
    )
    raise ErrorPerfil(f"No existe el perfil '{referencia}'. Disponibles: {disponibles}")


def cargar_todos(base: Path | None = None) -> list[Perfil]:
    return [cargar_perfil_en(r) for r in listar_perfiles(base)]
