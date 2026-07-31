"""M3 - patrones: cruza metadata con anotaciones y destila reglas.

Entrada: `corpus/videos.jsonl` (M1) + `corpus/anotaciones.jsonl` (M2), y si
existe, `corpus/mi_ctr.csv` (export manual del Modo Avanzado de YouTube
Studio). Salida: `corpus/reglas.md`, que consume M4.

Tres decisiones de diseno que no se negocian:

1. Se comparan MEDIANAS, nunca promedios. Un solo video viral mueve un
   promedio varios cientos por ciento y ninguna mediana.
2. Toda regla publica su `n`. Por debajo de `N_MINIMA` el corte se marca
   `[muestra insuficiente]` y no genera regla: con 5 videos por lado, la
   diferencia de medianas es ruido con formato de conclusion.
3. El modulo no sabe nada del nicho. Los cortes salen del esquema de
   anotacion y de los datos; los tramos de los campos numericos son
   cuantiles empiricos del propio corpus, no umbrales escritos a mano.

El `outlier_score` es rendimiento relativo al propio canal (views sobre la
mediana del canal en la ventana). NO es CTR. El CTR ajeno no existe en
ninguna API: el unico CTR real es el propio, y por eso su informe pesa mas.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errores import ErrorThumbforge
from ..esquemas import CAMPOS_ANOTACION_SISTEMA
from ..perfiles import Perfil, normalizar

# --- parametros del analisis -------------------------------------------------
# Minimo de videos por lado del corte. Por debajo no se emite regla.
N_MINIMA = 8
# Tope duro de reglas activas. Una lista de 30 reglas no la aplica nadie.
MAX_REGLAS = 7
# Diferencia relativa de medianas a partir de la cual la regla se publica.
UMBRAL_EFECTO = 0.15
# Tramos en los que se parte un campo numerico (cuantiles empiricos).
TRAMOS = 3
# Cardinalidad maxima de un campo categorico para considerarlo agrupable.
MAX_CATEGORIAS = 12
# Cuantos cortes descartados se listan por campo, para que el informe no
# se vuelva un volcado.
MAX_DESCARTES_POR_CAMPO = 5

METRICA_CORPUS = "outlier_score"
METRICA_CTR = "ctr"
FUENTE_CORPUS = "corpus_ajeno"
FUENTE_CTR = "ctr_propio"

PREFIJO_ID = {FUENTE_CORPUS: "R", FUENTE_CTR: "C"}

MARCA_INSUFICIENTE = "[muestra insuficiente]"
MARCA_DATOS = "<!-- thumbforge:datos -->"

# Nombres alternativos de la mediana del canal en videos.jsonl. M1 puede
# escribir cualquiera de estos; si no viene `outlier_score` hecho, se
# reconstruye con views / mediana.
CLAVES_MEDIANA_CANAL = ("mediana_canal", "mediana_del_canal", "canal_mediana", "mediana")


class ErrorCorpus(ErrorThumbforge):
    """El corpus no existe, o un archivo de entrada no se puede interpretar."""


# --- utilidades de lectura tolerante -----------------------------------------
def _a_numero(valor: Any) -> float | None:
    """Numero desde lo que venga. None si no hay forma de leerlo.

    Tolera lo que escupe una planilla: '4,5', '4.5%', '1.234,5', espacios
    finos. Un bool no es una medida, se rechaza.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if not isinstance(valor, str):
        return None
    texto = valor.strip().replace("\u00a0", "").replace("%", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        # El separador que aparece ultimo es el decimal.
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _a_bool(valor: Any) -> bool | None:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    if isinstance(valor, str):
        texto = normalizar(valor).strip()
        if texto in ("si", "true", "1", "verdadero", "yes", "y"):
            return True
        if texto in ("no", "false", "0", "falso", "n"):
            return False
    return None


def _fmt(x: float) -> str:
    """Numero para leer, no para operar."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}"


def _fmt_efecto(efecto: float) -> str:
    return f"{efecto * 100:+.1f}%"


def leer_jsonl(ruta: Path, contadores: dict[str, int], sufijo: str) -> list[dict]:
    """JSONL tolerante: una linea rota no voltea la corrida, se cuenta.

    M1 y M2 escriben en modo append y pueden dejar una linea a medias si el
    proceso se corta. Preferimos analizar 199 registros a fallar por uno.
    """
    registros: list[dict] = []
    if not ruta.is_file():
        contadores[f"{sufijo}_archivo_ausente"] = 1
        return registros
    with ruta.open("r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            contadores[f"{sufijo}_lineas"] = contadores.get(f"{sufijo}_lineas", 0) + 1
            try:
                dato = json.loads(linea)
            except json.JSONDecodeError:
                contadores[f"{sufijo}_json_invalido"] = contadores.get(f"{sufijo}_json_invalido", 0) + 1
                continue
            if not isinstance(dato, dict):
                contadores[f"{sufijo}_no_es_objeto"] = contadores.get(f"{sufijo}_no_es_objeto", 0) + 1
                continue
            if dato.get("error"):
                contadores[f"{sufijo}_con_error"] = contadores.get(f"{sufijo}_con_error", 0) + 1
                continue
            if not str(dato.get("video_id") or "").strip():
                contadores[f"{sufijo}_sin_video_id"] = contadores.get(f"{sufijo}_sin_video_id", 0) + 1
                continue
            registros.append(dato)
    return registros


def _outlier_score(video: dict) -> float | None:
    """`outlier_score` tal cual, o reconstruido con views / mediana del canal."""
    directo = _a_numero(video.get("outlier_score"))
    if directo is not None:
        return directo
    views = _a_numero(video.get("views"))
    for clave in CLAVES_MEDIANA_CANAL:
        mediana = _a_numero(video.get(clave))
        if views is not None and mediana:
            return views / mediana
    return None


# --- lectura del CSV de CTR propio -------------------------------------------
# YouTube Studio no exporta un formato unico: cambia el idioma de la interfaz,
# el separador segun la region y mete BOM. Todo se detecta, nada se asume.
_PISTAS_CTR = ("clic", "ctr")
_PISTAS_CTR_FUERTES = ("impres",)
_CABECERAS_ID = (
    "contenido", "content", "video", "video id", "video_id",
    "id del video", "id de video", "id",
)
_RE_ID_VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass
class LecturaCtr:
    """Resultado de interpretar mi_ctr.csv, con lo que se detecto y por que."""

    valores: dict[str, float]
    columna_id: str
    columna_ctr: str
    separador: str
    filas_leidas: int
    filas_salteadas: int


def _decodificar(ruta: Path) -> str:
    crudo = ruta.read_bytes()
    for codec in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return crudo.decode(codec)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", errors="replace")


def _detectar_separador(cabecera: str) -> str:
    """El que mas veces aparece en la primera linea. Sin Sniffer: con una
    sola columna el Sniffer levanta excepcion y aca eso no es un error."""
    candidatos = [";", ",", "\t", "|"]
    conteos = {sep: cabecera.count(sep) for sep in candidatos}
    mejor = max(conteos, key=lambda s: conteos[s])
    return mejor if conteos[mejor] else ","


def _columna_ctr(cabeceras: list[str]) -> str | None:
    normalizadas = {h: normalizar(h) for h in cabeceras}
    fuertes = [h for h, n in normalizadas.items()
               if any(p in n for p in _PISTAS_CTR) and any(f in n for f in _PISTAS_CTR_FUERTES)]
    if fuertes:
        return fuertes[0]
    debiles = [h for h, n in normalizadas.items() if any(p in n for p in _PISTAS_CTR)]
    return debiles[0] if debiles else None


def _columna_id(cabeceras: list[str], filas: list[dict]) -> str | None:
    normalizadas = {h: normalizar(h).strip() for h in cabeceras}
    for h, n in normalizadas.items():
        if n in _CABECERAS_ID:
            return h
    # Sin nombre reconocible: se busca la columna cuyos valores tienen forma
    # de id de YouTube. Es preferible a fallar por como se llamo la columna.
    for h in cabeceras:
        valores = [str(f.get(h) or "").strip() for f in filas]
        validos = [v for v in valores if _RE_ID_VIDEO.match(v)]
        if valores and len(validos) >= max(1, len(valores) // 2):
            return h
    return None


def leer_ctr(ruta: Path) -> LecturaCtr:
    """Interpreta mi_ctr.csv. Si falta una columna, dice cual y como obtenerla.

    Nunca revienta con KeyError: el operador tiene que poder arreglar el
    export sin leer el codigo.
    """
    if not Path(ruta).is_file():
        raise ErrorCorpus(f"No existe {ruta}.")

    texto = _decodificar(Path(ruta))
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        raise ErrorCorpus(f"{ruta} esta vacio: no tiene ni fila de encabezados.")

    separador = _detectar_separador(lineas[0])
    lector = csv.DictReader(lineas, delimiter=separador)
    cabeceras = [h for h in (lector.fieldnames or []) if h is not None]
    if not cabeceras:
        raise ErrorCorpus(f"{ruta} no tiene fila de encabezados legible.")
    filas = [f for f in lector]

    col_ctr = _columna_ctr(cabeceras)
    if col_ctr is None:
        raise ErrorCorpus(
            f"{ruta}: falta la columna de CTR. Se buscaron encabezados que contengan "
            f"'clic', 'click' o 'ctr'; los encabezados presentes son: "
            f"{', '.join(cabeceras)}. Exportalo desde YouTube Studio > Analytics > "
            f"Modo avanzado con la columna 'Porcentaje de clics de las impresiones (%)'."
        )

    col_id = _columna_id(cabeceras, filas)
    if col_id is None:
        raise ErrorCorpus(
            f"{ruta}: falta la columna de id de video. Se buscaron encabezados "
            f"{', '.join(_CABECERAS_ID)} y tambien una columna con ids de 11 caracteres; "
            f"los encabezados presentes son: {', '.join(cabeceras)}. En el export de "
            f"YouTube Studio esa columna se llama 'Contenido'."
        )

    valores: dict[str, float] = {}
    salteadas = 0
    for fila in filas:
        vid = str(fila.get(col_id) or "").strip()
        ctr = _a_numero(fila.get(col_ctr))
        if not vid or ctr is None:
            salteadas += 1
            continue
        valores[vid] = ctr
    return LecturaCtr(
        valores=valores,
        columna_id=col_id,
        columna_ctr=col_ctr,
        separador="TAB" if separador == "\t" else separador,
        filas_leidas=len(filas),
        filas_salteadas=salteadas,
    )


# --- cortes -------------------------------------------------------------------
CORTE_BOOL = "booleano"
CORTE_CATEGORICO = "categorico"
CORTE_TRAMO = "tramo"
CORTE_PERTENENCIA = "pertenencia"


@dataclass
class _Grupo:
    campo: str
    etiqueta: str
    tipo_corte: str
    dentro: list[float]
    fuera: list[float]


def _cortes_cuantiles(valores: list[float], tramos: int = TRAMOS) -> list[float]:
    """Cuantiles empiricos que separan de verdad.

    Se usan cuantiles y no umbrales fijos porque un umbral fijo seria
    conocimiento del nicho cableado en el motor. Ademas los cuantiles dejan
    grupos de tamano parecido, que es lo que da mas chances de superar la
    n minima. Un corte que no separa (todos los valores de un lado) se tira.
    """
    ordenados = sorted(valores)
    if len(ordenados) < 2:
        return []
    minimo, maximo = ordenados[0], ordenados[-1]
    cortes: list[float] = []
    for i in range(1, tramos):
        pos = (len(ordenados) - 1) * i / tramos
        bajo = int(pos)
        alto = min(bajo + 1, len(ordenados) - 1)
        valor = ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (pos - bajo)
        if minimo <= valor < maximo and (not cortes or valor > cortes[-1] + 1e-12):
            cortes.append(valor)
    return cortes


def _etiquetas_tramos(cortes: list[float]) -> list[str]:
    if not cortes:
        return []
    etiquetas = [f"<= {_fmt(cortes[0])}"]
    for anterior, siguiente in zip(cortes, cortes[1:]):
        etiquetas.append(f"{_fmt(anterior)} a {_fmt(siguiente)}")
    etiquetas.append(f"> {_fmt(cortes[-1])}")
    return etiquetas


def _grupos_tramos(campo: str, pares: list[tuple[float, float]]) -> list[_Grupo]:
    cortes = _cortes_cuantiles([v for v, _ in pares])
    etiquetas = _etiquetas_tramos(cortes)
    if not etiquetas:
        return []
    baldes: dict[str, list[float]] = {e: [] for e in etiquetas}
    for valor, y in pares:
        indice = 0
        while indice < len(cortes) and valor > cortes[indice]:
            indice += 1
        baldes[etiquetas[indice]].append(y)
    return _armar_grupos(campo, CORTE_TRAMO, baldes, [y for _, y in pares])


def _grupos_categoricos(campo: str, tipo: str,
                        pares: list[tuple[Any, float]]) -> tuple[list[_Grupo], str]:
    baldes: dict[str, list[float]] = {}
    for valor, y in pares:
        if tipo == "bool":
            booleano = _a_bool(valor)
            if booleano is None:
                continue
            etiqueta = "si" if booleano else "no"
        else:
            etiqueta = str(valor).strip()
            if not etiqueta:
                etiqueta = "(vacio)"
        baldes.setdefault(etiqueta, []).append(y)
    if len(baldes) > MAX_CATEGORIAS:
        return [], (f"campo de alta cardinalidad: {len(baldes)} valores distintos, "
                    f"maximo {MAX_CATEGORIAS}")
    todos = [y for balde in baldes.values() for y in balde]
    tipo_corte = CORTE_BOOL if tipo == "bool" else CORTE_CATEGORICO
    return _armar_grupos(campo, tipo_corte, baldes, todos), ""


def _grupos_pertenencia(campo: str, pares: list[tuple[Any, float]]) -> list[_Grupo]:
    """Para campos lista: cada elemento observado es un corte 'lo contiene o no'."""
    presencias: dict[str, list[float]] = {}
    frecuencia: dict[str, int] = {}
    todos: list[float] = []
    for valor, y in pares:
        if isinstance(valor, str):
            elementos = [valor] if valor.strip() else []
        elif isinstance(valor, (list, tuple, set)):
            elementos = [str(e).strip() for e in valor if str(e).strip()]
        else:
            continue
        todos.append(y)
        for elemento in set(elementos):
            presencias.setdefault(elemento, []).append(y)
            frecuencia[elemento] = frecuencia.get(elemento, 0) + 1

    mas_frecuentes = sorted(frecuencia, key=lambda e: (-frecuencia[e], e))[:MAX_CATEGORIAS]
    grupos: list[_Grupo] = []
    for elemento in mas_frecuentes:
        dentro = presencias[elemento]
        # El resto son las filas del campo que no contienen el elemento.
        fuera = _resta_multiconjunto(todos, dentro)
        grupos.append(_Grupo(campo, f"contiene {elemento}", CORTE_PERTENENCIA, dentro, fuera))
    return grupos


def _resta_multiconjunto(todos: list[float], dentro: list[float]) -> list[float]:
    restantes = list(todos)
    for y in dentro:
        try:
            restantes.remove(y)
        except ValueError:  # pragma: no cover - defensivo
            pass
    return restantes


def _armar_grupos(campo: str, tipo_corte: str, baldes: dict[str, list[float]],
                  todos: list[float]) -> list[_Grupo]:
    grupos: list[_Grupo] = []
    if len(baldes) < 2:
        return grupos
    for etiqueta, dentro in baldes.items():
        fuera = _resta_multiconjunto(todos, dentro)
        grupos.append(_Grupo(campo, etiqueta, tipo_corte, dentro, fuera))
    return grupos


def _grupos_de_campo(campo: str, tipo: str,
                     pares: list[tuple[Any, float]]) -> tuple[list[_Grupo], str]:
    """Todos los cortes candidatos de un campo. El str es el motivo de descarte."""
    if not pares:
        return [], "sin datos"
    if tipo == "list[str]":
        return _grupos_pertenencia(campo, pares), ""
    if tipo in ("int", "float"):
        numericos = [(n, y) for v, y in pares if (n := _a_numero(v)) is not None]
        # Si el campo dice ser numerico pero los datos no lo son, se lo trata
        # como categorico en vez de perderlo.
        if len(numericos) >= 2 * N_MINIMA:
            return _grupos_tramos(campo, numericos), ""
        if len(numericos) >= len(pares) // 2 and numericos:
            return [], f"solo {len(numericos)} valores numericos, hacen falta {2 * N_MINIMA}"
    return _grupos_categoricos(campo, tipo, pares)


# --- reglas -------------------------------------------------------------------
DIR_FAVORECE = "favorece"
DIR_PENALIZA = "penaliza"


@dataclass
class Regla:
    """Una regla activa, con toda su trazabilidad encima.

    `id` es lo que M4 cita en `reglas_aplicadas`; con ese id se llega a una
    linea de reglas.md que tiene el corte, la n de cada lado y las medianas.
    """

    id: str
    texto: str
    campo: str
    grupo: str
    tipo_corte: str
    direccion: str
    n_grupo: int
    n_resto: int
    mediana_grupo: float
    mediana_resto: float
    efecto: float
    metrica: str
    fuente: str
    conflicto_con: str = ""

    @property
    def n_total(self) -> int:
        return self.n_grupo + self.n_resto

    @property
    def corte(self) -> str:
        if self.tipo_corte == CORTE_TRAMO:
            return f"`{self.campo}` en el tramo «{self.grupo}»"
        if self.tipo_corte == CORTE_PERTENENCIA:
            return f"`{self.campo}` {self.grupo}"
        return f"`{self.campo}` = «{self.grupo}»"

    @property
    def pesa_mas(self) -> bool:
        return self.fuente == FUENTE_CTR


def _texto_imperativo(campo: str, grupo: str, tipo_corte: str, direccion: str) -> str:
    """Imperativo, siempre. Una regla que describe no se aplica: se comenta.

    El motor no conoce la semantica del campo, asi que la orden se arma con
    el nombre del campo y el valor del corte. Sin tildes, como todo el repo.
    """
    favorece = direccion == DIR_FAVORECE
    if tipo_corte == CORTE_BOOL:
        if grupo == "si":
            return (f"Inclui `{campo}` en la miniatura." if favorece
                    else f"Evita `{campo}` en la miniatura.")
        return (f"Evita `{campo}` en la miniatura." if favorece
                else f"Inclui `{campo}` en la miniatura.")
    if tipo_corte == CORTE_TRAMO:
        return (f"Mantene `{campo}` en el tramo «{grupo}»." if favorece
                else f"Saca `{campo}` del tramo «{grupo}».")
    if tipo_corte == CORTE_PERTENENCIA:
        elemento = grupo.removeprefix("contiene ").strip()
        return (f"Inclui «{elemento}» en `{campo}`." if favorece
                else f"Evita «{elemento}» en `{campo}`.")
    return (f"Pone `{campo}` en «{grupo}»." if favorece
            else f"Evita `{campo}` = «{grupo}».")


@dataclass
class Descarte:
    """Un corte que se miro y no genero regla. Va al informe: el lector tiene
    que poder ver que se probo y por que no alcanzo."""

    campo: str
    grupo: str
    n_grupo: int
    n_resto: int
    motivo: str
    detalle: str = ""

    @property
    def insuficiente(self) -> bool:
        return self.motivo == "muestra insuficiente"


@dataclass
class _Candidata:
    campo: str
    grupo: str
    tipo_corte: str
    n_grupo: int
    n_resto: int
    mediana_grupo: float
    mediana_resto: float
    efecto: float

    @property
    def direccion(self) -> str:
        return DIR_FAVORECE if self.efecto >= 0 else DIR_PENALIZA


def _analizar_metrica(filas: list[dict], esquema: dict[str, tuple],
                      n_minima: int, umbral: float,
                      max_reglas: int) -> tuple[list[_Candidata], list[_Candidata], list[Descarte]]:
    """Devuelve (publicadas, sobrantes, descartes) para una variable dependiente."""
    descartes: list[Descarte] = []
    mejores: list[_Candidata] = []

    for campo, definicion in esquema.items():
        if campo in CAMPOS_ANOTACION_SISTEMA:
            continue
        tipo = definicion[0] if isinstance(definicion, (tuple, list)) and definicion else "str"
        pares = [(f[campo], f["__y"]) for f in filas if f.get(campo) is not None]
        grupos, motivo_campo = _grupos_de_campo(campo, tipo, pares)
        if motivo_campo:
            descartes.append(Descarte(campo, "(todo el campo)", len(pares), 0,
                                      "campo no agrupable", motivo_campo))
            continue

        candidatas_campo: list[_Candidata] = []
        insuficientes: list[Descarte] = []
        for grupo in grupos:
            n_g, n_r = len(grupo.dentro), len(grupo.fuera)
            if n_g < n_minima or n_r < n_minima:
                insuficientes.append(Descarte(campo, grupo.etiqueta, n_g, n_r,
                                              "muestra insuficiente",
                                              f"hace falta n >= {n_minima} de los dos lados"))
                continue
            med_g = statistics.median(grupo.dentro)
            med_r = statistics.median(grupo.fuera)
            if med_r == 0:
                descartes.append(Descarte(campo, grupo.etiqueta, n_g, n_r,
                                          "mediana de referencia nula",
                                          "no se puede medir un efecto relativo contra 0"))
                continue
            efecto = (med_g - med_r) / abs(med_r)
            candidatas_campo.append(
                _Candidata(campo, grupo.etiqueta, grupo.tipo_corte, n_g, n_r,
                           med_g, med_r, efecto))

        insuficientes.sort(key=lambda d: (-d.n_grupo, d.grupo))
        descartes.extend(insuficientes[:MAX_DESCARTES_POR_CAMPO])

        if not candidatas_campo:
            continue
        # Una sola regla por campo: la de mayor efecto. Los cortes de un mismo
        # campo son la misma informacion contada al reves (si/no) o en tramos
        # contiguos; publicar dos gasta cupo y no agrega senal.
        candidatas_campo.sort(key=lambda c: (-abs(c.efecto), c.grupo))
        mejor = candidatas_campo[0]
        for perdedora in candidatas_campo[1:]:
            descartes.append(Descarte(perdedora.campo, perdedora.grupo,
                                      perdedora.n_grupo, perdedora.n_resto,
                                      "otro corte del mismo campo tiene mas efecto",
                                      f"efecto {_fmt_efecto(perdedora.efecto)}"))
        if abs(mejor.efecto) < umbral:
            descartes.append(Descarte(mejor.campo, mejor.grupo, mejor.n_grupo, mejor.n_resto,
                                      "efecto insuficiente",
                                      f"efecto {_fmt_efecto(mejor.efecto)}, "
                                      f"umbral {_fmt_efecto(umbral)}"))
            continue
        mejores.append(mejor)

    mejores.sort(key=lambda c: (-abs(c.efecto), c.campo, c.grupo))
    return mejores[:max_reglas], mejores[max_reglas:], descartes


def _a_reglas(candidatas: list[_Candidata], metrica: str, fuente: str) -> list[Regla]:
    reglas: list[Regla] = []
    for i, c in enumerate(candidatas, start=1):
        reglas.append(Regla(
            id=f"{PREFIJO_ID[fuente]}{i}",
            texto=_texto_imperativo(c.campo, c.grupo, c.tipo_corte, c.direccion),
            campo=c.campo,
            grupo=c.grupo,
            tipo_corte=c.tipo_corte,
            direccion=c.direccion,
            n_grupo=c.n_grupo,
            n_resto=c.n_resto,
            mediana_grupo=c.mediana_grupo,
            mediana_resto=c.mediana_resto,
            efecto=c.efecto,
            metrica=metrica,
            fuente=fuente,
        ))
    return reglas


# --- informe ------------------------------------------------------------------
@dataclass
class Bloque:
    """Un analisis completo sobre una variable dependiente."""

    metrica: str
    fuente: str
    n_total: int
    reglas: list[Regla] = field(default_factory=list)
    sobrantes: list[_Candidata] = field(default_factory=list)
    descartes: list[Descarte] = field(default_factory=list)
    disponible: bool = True
    motivo_no_disponible: str = ""

    @property
    def suficiente(self) -> bool:
        """Con menos de dos grupos posibles de n minima no hay nada que comparar."""
        return self.n_total >= 2 * N_MINIMA

    @property
    def insuficientes(self) -> list[Descarte]:
        return [d for d in self.descartes if d.insuficiente]


@dataclass
class Conflicto:
    campo: str
    regla_ctr: str
    regla_corpus: str
    detalle: str


@dataclass
class Informe:
    perfil_slug: str
    generado_en: str
    lecturas: dict[str, int] = field(default_factory=dict)
    corpus: Bloque | None = None
    ctr: Bloque | None = None
    conflictos: list[Conflicto] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    ruta_reglas: Path | None = None
    parametros: dict[str, Any] = field(default_factory=dict)
    deteccion_ctr: dict[str, Any] = field(default_factory=dict)

    def reglas_activas(self) -> list[Regla]:
        """CTR propio primero: pesa mas."""
        reglas: list[Regla] = []
        if self.ctr is not None:
            reglas.extend(self.ctr.reglas)
        if self.corpus is not None:
            reglas.extend(self.corpus.reglas)
        return reglas

    def regla(self, identificador: str) -> Regla | None:
        for r in self.reglas_activas():
            if r.id == identificador:
                return r
        return None


def _detectar_conflictos(bloque_ctr: Bloque | None, bloque_corpus: Bloque | None) -> list[Conflicto]:
    """Contradicciones entre el CTR propio y el corpus ajeno.

    Se marcan explicitamente porque la tentacion es promediarlas, y no se
    promedian: cuando chocan, manda el CTR propio.
    """
    if bloque_ctr is None or bloque_corpus is None:
        return []
    conflictos: list[Conflicto] = []
    for rc in bloque_ctr.reglas:
        for rr in bloque_corpus.reglas:
            if rc.campo != rr.campo:
                continue
            if rc.grupo == rr.grupo and rc.direccion != rr.direccion:
                detalle = (f"sobre el mismo corte {rc.corte}, el CTR propio dice "
                           f"'{rc.direccion}' y el corpus ajeno dice '{rr.direccion}'")
            elif rc.grupo != rr.grupo and rc.direccion == DIR_FAVORECE == rr.direccion:
                detalle = (f"el CTR propio favorece «{rc.grupo}» y el corpus ajeno "
                           f"favorece «{rr.grupo}» para el mismo campo `{rc.campo}`")
            else:
                continue
            conflictos.append(Conflicto(rc.campo, rc.id, rr.id, detalle))
            rc.conflicto_con = rr.id
            rr.conflicto_con = rc.id
    return conflictos


def _filas(anotaciones: dict[str, dict], valores_y: dict[str, float],
           esquema: dict[str, tuple]) -> list[dict]:
    """Cruce: una fila por video que tiene anotacion y variable dependiente."""
    filas = []
    for vid, y in valores_y.items():
        anotacion = anotaciones.get(vid)
        if anotacion is None:
            continue
        fila = {campo: anotacion.get(campo) for campo in esquema}
        fila["__y"] = y
        fila["__video_id"] = vid
        filas.append(fila)
    return filas


def analizar(perfil: Perfil, *,
             archivo_videos: Path | None = None,
             archivo_anotaciones: Path | None = None,
             archivo_ctr: Path | None = None,
             n_minima: int = N_MINIMA,
             max_reglas: int = MAX_REGLAS,
             umbral_efecto: float = UMBRAL_EFECTO) -> Informe:
    """Cruza metadata con anotaciones y devuelve el informe completo.

    No sale a la red y no escribe nada: escribir es tarea de
    `escribir_reglas`, para que se pueda inspeccionar el informe antes.
    """
    ruta_videos = Path(archivo_videos) if archivo_videos else perfil.archivo_videos
    ruta_anotaciones = Path(archivo_anotaciones) if archivo_anotaciones else perfil.archivo_anotaciones
    ruta_ctr = Path(archivo_ctr) if archivo_ctr else perfil.archivo_ctr

    esquema = perfil.esquema_anotacion()
    contadores: dict[str, int] = {}
    avisos: list[str] = []

    videos = leer_jsonl(ruta_videos, contadores, "videos")
    anotados = leer_jsonl(ruta_anotaciones, contadores, "anotaciones")

    anotaciones = {str(a["video_id"]): a for a in anotados}
    contadores["anotaciones_utiles"] = len(anotaciones)
    contadores["videos_utiles"] = len(videos)

    puntajes: dict[str, float] = {}
    for video in videos:
        score = _outlier_score(video)
        if score is None:
            contadores["videos_sin_outlier_score"] = contadores.get("videos_sin_outlier_score", 0) + 1
            continue
        puntajes[str(video["video_id"])] = score
    contadores["sin_anotacion"] = sum(1 for v in puntajes if v not in anotaciones)

    filas_corpus = _filas(anotaciones, puntajes, esquema)
    contadores["cruzados_corpus"] = len(filas_corpus)

    publicadas, sobrantes, descartes = _analizar_metrica(
        filas_corpus, esquema, n_minima, umbral_efecto, max_reglas)
    bloque_corpus = Bloque(metrica=METRICA_CORPUS, fuente=FUENTE_CORPUS,
                           n_total=len(filas_corpus), descartes=descartes,
                           sobrantes=sobrantes)
    if bloque_corpus.suficiente:
        bloque_corpus.reglas = _a_reglas(publicadas, METRICA_CORPUS, FUENTE_CORPUS)

    # --- CTR propio ---------------------------------------------------------
    bloque_ctr: Bloque | None = None
    deteccion: dict[str, Any] = {}
    if ruta_ctr.is_file():
        try:
            lectura = leer_ctr(ruta_ctr)
        except ErrorCorpus as exc:
            avisos.append(f"mi_ctr.csv presente pero ilegible: {exc}")
            bloque_ctr = Bloque(metrica=METRICA_CTR, fuente=FUENTE_CTR, n_total=0,
                                disponible=False, motivo_no_disponible=str(exc))
        else:
            deteccion = {
                "archivo": str(ruta_ctr),
                "columna_id": lectura.columna_id,
                "columna_ctr": lectura.columna_ctr,
                "separador": lectura.separador,
                "filas_leidas": lectura.filas_leidas,
                "filas_salteadas": lectura.filas_salteadas,
            }
            filas_ctr = _filas(anotaciones, lectura.valores, esquema)
            contadores["cruzados_ctr"] = len(filas_ctr)
            if not filas_ctr:
                avisos.append(
                    f"mi_ctr.csv trae {len(lectura.valores)} video(s) con CTR pero ninguno "
                    f"esta en anotaciones.jsonl. Para analizar el CTR propio, los videos "
                    f"del canal propio tienen que estar anotados por M2."
                )
            pub_ctr, sob_ctr, desc_ctr = _analizar_metrica(
                filas_ctr, esquema, n_minima, umbral_efecto, max_reglas)
            bloque_ctr = Bloque(metrica=METRICA_CTR, fuente=FUENTE_CTR,
                                n_total=len(filas_ctr), descartes=desc_ctr, sobrantes=sob_ctr)
            if bloque_ctr.suficiente:
                bloque_ctr.reglas = _a_reglas(pub_ctr, METRICA_CTR, FUENTE_CTR)

    informe = Informe(
        perfil_slug=perfil.slug,
        generado_en=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        lecturas=contadores,
        corpus=bloque_corpus,
        ctr=bloque_ctr,
        avisos=avisos,
        ruta_reglas=perfil.archivo_reglas,
        parametros={"n_minima": n_minima, "max_reglas": max_reglas,
                    "umbral_efecto": umbral_efecto, "tramos": TRAMOS},
        deteccion_ctr=deteccion,
    )
    informe.conflictos = _detectar_conflictos(bloque_ctr, bloque_corpus)
    return informe


# --- render -------------------------------------------------------------------
def _linea_regla(regla: Regla) -> list[str]:
    """El bloque de una regla. Cada campo va en su linea para que la
    trazabilidad se pueda leer y tambien parsear."""
    lineas = [
        f"### {regla.id} - {regla.texto}",
        "",
        f"- corte: {regla.corte}",
        f"- n: grupo={regla.n_grupo} / resto={regla.n_resto} / total={regla.n_total}",
        f"- mediana {regla.metrica}: grupo={_fmt(regla.mediana_grupo)} "
        f"/ resto={_fmt(regla.mediana_resto)}",
        f"- efecto: {_fmt_efecto(regla.efecto)} ({regla.direccion})",
    ]
    if regla.conflicto_con:
        lineas.append(f"- CONFLICTO: contradice a {regla.conflicto_con} del otro informe.")
    lineas.append("")
    return lineas


def _seccion_descartes(bloque: Bloque) -> list[str]:
    lineas: list[str] = []
    insuficientes = bloque.insuficientes
    if insuficientes:
        lineas.append(f"Cortes sin muestra suficiente (n minima {N_MINIMA} de los dos lados). "
                      f"Se miraron y no generan regla:")
        lineas.append("")
        for d in insuficientes:
            lineas.append(f"- `{d.campo}` = «{d.grupo}»: n grupo={d.n_grupo} / "
                          f"resto={d.n_resto} {MARCA_INSUFICIENTE}")
        lineas.append("")
    otros = [d for d in bloque.descartes if not d.insuficiente]
    if otros:
        lineas.append("Cortes con muestra suficiente que no llegaron a regla:")
        lineas.append("")
        for d in otros:
            lineas.append(f"- `{d.campo}` = «{d.grupo}»: n grupo={d.n_grupo} / "
                          f"resto={d.n_resto} - {d.motivo}"
                          + (f" ({d.detalle})" if d.detalle else ""))
        lineas.append("")
    if not lineas:
        lineas.append("No hubo cortes descartados.")
        lineas.append("")
    return lineas


def _seccion_bloque(bloque: Bloque | None, titulo: str, encabezado: list[str],
                    parametros: dict[str, Any]) -> list[str]:
    lineas = [f"## {titulo}", ""]
    lineas.extend(encabezado)

    if bloque is None:
        lineas.append("")
        return lineas
    if not bloque.disponible:
        lineas += ["", f"No se pudo usar: {bloque.motivo_no_disponible}", ""]
        return lineas

    lineas.append("")
    lineas.append(f"Videos cruzados: n = {bloque.n_total}. "
                  f"Variable dependiente: `{bloque.metrica}`.")
    lineas.append("")
    if not bloque.suficiente:
        lineas.append(
            f"{MARCA_INSUFICIENTE} n = {bloque.n_total} y hacen falta al menos "
            f"{2 * N_MINIMA} videos cruzados para partir el corpus en dos grupos de "
            f"{parametros.get('n_minima', N_MINIMA)}. No se emite ninguna regla."
        )
        lineas.append("")
        lineas.extend(_seccion_descartes(bloque))
        return lineas

    if not bloque.reglas:
        lineas.append("Ningun corte supero a la vez la n minima y el umbral de efecto. "
                      "No se emite ninguna regla.")
        lineas.append("")
    for regla in bloque.reglas:
        lineas.extend(_linea_regla(regla))

    if bloque.sobrantes:
        lineas.append(f"Candidatas que no entraron por el tope de "
                      f"{parametros.get('max_reglas', MAX_REGLAS)} reglas:")
        lineas.append("")
        for c in bloque.sobrantes:
            lineas.append(f"- `{c.campo}` = «{c.grupo}»: efecto {_fmt_efecto(c.efecto)}, "
                          f"n grupo={c.n_grupo} / resto={c.n_resto}")
        lineas.append("")

    lineas.append("<details><summary>Cortes descartados</summary>")
    lineas.append("")
    lineas.extend(_seccion_descartes(bloque))
    lineas.append("</details>")
    lineas.append("")
    return lineas


def render_markdown(informe: Informe) -> str:
    """reglas.md completo. Formato pensado para dos lectores: una persona y M4."""
    p = informe.parametros
    lineas: list[str] = [
        f"# Reglas de miniatura - perfil `{informe.perfil_slug}`",
        "",
        f"Generado por M3 (patrones) el {informe.generado_en}. No editar a mano: "
        f"se reescribe entero en cada corrida de `thumbforge reglas`.",
        "",
        "## Como se lee esto",
        "",
        f"- Cada regla tiene un identificador estable (`R1`, `R2`, ... para el corpus "
        f"ajeno; `C1`, `C2`, ... para el CTR propio). M4 cita ese identificador en "
        f"`reglas_aplicadas`, y desde ahi se vuelve a esta linea con su `n`.",
        f"- `n` es la cantidad de videos de cada lado del corte: `grupo` son los que "
        f"cumplen la condicion, `resto` son los demas videos que tienen ese campo "
        f"anotado. Con menos de {p.get('n_minima', N_MINIMA)} de un lado no se emite "
        f"regla y el corte queda marcado {MARCA_INSUFICIENTE}.",
        "- Se comparan **medianas**, nunca promedios: un solo video viral mueve un "
        "promedio cientos por ciento y una mediana casi nada.",
        f"- `efecto` es la diferencia relativa entre las dos medianas. Se publica a "
        f"partir de {_fmt_efecto(p.get('umbral_efecto', UMBRAL_EFECTO))}.",
        "- El `outlier_score` es rendimiento **relativo al propio canal** de cada video "
        "(views sobre la mediana de su canal), **no es CTR**. El CTR ajeno no existe "
        "en ninguna API.",
        "- Correlacion, no causa: el corte explica con que aparece asociado el "
        "rendimiento, no que lo produzca.",
        "",
        "## Orden de autoridad",
        "",
        "1. **Informe A - CTR propio**: sale de `mi_ctr.csv`, el unico CTR real que "
        "existe. **Pesa mas** que cualquier conclusion del corpus ajeno.",
        "2. **Informe B - corpus ajeno**: sale de videos de otros canales, medido con "
        "`outlier_score`. Se usa cuando el Informe A no dice nada sobre ese campo.",
        "",
        "Cuando los dos se contradicen, manda el Informe A y el choque queda anotado "
        "en la seccion de conflictos.",
        "",
        "## Origen de los datos",
        "",
    ]

    for clave in sorted(informe.lecturas):
        lineas.append(f"- {clave}: {informe.lecturas[clave]}")
    lineas.append("")
    if informe.deteccion_ctr:
        d = informe.deteccion_ctr
        lineas.append(f"- mi_ctr.csv: separador `{d['separador']}`, columna de id "
                      f"`{d['columna_id']}`, columna de CTR `{d['columna_ctr']}`, "
                      f"{d['filas_leidas']} fila(s), {d['filas_salteadas']} salteada(s).")
        lineas.append("")
    if informe.avisos:
        lineas.append("### Avisos")
        lineas.append("")
        for aviso in informe.avisos:
            lineas.append(f"- {aviso}")
        lineas.append("")

    encabezado_ctr = [
        "**Estas conclusiones pesan mas que las del Informe B.** Salen del CTR real del "
        "canal propio, exportado a mano desde el Modo Avanzado de YouTube Studio. "
        "Ninguna API expone el CTR de un canal ajeno.",
    ]
    if informe.ctr is None:
        encabezado_ctr.append("")
        encabezado_ctr.append(
            "No hay `corpus/mi_ctr.csv`, asi que este informe esta vacio. Para tenerlo: "
            "YouTube Studio > Analytics > Modo avanzado > exportar la tabla con la "
            "columna 'Porcentaje de clics de las impresiones (%)' y dejar el archivo "
            "en `corpus/mi_ctr.csv`. Mientras tanto solo aplica el Informe B, que mide "
            "rendimiento relativo ajeno y no CTR.")
    lineas.extend(_seccion_bloque(informe.ctr, "Informe A - CTR propio (pesa mas)",
                                  encabezado_ctr, p))

    encabezado_corpus = [
        "Corpus de referencia de otros canales, medido con `outlier_score` "
        "(views sobre la mediana del canal). Es rendimiento relativo, no CTR. "
        "Cede ante el Informe A.",
    ]
    lineas.extend(_seccion_bloque(informe.corpus, "Informe B - corpus ajeno (outlier_score)",
                                  encabezado_corpus, p))

    lineas.append("## Conflictos entre informes")
    lineas.append("")
    if informe.conflictos:
        lineas.append("El CTR propio contradice al corpus ajeno en estos puntos. "
                      "**Gana el CTR propio.**")
        lineas.append("")
        for c in informe.conflictos:
            lineas.append(f"- `{c.campo}`: {c.regla_ctr} (CTR propio) vs "
                          f"{c.regla_corpus} (corpus ajeno) - {c.detalle}. "
                          f"Aplica {c.regla_ctr}.")
    else:
        lineas.append("Ninguno.")
    lineas.append("")

    lineas.append("## Apendice legible por maquina")
    lineas.append("")
    lineas.append("`leer_reglas()` prefiere este bloque; si falta, vuelve a parsear "
                  "las secciones de arriba.")
    lineas.append("")
    lineas.append(MARCA_DATOS)
    lineas.append("```json")
    lineas.append(json.dumps(_a_json(informe), ensure_ascii=False, indent=2))
    lineas.append("```")
    lineas.append("")
    return "\n".join(lineas)


def _a_json(informe: Informe) -> dict:
    return {
        "perfil": informe.perfil_slug,
        "generado_en": informe.generado_en,
        "parametros": informe.parametros,
        "lecturas": informe.lecturas,
        "avisos": informe.avisos,
        "conflictos": [asdict(c) for c in informe.conflictos],
        "reglas": [asdict(r) for r in informe.reglas_activas()],
    }


def escribir_reglas(informe: Informe, ruta: Path | None = None) -> Path:
    """Escribe reglas.md y devuelve la ruta. Crea `corpus/` si no existe."""
    destino = Path(ruta) if ruta else informe.ruta_reglas
    if destino is None:
        raise ErrorCorpus("No se sabe donde escribir las reglas: pasa una ruta.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(render_markdown(informe), encoding="utf-8")
    return destino


# --- lectura de vuelta (la usa M4) -------------------------------------------
_RE_TITULO_REGLA = re.compile(r"^###\s+([RC]\d+)\s+-\s+(.+?)\s*$")
_RE_N = re.compile(r"^-\s+n:\s+grupo=(\d+)\s*/\s*resto=(\d+)")
_RE_MEDIANA = re.compile(r"^-\s+mediana\s+(\S+):\s+grupo=([-\d.]+)\s*/\s*resto=([-\d.]+)")
_RE_EFECTO = re.compile(r"^-\s+efecto:\s+([+-][\d.]+)%\s+\((\w+)\)")
_RE_CORTE = re.compile(r"^-\s+corte:\s+`([^`]+)`\s*(.*)$")


def _reglas_desde_json(texto: str) -> list[Regla] | None:
    if MARCA_DATOS not in texto:
        return None
    resto = texto.split(MARCA_DATOS, 1)[1]
    inicio = resto.find("```json")
    if inicio < 0:
        return None
    cuerpo = resto[inicio + len("```json"):]
    fin = cuerpo.find("```")
    if fin < 0:
        return None
    try:
        datos = json.loads(cuerpo[:fin])
    except json.JSONDecodeError:
        return None
    reglas = []
    for d in datos.get("reglas", []):
        try:
            reglas.append(Regla(**d))
        except TypeError:
            return None
    return reglas


def _reglas_desde_markdown(texto: str) -> list[Regla]:
    """Respaldo por si alguien edito el archivo y rompio el apendice JSON."""
    reglas: list[Regla] = []
    actual: dict[str, Any] | None = None

    def cerrar() -> None:
        if actual and {"n_grupo", "mediana_grupo", "efecto"} <= actual.keys():
            reglas.append(Regla(**actual))  # type: ignore[arg-type]

    for linea in texto.splitlines():
        m = _RE_TITULO_REGLA.match(linea)
        if m:
            cerrar()
            identificador, cuerpo = m.group(1), m.group(2)
            actual = {
                "id": identificador,
                "texto": cuerpo,
                "campo": "",
                "grupo": "",
                "tipo_corte": "",
                "direccion": "",
                "n_resto": 0,
                "mediana_resto": 0.0,
                "metrica": METRICA_CTR if identificador.startswith("C") else METRICA_CORPUS,
                "fuente": FUENTE_CTR if identificador.startswith("C") else FUENTE_CORPUS,
                "conflicto_con": "",
            }
            continue
        if actual is None:
            continue
        m = _RE_CORTE.match(linea)
        if m:
            actual["campo"] = m.group(1)
            cola = m.group(2)
            valor = re.search(r"«([^»]*)»", cola)
            if "tramo" in cola:
                actual["tipo_corte"] = CORTE_TRAMO
                actual["grupo"] = valor.group(1) if valor else ""
            elif cola.strip().startswith("contiene"):
                actual["tipo_corte"] = CORTE_PERTENENCIA
                actual["grupo"] = cola.strip()
            else:
                actual["tipo_corte"] = CORTE_CATEGORICO
                actual["grupo"] = valor.group(1) if valor else ""
            continue
        m = _RE_N.match(linea)
        if m:
            actual["n_grupo"] = int(m.group(1))
            actual["n_resto"] = int(m.group(2))
            continue
        m = _RE_MEDIANA.match(linea)
        if m:
            actual["metrica"] = m.group(1)
            actual["mediana_grupo"] = float(m.group(2))
            actual["mediana_resto"] = float(m.group(3))
            continue
        m = _RE_EFECTO.match(linea)
        if m:
            actual["efecto"] = float(m.group(1)) / 100.0
            actual["direccion"] = m.group(2)
            continue
        if linea.startswith("- CONFLICTO: contradice a "):
            actual["conflicto_con"] = linea.split("contradice a ", 1)[1].split()[0]
    cerrar()
    return reglas


def leer_reglas(perfil: Perfil | Path) -> list[Regla]:
    """Reglas activas de reglas.md, las del CTR propio primero.

    Es la puerta de entrada de M4: cita `regla.id` en `reglas_aplicadas` y con
    eso cualquiera vuelve a la linea de reglas.md que la origino.
    """
    ruta = perfil.archivo_reglas if isinstance(perfil, Perfil) else Path(perfil)
    if not ruta.is_file():
        raise ErrorCorpus(
            f"No existe {ruta}. Generalo con 'thumbforge reglas --perfil "
            f"{ruta.parent.parent.name}' despues de recolectar y anotar el corpus."
        )
    texto = ruta.read_text("utf-8")
    desde_json = _reglas_desde_json(texto)
    if desde_json is not None:
        return desde_json
    return _reglas_desde_markdown(texto)
