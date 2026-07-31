"""M4 - brief: guion -> tres conceptos de miniatura.

Este modulo no sabe de que trata el canal. Todo lo que le da personalidad al
brief -que se puede generar, que categoria esta vetada, cuantas palabras entran
en el copy- sale de perfil.yaml a traves de `politicas.politica_para_prompt`.
Si aca aparece una categoria concreta escrita a mano, el diseno esta mal.

Tres cosas que este modulo se toma en serio, porque son criterios de
aceptacion del proyecto y no adornos:

1. La politica del perfil es una restriccion dura. Un concepto que la viola no
   se entrega con una advertencia: se rechaza, el error vuelve al modelo como
   feedback y se pide de nuevo. Con el tope agotado se falla, nunca se entrega.
   Las violaciones DIFERIDAS son otra cosa: no rechazan nada, viajan como
   pendientes para que M5 las resuelva antes de componer.

2. Los tres conceptos difieren en estrategia, no en estetica. Repintar la misma
   idea con otra paleta no es una variante: es la misma apuesta tres veces, y
   el test A/B no puede aprender nada de eso. Se verifica aca, no aguas abajo,
   porque aguas abajo ya se pagaron las imagenes.

3. Cada regla que el brief dice haber aplicado tiene que existir. Un modelo que
   cita 'R9' cuando solo hay siete reglas rompe la trazabilidad en silencio, y
   el silencio es lo peor que puede pasarle a una cadena de decisiones.
"""

from __future__ import annotations

import itertools
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

from .. import esquemas, llm, politicas
from ..cache import Cache, huella
from ..errores import ErrorPolitica
from ..perfiles import Perfil, normalizar
from ..rutas import dir_salida

# --- constantes --------------------------------------------------------------
CANTIDAD_CONCEPTOS = 3
MAX_INTENTOS = 3
ESPACIO_CACHE = "brief"

# Cambiar el prompt cambia la respuesta: la version entra en la clave de cache
# para que un cambio de prompt no siga sirviendo briefs viejos.
VERSION_BRIEF = "1"

# Dos conceptos que comparten esta fraccion de su formulacion son el mismo
# concepto con otras palabras. Medido sobre estrategia + hipotesis + copy +
# categoria + descripcion de la base visual.
UMBRAL_SIMILITUD = 0.60

# Limite de guion que se manda al modelo, en caracteres. Se puede subir por
# entorno cuando el episodio lo justifica.
LIMITE_GUION = int(os.environ.get("TF_BRIEF_LIMITE_GUION") or 12000)
# Del recorte, cuanto se reserva para el arranque. El resto va al cierre.
PROPORCION_CABEZA = 0.6

MARCA_RECORTE = "[...tramo intermedio del guion omitido por longitud: {n} caracteres...]"


class ErrorBrief(ErrorPolitica):
    """M4 agoto los intentos sin conseguir un juego de conceptos aceptable.

    Hereda de ErrorPolitica para que la CLI lo trate como lo que es en el caso
    mas comun -el modelo insiste en violar el perfil- y expone ademas los
    rechazos completos, que son lo que el operador necesita leer.
    """

    def __init__(self, mensaje: str, violaciones=None, rechazos=None):
        super().__init__(mensaje, violaciones)
        self.rechazos = list(rechazos or [])


# --- reglas de M3 -------------------------------------------------------------
@dataclass
class Regla:
    """Una regla identificada del corpus. `id` es lo que el brief cita."""

    id: str
    texto: str = ""
    activa: bool = True


# Identificador al principio de la linea, tolerante con el formato que use M3:
# encabezado, item de lista, cita, fila de tabla, con o sin negritas.
_RE_REGLA = re.compile(r"^[\s>#*\-+|]*\**\s*(R\d+)\b\**\s*[:.)\]\-–—|]*\s*(.*)$",
                       re.IGNORECASE)
_RE_CITA_REGLA = re.compile(r"R\d+", re.IGNORECASE)
_RE_INACTIVA = re.compile(
    r"\b(inactiva|inactivo|desactivada|desactivado|descartada|descartado|"
    r"obsoleta|obsoleto|retirada|retirado)\b")


def _limpiar_linea(texto: str) -> str:
    """Saca decoracion de Markdown sin comerse la puntuacion del enunciado."""
    texto = re.sub(r"\*\*|__|`", "", texto).strip()
    # Los separadores solo se sacan del principio: un punto final es del texto.
    return texto.lstrip("|-–—:. \t").rstrip("| \t").strip()


def _texto_de_fila(linea: str) -> str:
    """Enunciado de una fila de tabla: la primera celda no vacia tras el id."""
    celdas = [_limpiar_linea(c) for c in linea.strip().strip("|").split("|")]
    return next((c for c in celdas[1:] if c), "")


