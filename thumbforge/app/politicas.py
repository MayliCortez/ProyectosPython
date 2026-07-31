"""Motor de politicas.

Este archivo evalua conceptos contra el perfil activo. No sabe que es un
P-51, ni que es un caso policial, ni que es un telefono. Todo lo que decide
sale de perfil.yaml.

Regla de diseno: si aparece un `if nicho == ...` aca, el diseno esta mal y
lo que se estaba por escribir va al YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .perfiles import Perfil, normalizar

SEV_DURA = "dura"          # rechaza el concepto
SEV_DIFERIDA = "diferida"  # no rechaza: obliga a resolver algo en M5


@dataclass
class Violacion:
    codigo: str
    mensaje: str
    regla: str                  # clave de perfil.yaml que se violo
    severidad: str = SEV_DURA
    razon: str = ""             # el 'por que' declarado en el perfil

    def texto(self) -> str:
        base = f"[{self.codigo}] {self.mensaje} (regla: {self.regla})"
        return f"{base}\n    Motivo declarado en el perfil: {self.razon}" if self.razon else base


@dataclass
class Veredicto:
    concepto_id: str
    violaciones: list[Violacion] = field(default_factory=list)

    @property
    def duras(self) -> list[Violacion]:
        return [v for v in self.violaciones if v.severidad == SEV_DURA]

    @property
    def diferidas(self) -> list[Violacion]:
        return [v for v in self.violaciones if v.severidad == SEV_DIFERIDA]

    @property
    def ok(self) -> bool:
        return not self.duras

    def informe(self) -> str:
        if not self.violaciones:
            return f"{self.concepto_id}: aprobado"
        lineas = [f"{self.concepto_id}: {'aprobado con pendientes' if self.ok else 'RECHAZADO'}"]
        lineas += [f"  - {v.texto()}" for v in self.violaciones]
        return "\n".join(lineas)


# --- controles de copy con nombre -------------------------------------------
# El perfil los invoca por su etiqueta humana en `copy.prohibido`. Cualquier
# entrada que no coincida con una etiqueta se trata como subcadena literal.
_RE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿]"
)
_RE_CLICKBAIT_NUM = re.compile(
    r"(^\s*(top\s*)?\d+\b)|(\b\d+\s+(cosas|razones|secretos|datos|errores|formas|motivos|claves)\b)"
)


def _ck_mayusculas_linea(texto: str) -> bool:
    letras = [c for c in texto if c.isalpha()]
    return bool(letras) and texto.upper() == texto


def _ck_emojis(texto: str) -> bool:
    return bool(_RE_EMOJI.search(texto))


def _ck_clickbait_numerico(texto: str) -> bool:
    return bool(_RE_CLICKBAIT_NUM.search(normalizar(texto)))


def _ck_exclamacion(texto: str) -> bool:
    return "!" in texto or "¡" in texto


def _ck_interrogacion(texto: str) -> bool:
    return "?" in texto or "¿" in texto


CONTROLES_COPY: dict[str, Callable[[str], bool]] = {
    "mayusculas en toda la linea": _ck_mayusculas_linea,
    "mayusculas": _ck_mayusculas_linea,
    "emojis": _ck_emojis,
    "emoji": _ck_emojis,
    "clickbait numerico": _ck_clickbait_numerico,
    "signos de exclamacion": _ck_exclamacion,
    "signos de interrogacion": _ck_interrogacion,
    "!": _ck_exclamacion,
    "?": _ck_interrogacion,
}


# --- utilidades sobre el concepto -------------------------------------------
def elementos_visuales(concepto: dict) -> list[dict]:
    """base_visual + capas, en una sola lista uniforme."""
    elementos = []
    base = concepto.get("base_visual")
    if isinstance(base, dict):
        elementos.append({"_rol": "base_visual", **base})
    for i, capa in enumerate(concepto.get("capas") or []):
        if isinstance(capa, dict):
            elementos.append({"_rol": f"capas[{i}]", **capa})
    return elementos


def _palabras(texto: str) -> list[str]:
    return [p for p in re.split(r"\s+", texto.strip()) if p]


def _cats_persona(perfil: Perfil) -> set[str]:
    """Categorias que el perfil considera 'persona real'."""
    declaradas = perfil.get("personas_reales.categorias")
    if declaradas:
        return {normalizar(str(c)) for c in declaradas}
    return {"persona_real"}


# --- evaluacion --------------------------------------------------------------
def evaluar_concepto(concepto: dict, perfil: Perfil, titulo: str | None = None) -> Veredicto:
    """Contrasta un concepto de M4 con las politicas duras del perfil."""
    ver = Veredicto(concepto_id=str(concepto.get("id") or "sin-id"))
    v = ver.violaciones

    razon_visual = perfil.get("politica_base_visual.razon", "")
    razon_personas = perfil.get("personas_reales.razon", "")
    # Motivo especifico para el veto de categorias; si el perfil no lo declara,
    # se reusa el motivo general de la politica visual.
    razon_cats = perfil.get("politica_base_visual.razon_categorias_prohibidas") or razon_visual

    orden = [normalizar(o) for o in (perfil.get("politica_base_visual.orden_preferencia") or [])]
    # Una lista presente pero vacia significa "nada es generable"; una clave
    # ausente significa "no hay lista blanca, solo manda la prohibicion".
    _permitidas = perfil.get("politica_base_visual.generacion_ia_permitida_para")
    lista_blanca = isinstance(_permitidas, list)
    permitidas = {normalizar(c) for c in (_permitidas or [])}
    prohibidas = {normalizar(c) for c in (perfil.get("politica_base_visual.generacion_ia_prohibida_para") or [])}
    cat_vetadas = {normalizar(c) for c in (perfil.get("politica_base_visual.categorias_prohibidas") or [])}
    cats_persona = _cats_persona(perfil)
    permite_ia_personas = bool(perfil.get("personas_reales.generar_con_ia"))
    exige_licencia = bool(perfil.get("personas_reales.solo_licencia_verificada"))

    # 1. Origenes visuales
    for elem in elementos_visuales(concepto):
        rol = elem.get("_rol", "?")
        origen = normalizar(str(elem.get("origen") or ""))
        categoria = normalizar(str(elem.get("categoria") or ""))

        if not origen:
            v.append(Violacion("origen_ausente", f"{rol} no declara 'origen'.",
                               "politica_base_visual.orden_preferencia"))
            continue

        if orden and origen not in orden:
            v.append(Violacion(
                "origen_no_permitido",
                f"{rol} usa origen '{origen}', que el perfil no admite. "
                f"Admitidos, en orden de preferencia: {', '.join(orden)}.",
                "politica_base_visual.orden_preferencia", razon=razon_visual))

        if categoria in cat_vetadas:
            v.append(Violacion(
                "categoria_vetada",
                f"{rol} usa la categoria '{categoria}', prohibida en cualquier origen para este perfil.",
                "politica_base_visual.categorias_prohibidas", razon=razon_cats))

        if origen == "generada":
            if categoria in prohibidas:
                v.append(Violacion(
                    "ia_prohibida_para_categoria",
                    f"{rol} propone generar con IA la categoria '{categoria}', "
                    f"expresamente prohibida por el perfil.",
                    "politica_base_visual.generacion_ia_prohibida_para", razon=razon_visual))
            elif lista_blanca and categoria not in permitidas:
                v.append(Violacion(
                    "ia_fuera_de_lista",
                    f"{rol} propone generar con IA la categoria '{categoria}', que no esta en la "
                    f"lista de lo permitido: {', '.join(sorted(permitidas)) or '(vacia)'}.",
                    "politica_base_visual.generacion_ia_permitida_para", razon=razon_visual))

            if categoria in cats_persona and not permite_ia_personas:
                v.append(Violacion(
                    "ia_sobre_persona_real",
                    f"{rol} propone generar con IA a una persona real ('{categoria}'). "
                    f"El perfil lo bloquea sin excepcion.",
                    "personas_reales.generar_con_ia", razon=razon_personas))

        elif categoria in cats_persona and exige_licencia:
            licencia = str(elem.get("licencia") or "").strip()
            if not licencia:
                v.append(Violacion(
                    "licencia_pendiente",
                    f"{rol} muestra una persona real y el perfil solo acepta material con "
                    f"licencia verificada. M5 debe resolver la fuente y anotar la licencia "
                    f"antes de componer.",
                    "personas_reales.solo_licencia_verificada",
                    severidad=SEV_DIFERIDA, razon=razon_personas))

    # 2. Copy
    copy_cfg = perfil.get("copy") or {}
    copy_concepto = concepto.get("copy") or {}
    texto = str(copy_concepto.get("texto") or "")

    max_palabras = copy_cfg.get("max_palabras")
    if isinstance(max_palabras, int):
        n = len(_palabras(texto))
        if n > max_palabras:
            v.append(Violacion(
                "copy_largo",
                f"El copy tiene {n} palabras y el maximo del perfil es {max_palabras}: \"{texto}\".",
                "copy.max_palabras"))

    debe_incluir = copy_cfg.get("debe_incluir")
    if debe_incluir:
        valor = str(copy_concepto.get(debe_incluir) or "").strip()
        if not valor:
            v.append(Violacion(
                "copy_sin_campo_obligatorio",
                f"El copy no declara '{debe_incluir}', que este perfil exige.",
                "copy.debe_incluir"))
        elif normalizar(valor) not in normalizar(texto):
            v.append(Violacion(
                "copy_no_contiene_campo",
                f"El copy declara {debe_incluir}='{valor}' pero ese valor no aparece en "
                f"el texto \"{texto}\".",
                "copy.debe_incluir"))

    for prohibido in copy_cfg.get("prohibido") or []:
        etiqueta = str(prohibido)
        clave = normalizar(etiqueta)
        control = CONTROLES_COPY.get(clave)
        if control is not None:
            disparo = control(texto)
        else:
            disparo = clave in normalizar(texto)
        if disparo:
            v.append(Violacion(
                "copy_prohibido",
                f"El copy incurre en '{etiqueta}': \"{texto}\".",
                "copy.prohibido"))

    for tipo in copy_cfg.get("prohibir_entidades") or []:
        objetivo = normalizar(str(tipo))
        for entidad in copy_concepto.get("entidades") or []:
            if not isinstance(entidad, dict):
                continue
            if normalizar(str(entidad.get("tipo") or "")) == objetivo:
                v.append(Violacion(
                    "entidad_prohibida",
                    f"El copy nombra una entidad de tipo '{tipo}' "
                    f"('{entidad.get('valor')}'), prohibida por el perfil.",
                    "copy.prohibir_entidades",
                    razon=copy_cfg.get("razon_entidades", "")))

    if copy_cfg.get("no_duplicar_titulo") and titulo:
        if normalizar(texto) and normalizar(texto) in normalizar(titulo):
            v.append(Violacion(
                "copy_duplica_titulo",
                f"El copy \"{texto}\" repite el titulo del video; la miniatura tiene que "
                f"sumar informacion, no repetirla.",
                "copy.no_duplicar_titulo"))

    return ver


def evaluar_conceptos(conceptos: list[dict], perfil: Perfil,
                      titulo: str | None = None) -> list[Veredicto]:
    return [evaluar_concepto(c, perfil, titulo) for c in conceptos]


# --- serializacion de la politica para el prompt ------------------------------
def politica_para_prompt(perfil: Perfil) -> str:
    """Vuelca las politicas del perfil como texto para el LLM.

    Se genera desde el YAML: cuando alguien agrega una clave nueva al perfil,
    el prompt la refleja sin tocar Python.
    """
    lineas: list[str] = []

    def escalar(valor: Any) -> str:
        # El volcado va al prompt del LLM: nada de True/False de Python.
        if isinstance(valor, bool):
            return "si" if valor else "no"
        return str(valor)

    def volcar(nodo: Any, sangria: int = 0) -> None:
        pad = "  " * sangria
        if isinstance(nodo, dict):
            for clave, valor in nodo.items():
                if isinstance(valor, list) and not valor:
                    lineas.append(f"{pad}- {clave}: (lista vacia: no se admite ningun valor)")
                elif isinstance(valor, (dict, list)):
                    lineas.append(f"{pad}- {clave}:")
                    volcar(valor, sangria + 1)
                else:
                    lineas.append(f"{pad}- {clave}: {escalar(valor)}")
        elif isinstance(nodo, list):
            for valor in nodo:
                if isinstance(valor, (dict, list)):
                    volcar(valor, sangria + 1)
                else:
                    lineas.append(f"{pad}- {escalar(valor)}")
        else:
            lineas.append(f"{pad}- {escalar(nodo)}")

    for seccion in ("politica_base_visual", "personas_reales", "copy"):
        datos = perfil.get(seccion)
        if datos:
            lineas.append(f"{seccion}:")
            volcar(datos, 1)
    return "\n".join(lineas)