def _orden_regla(regla: Regla) -> tuple:
    digitos = regla.id[1:]
    return (int(digitos) if digitos.isdigit() else 10**9, regla.id)


def leer_reglas_markdown(ruta: Path | None) -> list[Regla]:
    """Lector tolerante de corpus/reglas.md.

    Provisional a proposito: M3 va a exponer su propio lector. Cuando exista,
    se reemplaza `LECTOR_REGLAS` (una sola linea, mas abajo) y este parser se
    borra sin tocar nada mas del modulo.
    """
    if ruta is None or not Path(ruta).is_file():
        return []
    try:
        lineas = Path(ruta).read_text("utf-8").splitlines()
    except OSError:
        return []

    encontradas: dict[str, Regla] = {}
    for i, linea in enumerate(lineas):
        m = _RE_REGLA.match(linea)
        if not m:
            continue
        rid = m.group(1).upper()
        if linea.lstrip().startswith("|"):
            texto = _texto_de_fila(linea)
        else:
            texto = _limpiar_linea(m.group(2))
        if not texto:
            # Formato de encabezado: el identificador arriba, el imperativo
            # en la linea siguiente.
            for siguiente in lineas[i + 1: i + 4]:
                if _RE_REGLA.match(siguiente):
                    break
                candidato = _limpiar_linea(siguiente)
                if candidato:
                    texto = candidato
                    break
        activa = not _RE_INACTIVA.search(normalizar(linea))
        encontradas.setdefault(rid, Regla(id=rid, texto=texto, activa=activa))
    return sorted(encontradas.values(), key=_orden_regla)


def _lector_por_defecto(perfil: Perfil) -> list[Regla]:
    return leer_reglas_markdown(perfil.archivo_reglas)


# PUNTO UNICO DE REEMPLAZO: cuando M3 publique su lector, asignarlo aca.
LECTOR_REGLAS: Callable[[Perfil], list[Regla]] = _lector_por_defecto


def reglas_del_perfil(perfil: Perfil) -> list[Regla]:
    return _normalizar_reglas(LECTOR_REGLAS(perfil))


def _normalizar_reglas(crudas: Iterable[Any] | None) -> list[Regla]:
    """Acepta Regla, dict o texto suelto: M3 todavia no fijo su tipo."""
    salida: list[Regla] = []
    for cruda in crudas or []:
        if isinstance(cruda, Regla):
            salida.append(cruda)
        elif isinstance(cruda, dict):
            rid = str(cruda.get("id") or cruda.get("identificador") or "").strip().upper()
            if rid:
                salida.append(Regla(id=rid,
                                    texto=str(cruda.get("texto") or cruda.get("regla") or ""),
                                    activa=bool(cruda.get("activa", True))))
        elif isinstance(cruda, str):
            m = _RE_CITA_REGLA.search(cruda)
            if m:
                salida.append(Regla(id=m.group().upper(),
                                    texto=_limpiar_linea(cruda[m.end():])))
    return salida


def _reglas_activas(reglas: list[Regla]) -> list[Regla]:
    return [r for r in reglas if r.activa]


# --- guion --------------------------------------------------------------------
@dataclass
class Guion:
    """El guion ya preparado para el prompt."""

    cuerpo: str
    titulo: str | None = None
    caracteres_originales: int = 0
    recortado: bool = False
    aviso: str = ""


_RE_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_RE_TITULO_MD = re.compile(r"^\s{0,3}#\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _corte_en_parrafo(texto: str, desde_el_final: bool) -> str:
    """Recorta hasta el limite de parrafo mas cercano, para no cortar frases."""
    if desde_el_final:
        pos = texto.find("\n\n")
        return texto[pos + 2:] if 0 <= pos <= len(texto) // 3 else texto
    pos = texto.rfind("\n\n")
    return texto[:pos] if pos >= len(texto) * 2 // 3 else texto


def preparar_guion(texto: str, titulo: str | None = None,
                   limite: int = LIMITE_GUION) -> Guion:
    """Extrae titulo y cuerpo de un guion en Markdown.

    Sobre los guiones largos: truncar en silencio es la peor opcion, porque el
    brief sale peor y nadie se entera. Se conserva el arranque -donde esta el
    gancho- y el cierre -donde esta la consecuencia-, que es de donde salen los
    dos polos del eje tension/consecuencia, y se omite el desarrollo del medio
    con una marca visible. El recorte queda registrado como aviso en el
    resultado, asi el operador sabe que el brief se armo con material parcial.
    """
    crudo = texto or ""
    originales = len(crudo)
    del_frontmatter: str | None = None

    m = _RE_FRONTMATTER.match(crudo)
    if m:
        try:
            datos = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            datos = None
        if isinstance(datos, dict):
            for clave in ("titulo", "title", "titulo_video"):
                if datos.get(clave):
                    del_frontmatter = str(datos[clave]).strip()
                    break
        crudo = crudo[m.end():]

    cuerpo = crudo
    titulo_final = (titulo or "").strip() or del_frontmatter

    encabezado = _RE_TITULO_MD.search(cuerpo)
    if encabezado:
        if not titulo_final:
            titulo_final = encabezado.group(1).strip()
        # El titulo no se repite dentro del cuerpo: ya viaja en su propio campo
        # y el control `no_duplicar_titulo` lo necesita limpio.
        cuerpo = cuerpo[:encabezado.start()] + cuerpo[encabezado.end():]

    cuerpo = re.sub(r"\n{3,}", "\n\n", cuerpo).strip()

    if len(cuerpo) <= limite:
        return Guion(cuerpo=cuerpo, titulo=titulo_final or None,
                     caracteres_originales=originales)

    n_cabeza = int(limite * PROPORCION_CABEZA)
    n_cola = limite - n_cabeza
    cabeza = _corte_en_parrafo(cuerpo[:n_cabeza], desde_el_final=False)
    cola = _corte_en_parrafo(cuerpo[-n_cola:], desde_el_final=True)
    omitidos = len(cuerpo) - len(cabeza) - len(cola)
    recortado = f"{cabeza}\n\n{MARCA_RECORTE.format(n=omitidos)}\n\n{cola}"

    aviso = (
        f"El guion tiene {len(cuerpo)} caracteres y el limite de M4 es {limite}. "
        f"Se enviaron los primeros {len(cabeza)} y los ultimos {len(cola)}; se "
        f"omitieron {omitidos} caracteres del desarrollo, marcados en el prompt. "
        f"Si el nucleo del episodio esta en el medio, pasa un resumen como guion "
        f"o subi TF_BRIEF_LIMITE_GUION."
    )
    return Guion(cuerpo=recortado, titulo=titulo_final or None,
                 caracteres_originales=originales, recortado=True, aviso=aviso)


def cargar_guion(ruta: Path | str, limite: int = LIMITE_GUION) -> Guion:
    """Lee un guion Markdown del disco. Lo usa la CLI."""
    p = Path(ruta)
    return preparar_guion(p.read_text("utf-8"), limite=limite)


# --- prompt -------------------------------------------------------------------
PROMPT_SISTEMA = """\
Sos director de arte de miniaturas para video. Trabajas para un canal concreto y
todo lo que sabes de ese canal esta en el bloque POLITICA DEL PERFIL de abajo.
No supongas nada que no este escrito ahi.

Tu tarea: leer un guion y proponer exactamente {cantidad} conceptos de miniatura.

REGLA 1 - La politica del perfil es una restriccion dura, no una sugerencia.
Un concepto que la incumple se rechaza entero y vuelve a vos con el error. Antes
de entregar, revisa cada concepto contra cada linea de la politica. 'origen' y
'categoria' son el vocabulario con el que el perfil concede y niega permisos:
elegilos con precision y no inventes una categoria vaga para esquivar una
prohibicion, porque eso es incumplir igual. Si la politica prohibe generar algo,
no se genera: se busca material de archivo o se cambia el concepto entero.

REGLA 2 - Los {cantidad} conceptos difieren en ESTRATEGIA, no en estetica.
Otro color, otro encuadre u otra tipografia no son una variante: son la misma
apuesta repintada. Cada concepto toma un eje distinto de esta lista y lo declara
en el campo 'eje':
{ejes}
Los {cantidad} ejes tienen que ser distintos entre si. Si dos conceptos se
pueden defender con el mismo argumento, uno de los dos sobra: cambiaselo.

REGLA 3 - Trazabilidad. Si te paso reglas identificadas, cada concepto cita en
'reglas_aplicadas' los identificadores que efectivamente aplicaste, y solo los
que figuren en la lista que te doy. Inventar un identificador rompe la
trazabilidad y el concepto se rechaza. Si no te paso ninguna regla, dejalo vacio.

REGLA 4 - Escribi en {idioma}. 'hipotesis' dice en una frase por que esa
miniatura ganaria el click: es lo que despues se mide, no un resumen del guion.
'estrategia' nombra la apuesta en pocas palabras. 'id' es un identificador corto
en minusculas con guiones.

POLITICA DEL PERFIL (volcada de perfil.yaml; cada linea es vinculante)
---------------------------------------------------------------------
{politica}
---------------------------------------------------------------------
"""


def prompt_sistema(perfil: Perfil) -> str:
    """El prompt de sistema con la politica del perfil ya inyectada.

    La politica no se escribe aca: se pide a `politicas.politica_para_prompt`,
    que la vuelca del YAML. Una clave nueva en el perfil llega al prompt sin
    tocar Python.
    """
    ejes = "\n".join(f"  - {e}" for e in esquemas.EJES_ESTRATEGIA)
    return PROMPT_SISTEMA.format(
        cantidad=CANTIDAD_CONCEPTOS,
        ejes=ejes,
        idioma=perfil.idioma,
        politica=politicas.politica_para_prompt(perfil),
    )


def _texto_reglas(reglas: list[Regla]) -> str:
    activas = _reglas_activas(reglas)
    if not activas:
        return ""
    lineas = [f"  {r.id}. {r.texto}" if r.texto else f"  {r.id}." for r in activas]
    return ("REGLAS DEL CANAL (identificadas por M3 sobre el corpus). Citalas por "
            "su identificador en 'reglas_aplicadas'; no existe ningun otro "
            "identificador:\n" + "\n".join(lineas))


def prompt_usuario(guion: Guion, reglas: list[Regla], titulo: str | None,
                   feedback: str = "") -> str:
    partes: list[str] = []
    if titulo:
        partes.append(f"TITULO DEL VIDEO\n{titulo}")
    texto_reglas = _texto_reglas(reglas)
    if texto_reglas:
        partes.append(texto_reglas)
    if guion.recortado:
        partes.append("AVISO SOBRE EL GUION\n" + guion.aviso)
    partes.append("GUION\n<<<\n" + guion.cuerpo + "\n>>>")
    partes.append(
        f"Devolve {CANTIDAD_CONCEPTOS} conceptos que cumplan la politica del "
        f"perfil y que ataquen {CANTIDAD_CONCEPTOS} ejes distintos.")
    if feedback:
        partes.append(feedback)
    return "\n\n".join(partes)


# --- esquema de la respuesta ---------------------------------------------------
def _esquema_elemento(origenes: list[str]) -> dict:
    return llm.esquema_json({
        "origen": {"type": "string", "enum": origenes,
                   "description": "De donde sale la imagen. El perfil solo admite estos valores."},
        "categoria": {"type": "string",
                      "description": "Que es lo representado, en el vocabulario del perfil. "
                                     "Es la clave con la que la politica concede o niega permiso."},
        "descripcion": {"type": "string", "description": "Que se ve, en una frase."},
        "fuente_sugerida": {"type": "string",
                            "description": "Donde conseguirlo. Cadena vacia si no aplica."},
        "licencia": {"type": "string",
                     "description": "Licencia del material si ya se conoce. Cadena vacia si no."},
    })


def esquema_respuesta(perfil: Perfil) -> dict:
    """JSON Schema de la respuesta, derivado del perfil.

    Los origenes admitidos y el campo obligatorio del copy salen del YAML: el
    esquema ya impide, a nivel de formato, lo que la politica prohibiria despues.
    Igual se valida la respuesta: un esquema no es una garantia de conducta.
    """
    origenes = [str(o) for o in (perfil.get("politica_base_visual.orden_preferencia") or [])]
    if not origenes:
        origenes = list(esquemas.ORIGENES_VISUALES)

    props_copy: dict[str, Any] = {
        "texto": {"type": "string", "description": "El texto que va sobre la miniatura."},
        "entidades": {
            "type": "array",
            "description": "Lo que el copy nombra, clasificado. El perfil puede prohibir tipos.",
            "items": llm.esquema_json({"tipo": {"type": "string"},
                                       "valor": {"type": "string"}}),
        },
    }
    campo_obligatorio = perfil.get("copy.debe_incluir")
    if campo_obligatorio:
        props_copy[str(campo_obligatorio)] = {
            "type": "string",
            "description": f"El perfil exige '{campo_obligatorio}' y que su valor "
                           f"aparezca literalmente dentro de 'texto'.",
        }

    concepto = llm.esquema_json({
        "id": {"type": "string"},
        "estrategia": {"type": "string"},
        "eje": {"type": "string", "enum": list(esquemas.EJES_ESTRATEGIA)},
        "hipotesis": {"type": "string"},
        "copy": llm.esquema_json(props_copy),
        "base_visual": _esquema_elemento(origenes),
        "capas": {"type": "array", "items": _esquema_elemento(origenes)},
        "reglas_aplicadas": {"type": "array", "items": {"type": "string"}},
    })

    return {
        "type": "object",
        "properties": {
            "conceptos": {"type": "array", "items": concepto,
                          "minItems": CANTIDAD_CONCEPTOS, "maxItems": CANTIDAD_CONCEPTOS},
        },
        "required": ["conceptos"],
        "additionalProperties": False,
    }


# --- control de distancia estrategica ------------------------------------------
_VACIAS = {
    "a", "al", "ante", "con", "contra", "de", "del", "desde", "el", "en", "entre",
    "es", "esa", "ese", "esta", "este", "la", "las", "lo", "los", "mas", "no",
    "para", "por", "que", "se", "sin", "sobre", "su", "sus", "un", "una", "uno",
    "y", "o", "u", "e", "como", "cuando", "donde", "muy", "ya",
}


def _tokens(texto: str) -> set[str]:
    return {p for p in re.split(r"[^a-z0-9]+", normalizar(texto))
            if len(p) > 2 and p not in _VACIAS}


def _huella_textual(concepto: dict) -> set[str]:
    base = concepto.get("base_visual") or {}
    copia = concepto.get("copy") or {}
    partes = [
        str(concepto.get("estrategia") or ""),
        str(concepto.get("hipotesis") or ""),
        str(copia.get("texto") or ""),
        str(base.get("categoria") or ""),
        str(base.get("descripcion") or ""),
    ]
    return _tokens(" ".join(partes))


def _similitud(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _id_concepto(concepto: dict, indice: int) -> str:
    return str(concepto.get("id") or f"concepto-{indice + 1}")


# --- rechazos y resultado ------------------------------------------------------
@dataclass
class Rechazo:
    """Un concepto que no entro, y el motivo exacto. Se le muestra al usuario:
    el rechazo explicito es parte del producto, no ruido."""

    intento: int
    concepto_id: str
    tipo: str            # politica | estrategia | trazabilidad | forma
    codigo: str
    detalle: str

    def texto(self) -> str:
        return f"intento {self.intento} - {self.concepto_id} [{self.tipo}/{self.codigo}]\n    {self.detalle}"


@dataclass
class ResultadoBrief:
    perfil: str
    titulo: str | None
    conceptos: list[dict]
    veredictos: list[politicas.Veredicto]
    pendientes: list[politicas.Violacion]      # diferidas: las resuelve M5
    intentos: int
    rechazos: list[Rechazo] = field(default_factory=list)
    reglas: list[Regla] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    desde_cache: bool = False
    archivo: Path | None = None

    @property
    def ok(self) -> bool:
        return all(v.ok for v in self.veredictos) and len(self.conceptos) == CANTIDAD_CONCEPTOS

    def a_json(self) -> dict:
        return {
            "perfil": self.perfil,
            "titulo": self.titulo,
            "intentos": self.intentos,
            "desde_cache": self.desde_cache,
            "conceptos": self.conceptos,
            "reglas_disponibles": [asdict(r) for r in self.reglas],
            "pendientes": [
                {"concepto": v.concepto_id,
                 "violaciones": [{"codigo": x.codigo, "mensaje": x.mensaje,
                                  "regla": x.regla, "razon": x.razon}
                                 for x in v.diferidas]}
                for v in self.veredictos if v.diferidas
            ],
            "rechazos": [asdict(r) for r in self.rechazos],
            "avisos": self.avisos,
        }

    def informe(self) -> str:
        lineas = [f"Perfil: {self.perfil}"]
        if self.titulo:
            lineas.append(f"Titulo: {self.titulo}")
        lineas.append(f"Intentos: {self.intentos}"
                      + (" (desde cache: sin llamadas de red)" if self.desde_cache else ""))
        for aviso in self.avisos:
            lineas.append(f"Aviso: {aviso}")

        lineas.append("")
        for concepto, veredicto in zip(self.conceptos, self.veredictos):
            lineas.append(f"{concepto.get('id')}  [{concepto.get('eje')}]")
            lineas.append(f"  estrategia: {concepto.get('estrategia')}")
            lineas.append(f"  copy:       \"{(concepto.get('copy') or {}).get('texto', '')}\"")
            lineas.append(f"  hipotesis:  {concepto.get('hipotesis')}")
            citadas = ", ".join(concepto.get("reglas_aplicadas") or []) or "(ninguna)"
            lineas.append(f"  reglas:     {citadas}")
            for pendiente in veredicto.diferidas:
                lineas.append(f"  PENDIENTE para M5: {pendiente.texto()}")
            lineas.append("")

        if self.rechazos:
            lineas.append(f"Conceptos rechazados por el camino ({len(self.rechazos)}):")
            lineas += [f"  - {r.texto()}" for r in self.rechazos]
            lineas.append("")
        if self.archivo:
            lineas.append(f"Brief escrito en {self.archivo}")
        return "\n".join(lineas).rstrip()


# --- validacion de un juego de conceptos ---------------------------------------
def _rechazos_de_forma(conceptos: Any, intento: int) -> list[Rechazo]:
    if not isinstance(conceptos, list) or len(conceptos) != CANTIDAD_CONCEPTOS:
        cuantos = len(conceptos) if isinstance(conceptos, list) else 0
        return [Rechazo(intento, "(juego completo)", "forma", "cantidad",
                        f"Se esperaban {CANTIDAD_CONCEPTOS} conceptos y llegaron {cuantos}.")]
    malos = [i for i, c in enumerate(conceptos) if not isinstance(c, dict)]
    if malos:
        return [Rechazo(intento, f"concepto-{i + 1}", "forma", "no_es_objeto",
                        "El concepto no es un objeto JSON.") for i in malos]
    return []


def _rechazos_de_politica(veredictos: list[politicas.Veredicto],
                          intento: int) -> list[Rechazo]:
    """Solo las duras rechazan. Las diferidas viajan como pendientes a M5."""
    rechazos = []
    for veredicto in veredictos:
        for violacion in veredicto.duras:
            rechazos.append(Rechazo(intento, veredicto.concepto_id, "politica",
                                    violacion.codigo, violacion.texto()))
    return rechazos


def _rechazos_de_estrategia(conceptos: list[dict], intento: int) -> list[Rechazo]:
    """Tres conceptos que apuestan a lo mismo son un solo concepto.

    M6 tambien mide distancia entre variantes, pero esa comprobacion llega
    despues de generar y componer las imagenes: cara y tarde. Se ataja aca.
    """
    rechazos: list[Rechazo] = []
    validos = {normalizar(e): e for e in esquemas.EJES_ESTRATEGIA}
    ejes = [normalizar(str(c.get("eje") or "")) for c in conceptos]

    vistos: dict[str, str] = {}
    for i, (concepto, eje) in enumerate(zip(conceptos, ejes)):
        cid = _id_concepto(concepto, i)
        if eje not in validos:
            rechazos.append(Rechazo(
                intento, cid, "estrategia", "eje_invalido",
                f"Declara el eje '{concepto.get('eje')}', que no existe. Los ejes "
                f"validos son: {', '.join(esquemas.EJES_ESTRATEGIA)}."))
            continue
        if eje in vistos:
            rechazos.append(Rechazo(
                intento, cid, "estrategia", "eje_repetido",
                f"Toma el eje '{validos[eje]}', que ya usa '{vistos[eje]}'. Los "
                f"{CANTIDAD_CONCEPTOS} conceptos tienen que atacar ejes distintos: "
                f"reemplazalo por uno que apueste a otra cosa, no por el mismo con "
                f"otra estetica."))
        else:
            vistos[eje] = cid

    for (i, a), (j, b) in itertools.combinations(list(enumerate(conceptos)), 2):
        similitud = _similitud(_huella_textual(a), _huella_textual(b))
        if similitud >= UMBRAL_SIMILITUD:
            rechazos.append(Rechazo(
                intento, _id_concepto(b, j), "estrategia", "encuadre_repetido",
                f"Comparte el {similitud:.0%} de su formulacion con "
                f"'{_id_concepto(a, i)}': misma apuesta con otras palabras. "
                f"Cambia el sujeto, el momento o la funcion del texto, no el estilo."))
    return rechazos


def _rechazos_de_trazabilidad(conceptos: list[dict], reglas: list[Regla],
                              intento: int) -> list[Rechazo]:
    """Cada identificador citado tiene que existir en reglas.md."""
    activas = _reglas_activas(reglas)
    if not activas:
        return []          # sin reglas no hay nada que rastrear
    disponibles = {r.id for r in activas}
    rechazos: list[Rechazo] = []

    for i, concepto in enumerate(conceptos):
        cid = _id_concepto(concepto, i)
        citadas: list[str] = []
        inventadas: list[str] = []
        for cruda in concepto.get("reglas_aplicadas") or []:
            m = _RE_CITA_REGLA.search(str(cruda))
            identificador = m.group().upper() if m else str(cruda).strip()
            citadas.append(identificador)
            if identificador not in disponibles:
                inventadas.append(identificador)
        if inventadas:
            rechazos.append(Rechazo(
                intento, cid, "trazabilidad", "regla_inexistente",
                f"Cita {', '.join(sorted(set(inventadas)))}, que no existe en "
                f"corpus/reglas.md. Identificadores disponibles: "
                f"{', '.join(sorted(disponibles, key=lambda x: (len(x), x)))}."))
        elif not citadas:
            rechazos.append(Rechazo(
                intento, cid, "trazabilidad", "sin_trazabilidad",
                f"No cita ninguna regla. Hay {len(disponibles)} reglas activas y "
                f"cada concepto tiene que declarar cuales aplico."))
    return rechazos


def _feedback(rechazos: list[Rechazo], perfil: Perfil, intento: int) -> str:
    """El rechazo vuelve al modelo tal cual, con el motivo del YAML incluido."""
    por_tipo: dict[str, list[Rechazo]] = {}
    for r in rechazos:
        por_tipo.setdefault(r.tipo, []).append(r)

    encabezados = {
        "forma": "PROBLEMAS DE FORMA",
        "politica": (f"VIOLACIONES DE LA POLITICA DEL PERFIL '{perfil.slug}' "
                     f"(son restricciones duras, no sugerencias)"),
        "estrategia": "PROBLEMAS DE ESTRATEGIA (los conceptos no son variantes reales)",
        "trazabilidad": "PROBLEMAS DE TRAZABILIDAD DE REGLAS",
    }

    lineas = [f"[Intento {intento} RECHAZADO. Corregi todo lo que sigue y devolve de "
              f"nuevo los {CANTIDAD_CONCEPTOS} conceptos completos.]"]
    for tipo in ("forma", "politica", "estrategia", "trazabilidad"):
        if tipo not in por_tipo:
            continue
        lineas.append("")
        lineas.append(encabezados[tipo])
        for r in por_tipo[tipo]:
            lineas.append(f"  - concepto '{r.concepto_id}': {r.detalle}")
    lineas.append("")
    lineas.append("No negocies con estas restricciones: reformula el concepto. Los que "
                  "no aparecen en la lista estaban bien, conservalos como estan.")
    return "\n".join(lineas)


# --- el generador --------------------------------------------------------------
def _generador_por_defecto(cache: Cache | None) -> Callable[[llm.Peticion], llm.RespuestaLLM]:
    def generar(peticion: llm.Peticion) -> llm.RespuestaLLM:
        # Se resuelve `llm.pedir_json` en el momento de la llamada para que un
        # monkeypatch del modulo lo intercepte.
        return llm.pedir_json(peticion, cache=cache, espacio_cache=ESPACIO_CACHE)

    return generar


def _clave_cache(perfil: Perfil, guion: Guion, titulo: str | None,
                 reglas: list[Regla]) -> str:
    """Deriva del guion, del perfil completo y de las reglas activas.

    Si cambia cualquiera de los tres, cambia el brief, y la cache tiene que
    fallar. Si no cambia ninguno, la segunda corrida no toca la red.
    """
    return huella(
        VERSION_BRIEF,
        perfil.slug,
        perfil.datos,
        guion.cuerpo,
        titulo or "",
        [(r.id, r.texto) for r in _reglas_activas(reglas)],
        list(esquemas.EJES_ESTRATEGIA),
        CANTIDAD_CONCEPTOS,
    )


def ruta_salida(perfil: Perfil, clave: str, nombre_guion: str | None = None) -> Path:
    etiqueta = re.sub(r"[^a-z0-9_-]+", "-", normalizar(nombre_guion or "")).strip("-")
    return dir_salida() / f"brief_{perfil.slug}_{etiqueta or clave[:8]}.json"


def escribir_brief(resultado: ResultadoBrief, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado.a_json(), ensure_ascii=False, indent=2),
                       "utf-8")
    return destino


# --- entrada publica -----------------------------------------------------------
def generar_conceptos(
    perfil: Perfil,
    guion_texto: str,
    cache: Cache | None = None,
    titulo: str | None = None,
    reglas: list[Any] | None = None,
    *,
    max_intentos: int = MAX_INTENTOS,
    generador: Callable[[llm.Peticion], llm.RespuestaLLM] | None = None,
    nombre_guion: str | None = None,
    escribir: bool = True,
) -> ResultadoBrief:
    """Guion -> tres conceptos que cumplen la politica del perfil.

    `reglas` en None se lee del corpus del perfil; una lista explicita la pisa.
    `generador` en None usa el LLM configurado; se inyecta para probar sin red.

    Lanza ErrorBrief si el modelo agota los intentos sin producir un juego
    aceptable. Nunca devuelve un concepto con violaciones duras.
    """
    guion = preparar_guion(guion_texto, titulo=titulo)
    titulo_final = titulo or guion.titulo

    avisos: list[str] = []
    if reglas is None:
        reglas_norm = reglas_del_perfil(perfil)
        if not reglas_norm:
            avisos.append(
                f"No hay reglas identificadas en {perfil.archivo_reglas}: el brief se "
                f"armo solo con la politica del perfil y el campo 'reglas_aplicadas' "
                f"queda vacio. Corre 'thumbforge reglas --perfil {perfil.slug}' cuando "
                f"el corpus este anotado.")
    else:
        reglas_norm = _normalizar_reglas(reglas)
    if guion.recortado:
        avisos.append(guion.aviso)

    clave = _clave_cache(perfil, guion, titulo_final, reglas_norm)
    destino = ruta_salida(perfil, clave, nombre_guion)

    # 1. Cache del brief entero. La clave sale del guion, del perfil y de las
    #    reglas activas: la segunda corrida del mismo guion no llama a nadie.
    if cache is not None:
        guardado = cache.leer_json(ESPACIO_CACHE, clave)
        if guardado is not None:
            cache.stats.aciertos += 1
            resultado = _desde_cache(guardado, perfil, titulo_final, avisos)
            if escribir:
                resultado.archivo = escribir_brief(resultado, destino)
            return resultado
        cache.stats.fallos += 1

    generar = generador or _generador_por_defecto(cache)
    sistema = prompt_sistema(perfil)
    esquema = esquema_respuesta(perfil)

    historial: list[Rechazo] = []
    feedback = ""
    ultimos_veredictos: list[politicas.Veredicto] = []

    for intento in range(1, max_intentos + 1):
        peticion = llm.Peticion(
            sistema=sistema,
            usuario=prompt_usuario(guion, reglas_norm, titulo_final, feedback),
            esquema=esquema,
            max_tokens=4096,
            esfuerzo="high",
        )
        respuesta = generar(peticion)
        datos = respuesta.datos if isinstance(respuesta.datos, dict) else {}
        conceptos = datos.get("conceptos")

        rechazos = _rechazos_de_forma(conceptos, intento)
        if not rechazos:
            veredictos = politicas.evaluar_conceptos(conceptos, perfil, titulo=titulo_final)
            ultimos_veredictos = veredictos
            rechazos += _rechazos_de_politica(veredictos, intento)
            rechazos += _rechazos_de_estrategia(conceptos, intento)
            rechazos += _rechazos_de_trazabilidad(conceptos, reglas_norm, intento)

            if not rechazos:
                pendientes = [v for ver in veredictos for v in ver.diferidas]
                resultado = ResultadoBrief(
                    perfil=perfil.slug, titulo=titulo_final, conceptos=conceptos,
                    veredictos=veredictos, pendientes=pendientes, intentos=intento,
                    rechazos=historial, reglas=reglas_norm, avisos=avisos)
                if cache is not None:
                    cache.guardar_json(ESPACIO_CACHE, clave, _a_cache(resultado))
                if escribir:
                    resultado.archivo = escribir_brief(resultado, destino)
                return resultado

        historial += rechazos
        feedback = _feedback(rechazos, perfil, intento)

    raise ErrorBrief(
        _mensaje_agotado(perfil, max_intentos, historial),
        violaciones=[v for ver in ultimos_veredictos for v in ver.duras],
        rechazos=historial,
    )


def _mensaje_agotado(perfil: Perfil, max_intentos: int,
                     historial: list[Rechazo]) -> str:
    ultimo = max((r.intento for r in historial), default=max_intentos)
    finales = [r for r in historial if r.intento == ultimo]
    lineas = [
        f"M4 agoto los {max_intentos} intentos y ningun juego de conceptos paso los "
        f"controles del perfil '{perfil.slug}' ({perfil.nombre}).",
        "Lo que quedo sin resolver en el ultimo intento:",
    ]
    lineas += [f"  - {r.texto()}" for r in finales]
    lineas.append(
        f"Estas restricciones las impone el perfil '{perfil.slug}', declaradas en "
        f"{perfil.raiz / 'perfil.yaml'}. No se entrega un concepto que las viole: "
        f"si la restriccion ya no aplica, se cambia el YAML, no el resultado.")
    return "\n".join(lineas)


# --- serializacion para la cache ------------------------------------------------
def _a_cache(resultado: ResultadoBrief) -> dict:
    return {
        "conceptos": resultado.conceptos,
        "intentos": resultado.intentos,
        "rechazos": [asdict(r) for r in resultado.rechazos],
        "reglas": [asdict(r) for r in resultado.reglas],
    }


def _desde_cache(guardado: dict, perfil: Perfil, titulo: str | None,
                 avisos: list[str]) -> ResultadoBrief:
    """Reconstruye el resultado. Los veredictos se recalculan en vez de
    guardarse: evaluar es gratis y deterministico, y asi un cambio del perfil
    no queda tapado por una cache vieja."""
    conceptos = guardado.get("conceptos") or []
    veredictos = politicas.evaluar_conceptos(conceptos, perfil, titulo=titulo)
    return ResultadoBrief(
        perfil=perfil.slug,
        titulo=titulo,
        conceptos=conceptos,
        veredictos=veredictos,
        pendientes=[v for ver in veredictos for v in ver.diferidas],
        intentos=int(guardado.get("intentos") or 0),
        rechazos=[Rechazo(**r) for r in guardado.get("rechazos") or []],
        reglas=[Regla(**r) for r in guardado.get("reglas") or []],
        avisos=avisos,
        desde_cache=True,
    )
