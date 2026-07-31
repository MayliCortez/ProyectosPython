"""M1 - recolector del corpus de referencia.

Junta videos de referencia con la YouTube Data API v3 (por HTTP, sin SDK) y
escribe `perfiles/<slug>/corpus/videos.jsonl`, un registro JSON por linea.

**El CTR ajeno no existe en ninguna API.** Ni la Data API v3 ni ninguna otra
fuente publica expone el click-through rate de un video de otro canal.
Cualquier herramienta que diga estimarlo, lo esta inventando. Lo unico que
este modulo calcula es:

    outlier_score = views / mediana_del_canal_en_la_ventana

es decir, cuanto rindio un video **contra su propio canal**. Es rendimiento
relativo y **no es CTR**. Comparar views entre canales de tamanos distintos no
dice nada; compararlas contra la mediana del mismo canal, si.

Este archivo no sabe de que trata el canal: las queries y los canales de
referencia salen de `corpus.queries` y `corpus.canales_referencia` del perfil.

Todo lo que sale a la red pasa por `red` y se cachea en `cache`, para que la
segunda corrida sin `--refrescar` no gaste ni una llamada ni una unidad de
cuota.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from .. import proveedores, red
from ..cache import Cache, huella
from ..errores import ErrorProveedor, ErrorThumbforge
from ..perfiles import Perfil

API_BASE = "https://www.googleapis.com/youtube/v3"
DESTINO = "youtube"

# --- reglas duras del motor --------------------------------------------------
# Un Short entra por otra superficie, con otra miniatura y otro comportamiento
# de audiencia: mezclarlo con video largo ensucia cualquier conclusion. El
# corte va en 62 s y no en 60 porque YouTube redondea y deja pasar 61.
DURACION_MINIMA_S = 62

# Un video de tres dias todavia esta acumulando views: su outlier_score es
# ruido, no senal.
ANTIGUEDAD_MINIMA_DIAS = 14

# Con uno o dos videos la "mediana del canal" es el propio video: el
# outlier_score daria 1.0 y mentiria. Ver `MOTIVO_POCOS_VIDEOS`.
MINIMO_VIDEOS_PARA_MEDIANA = 3

# `videos.list` acepta hasta 50 ids por llamada y cuesta 1 unidad la llamada,
# no 1 por video. Pedir de a uno multiplica la cuota por 50.
TAMANO_LOTE_VIDEOS = 50

# Ventana temporal por defecto. La mediana del canal se calcula sobre lo que
# entro en esta ventana, no sobre su historia completa.
VENTANA_DIAS_DEFECTO = 365
MAX_POR_FUENTE_DEFECTO = 50
MAX_RESULTADOS_PAGINA = 50

ORDEN_QUERY_DEFECTO = "relevance"
ORDEN_CANAL_DEFECTO = "date"

# De mayor a menor. Se guarda la mas grande disponible: recortar despues es
# gratis, volver a la red por una resolucion que no se bajo, no.
CALIDADES_MINIATURA = ("maxres", "standard", "high", "medium", "default")

MOTIVO_POCOS_VIDEOS = "canal_con_menos_de_3_videos_en_la_ventana"
MOTIVO_MEDIANA_CERO = "mediana_del_canal_es_cero"
MOTIVO_SIN_VIEWS = "el_video_no_reporta_views"

ESPACIO_BUSQUEDA = "yt_busqueda"
ESPACIO_VIDEOS = "yt_videos"
ESPACIO_MINIATURAS = "miniaturas"


# --- duraciones ISO-8601 -----------------------------------------------------
# YouTube devuelve la duracion como `PT4M13S`, y en los casos raros como
# `PT1H` (sin minutos ni segundos), `P1DT2H3M4S` (emisiones largas) o `P0D`
# (un vivo en curso). Un split por 'M' se rompe con todos esos.
_RE_DURACION = re.compile(
    r"^P"
    r"(?:(?P<semanas>\d+)W)?"
    r"(?:(?P<dias>\d+)D)?"
    r"(?:T"
    r"(?:(?P<horas>\d+)H)?"
    r"(?:(?P<minutos>\d+)M)?"
    r"(?:(?P<segundos>\d+(?:[.,]\d+)?)S)?"
    r")?$"
)

_FACTORES = {"semanas": 604800, "dias": 86400, "horas": 3600, "minutos": 60, "segundos": 1}


def duracion_iso_a_segundos(texto: str) -> int:
    """`PT4M13S` -> 253. Levanta ValueError si no es una duracion reconocible.

    No acepta anos ni meses: YouTube no los emite y su longitud en segundos
    depende del calendario, asi que convertirlos seria inventar un numero.
    """
    if not isinstance(texto, str):
        raise ValueError(f"duracion ISO-8601 no reconocida: {texto!r}")
    m = _RE_DURACION.fullmatch(texto.strip().upper())
    if m is None:
        raise ValueError(f"duracion ISO-8601 no reconocida: {texto!r}")
    partes = m.groupdict()
    if all(v is None for v in partes.values()):
        # 'P' o 'PT' pelados: sintacticamente parecidos, semanticamente vacios.
        raise ValueError(f"duracion ISO-8601 sin ningun componente: {texto!r}")
    total = 0.0
    for nombre, valor in partes.items():
        if valor is not None:
            total += float(valor.replace(",", ".")) * _FACTORES[nombre]
    return int(round(total))


def _fecha(texto: str) -> datetime:
    return datetime.fromisoformat(str(texto).replace("Z", "+00:00"))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# --- transporte --------------------------------------------------------------
class Transporte(Protocol):
    """Seam de inyeccion. En produccion es `TransporteHTTP`; en las pruebas,
    un doble que devuelve respuestas grabadas."""

    def obtener_json(self, url: str, params: dict) -> dict: ...

    def obtener_bytes(self, url: str) -> bytes: ...


class TransporteHTTP:
    """Unica salida real a internet de este modulo, siempre via `red`."""

    def __init__(self, destino: str = DESTINO):
        self.destino = destino

    def obtener_json(self, url: str, params: dict) -> dict:
        with red.cliente(self.destino) as c:
            r = c.get(url, params=params)
        if r.status_code != 200:
            raise ErrorProveedor(_explicar_http(r.status_code, r.text))
        return r.json()

    def obtener_bytes(self, url: str) -> bytes:
        with red.cliente(self.destino) as c:
            r = c.get(url)
        if r.status_code != 200:
            raise ErrorProveedor(f"La miniatura {url} respondio HTTP {r.status_code}")
        return r.content


def _explicar_http(codigo: int, cuerpo: str) -> str:
    """Traduce el error de la API a algo accionable.

    Un 403 de esta API casi nunca es "no tenes permiso": es la cuota diaria
    agotada, y decirlo ahorra una hora de revisar credenciales sanas.
    """
    razon = ""
    m = re.search(r'"reason"\s*:\s*"([^"]+)"', cuerpo or "")
    if m:
        razon = m.group(1)
    if razon in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
        return (
            f"YouTube respondio {codigo} ({razon}): se agoto la cuota diaria del proyecto. "
            f"La cuota se renueva a medianoche hora del Pacifico. Mientras tanto, el corpus "
            f"ya cacheado sigue sirviendo: corre sin --refrescar."
        )
    if codigo == 403:
        return (
            f"YouTube respondio 403 ({razon or 'sin razon declarada'}): la clave no tiene "
            f"permiso o la Data API v3 no esta habilitada en el proyecto. "
            f"Corre 'thumbforge doctor' para confirmarlo."
        )
    if codigo == 400:
        return f"YouTube respondio 400 ({razon or 'peticion invalida'}): {(cuerpo or '')[:300]}"
    return f"YouTube respondio HTTP {codigo}: {(cuerpo or '')[:300]}"


# --- resumen -----------------------------------------------------------------
@dataclass
class ResumenRecoleccion:
    """Contadores de una corrida. Lo que la CLI imprime."""

    perfil: str
    archivo: Path | None = None
    fuentes: int = 0
    ids_encontrados: int = 0
    ids_unicos: int = 0
    metadatos_leidos: int = 0
    descartados_shorts: int = 0
    descartados_recientes: int = 0
    descartados_sin_duracion: int = 0
    canales: int = 0
    canales_sin_mediana: int = 0
    con_outlier: int = 0
    miniaturas_ok: int = 0
    miniaturas_fallidas: int = 0
    escritos: int = 0
    llamadas_red: int = 0
    avisos: list[str] = field(default_factory=list)

    def texto(self) -> str:
        lineas = [
            f"perfil            {self.perfil}",
            f"fuentes           {self.fuentes} (queries + canales de referencia)",
            f"ids unicos        {self.ids_unicos} de {self.ids_encontrados} encontrados",
            f"metadatos         {self.metadatos_leidos}",
            f"descartes         {self.descartados_shorts} shorts, "
            f"{self.descartados_recientes} recientes, "
            f"{self.descartados_sin_duracion} sin duracion legible",
            f"canales           {self.canales} ({self.canales_sin_mediana} sin mediana confiable)",
            f"outlier_score     {self.con_outlier} calculados",
            f"miniaturas        {self.miniaturas_ok} en cache, {self.miniaturas_fallidas} fallidas",
            f"escritos          {self.escritos} -> {self.archivo}",
            f"llamadas de red   {self.llamadas_red}",
        ]
        lineas += [f"aviso             {a}" for a in self.avisos]
        return "\n".join(lineas)


# --- jsonl -------------------------------------------------------------------
def leer_jsonl(ruta: Path) -> list[dict]:
    """Lee un .jsonl salteando lineas corruptas.

    Una linea rota no puede tirar abajo un corpus de 300 registros que costo
    cuota y tokens: se ignora y el resto sigue.
    """
    if not Path(ruta).is_file():
        return []
    import json

    registros: list[dict] = []
    for linea in Path(ruta).read_text("utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            valor = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(valor, dict):
            registros.append(valor)
    return registros


def escribir_jsonl(ruta: Path, registros: Iterable[dict]) -> int:
    """Escritura atomica: un ctrl-C a mitad no deja medio corpus pisado."""
    import json

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cuerpo = "".join(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n"
                     for r in registros)
    tmp = ruta.with_suffix(ruta.suffix + ".parcial")
    tmp.write_text(cuerpo, "utf-8")
    tmp.replace(ruta)
    return cuerpo.count("\n")


# --- cache con refresco ------------------------------------------------------
def _memo(cache: Cache, espacio: str, clave: str, productor: Callable[[], Any],
          refrescar: bool) -> Any:
    if refrescar:
        cache.ruta(espacio, clave).unlink(missing_ok=True)
    return cache.memo(espacio, clave, productor)


def _memo_bytes(cache: Cache, espacio: str, clave: str, productor: Callable[[], bytes],
                sufijo: str, refrescar: bool) -> bytes:
    if refrescar:
        cache.ruta(espacio, clave, sufijo).unlink(missing_ok=True)
    return cache.memo_bytes(espacio, clave, productor, sufijo)


# --- fuentes -----------------------------------------------------------------
@dataclass(frozen=True)
class Fuente:
    """De donde salio un video. El motor no interpreta el valor: lo pasa."""

    tipo: str      # "query" | "canal"
    valor: str


def fuentes_del_perfil(perfil: Perfil) -> list[Fuente]:
    """`corpus.canales_referencia` + `corpus.queries`, en ese orden.

    Los canales van primero porque una lista curada de canales rinde mejor
    corpus que una query abierta, y si `limite` corta, corta lo de afuera.
    """
    fuentes: list[Fuente] = []
    for canal in perfil.get("corpus.canales_referencia") or []:
        texto = str(canal).strip()
        if texto:
            fuentes.append(Fuente("canal", texto))
    for query in perfil.get("corpus.queries") or []:
        texto = str(query).strip()
        if texto:
            fuentes.append(Fuente("query", texto))
    return fuentes


# --- cliente de la API -------------------------------------------------------
class ClienteYouTube:
    """Envoltorio fino sobre la Data API v3: cachea, pagina y agrupa.

    No decide nada del corpus; solo evita que el resto del modulo tenga que
    saber de paginacion, de lotes de 50 ni de claves de cache.
    """

    def __init__(self, cache: Cache, transporte: Transporte | None = None,
                 clave_api: str | None = None, refrescar: bool = False):
        self.cache = cache
        self.transporte = transporte if transporte is not None else TransporteHTTP()
        self._clave_api = clave_api
        self.refrescar = refrescar

    def clave_api(self) -> str:
        clave = self._clave_api or proveedores.por_id("youtube").clave()
        if not clave:
            raise ErrorProveedor(
                "Falta YOUTUBE_API_KEY en .env para recolectar el corpus. "
                "Corre 'thumbforge doctor' para ver que mas falta."
            )
        return clave

    # --- search.list ---------------------------------------------------------
    def buscar(self, fuente: Fuente, maximo: int, publicado_desde: datetime,
               orden: str, idioma: str | None) -> list[str]:
        """Ids de video de una fuente, paginando hasta `maximo`.

        Cada pagina se cachea por separado: si la corrida se corta a la
        tercera, la cuarta no vuelve a pagar las tres primeras.
        """
        ids: list[str] = []
        token: str | None = None
        while len(ids) < maximo:
            params = {
                "part": "snippet",
                "type": "video",
                "maxResults": min(MAX_RESULTADOS_PAGINA, maximo - len(ids)),
                "order": orden,
                "publishedAfter": publicado_desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if fuente.tipo == "canal":
                params["channelId"] = fuente.valor
            else:
                params["q"] = fuente.valor
            if idioma:
                params["relevanceLanguage"] = idioma
            if token:
                params["pageToken"] = token

            cuerpo = self._pedir(ESPACIO_BUSQUEDA, "search", params)
            for item in cuerpo.get("items") or []:
                vid = (item.get("id") or {}).get("videoId")
                if vid:
                    ids.append(str(vid))
            token = cuerpo.get("nextPageToken")
            if not token or not cuerpo.get("items"):
                break
        return ids[:maximo]

    # --- videos.list ---------------------------------------------------------
    def detalles(self, ids: list[str]) -> list[dict]:
        """Metadata de muchos videos en lotes de 50.

        Un `videos.list` cuesta 1 unidad de cuota por llamada, no por video:
        de a uno, 60 videos costarian 60 unidades en vez de 2.
        """
        salida: list[dict] = []
        for i in range(0, len(ids), TAMANO_LOTE_VIDEOS):
            lote = ids[i:i + TAMANO_LOTE_VIDEOS]
            params = {
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(lote),
                "maxResults": TAMANO_LOTE_VIDEOS,
            }
            cuerpo = self._pedir(ESPACIO_VIDEOS, "videos", params)
            salida.extend(cuerpo.get("items") or [])
        return salida

    # --- miniaturas ----------------------------------------------------------
    def miniatura(self, url: str) -> tuple[str, Path]:
        """Baja la miniatura a la cache. Devuelve (clave, ruta en disco).

        M2 la lee de ahi: el corpus guarda la ruta para no volver a bajarla.
        """
        clave = huella("miniatura", url)
        sufijo = ".png" if url.lower().split("?")[0].endswith(".png") else ".jpg"
        _memo_bytes(self.cache, ESPACIO_MINIATURAS, clave,
                    lambda: self.transporte.obtener_bytes(url), sufijo, self.refrescar)
        return clave, self.cache.ruta(ESPACIO_MINIATURAS, clave, sufijo)

    # --- interno -------------------------------------------------------------
    def _pedir(self, espacio: str, recurso: str, params: dict) -> dict:
        # La clave de cache excluye la API key a proposito: rotar la clave no
        # deberia invalidar un corpus que ya se pago.
        clave = huella(recurso, params)

        def productor() -> dict:
            con_clave = dict(params, key=self.clave_api())
            return self.transporte.obtener_json(f"{API_BASE}/{recurso}", con_clave)

        return _memo(self.cache, espacio, clave, productor, self.refrescar)


# --- armado del registro -----------------------------------------------------
def _entero(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def elegir_miniatura(miniaturas: dict) -> tuple[str, str]:
    """(calidad, url) de la resolucion mas alta disponible."""
    for calidad in CALIDADES_MINIATURA:
        entrada = (miniaturas or {}).get(calidad) or {}
        url = entrada.get("url")
        if url:
            return calidad, str(url)
    return "", ""


def mediana(valores: list[int]) -> float:
    return float(statistics.median(valores))


def calcular_outliers(registros: list[dict]) -> tuple[int, int]:
    """Completa mediana_canal y outlier_score in place.

    La mediana se toma sobre los videos del MISMO canal dentro de la ventana
    recolectada, nunca sobre el corpus entero: 200k views es un exito en un
    canal de 5k y un fracaso en uno de 2M.

    Decision explicita para canales con menos de `MINIMO_VIDEOS_PARA_MEDIANA`
    videos: el registro se conserva -sirve igual para M2, que mira la imagen-
    pero queda con `outlier_score: null` y `motivo_sin_outlier` cargado. Con
    n=1 la mediana es el propio video y el score daria 1.0 exacto: un numero
    que parece medido y no midio nada. Callarlo seria peor que no tenerlo.

    Devuelve (canales, canales sin mediana confiable).
    """
    por_canal: dict[str, list[dict]] = {}
    for reg in registros:
        por_canal.setdefault(reg["canal_id"], []).append(reg)

    sin_mediana = 0
    for canal_id, del_canal in por_canal.items():
        vistas = [r["views"] for r in del_canal if r["views"] is not None]
        n = len(vistas)
        med = mediana(vistas) if vistas else 0.0
        confiable = n >= MINIMO_VIDEOS_PARA_MEDIANA and med > 0
        if not confiable:
            sin_mediana += 1

        for reg in del_canal:
            reg["videos_del_canal_en_ventana"] = n
            reg["mediana_canal"] = med if n else None
            reg["outlier_confiable"] = confiable and reg["views"] is not None
            if reg["views"] is None:
                reg["outlier_score"] = None
                reg["motivo_sin_outlier"] = MOTIVO_SIN_VIEWS
            elif n < MINIMO_VIDEOS_PARA_MEDIANA:
                reg["outlier_score"] = None
                reg["motivo_sin_outlier"] = MOTIVO_POCOS_VIDEOS
            elif med <= 0:
                reg["outlier_score"] = None
                reg["motivo_sin_outlier"] = MOTIVO_MEDIANA_CERO
            else:
                reg["outlier_score"] = round(reg["views"] / med, 4)
                reg["motivo_sin_outlier"] = ""
    return len(por_canal), sin_mediana


def _registro(item: dict, fuente: Fuente, ahora: datetime, ventana_dias: int,
              duracion_s: int) -> dict:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    calidad, url = elegir_miniatura(snippet.get("thumbnails") or {})
    publicado = str(snippet.get("publishedAt") or "")
    antiguedad = (ahora - _fecha(publicado)).days if publicado else None
    descripcion = str(snippet.get("description") or "")

    return {
        "video_id": str(item.get("id") or ""),
        "canal_id": str(snippet.get("channelId") or ""),
        "canal_titulo": str(snippet.get("channelTitle") or ""),
        "titulo": str(snippet.get("title") or ""),
        "descripcion_corta": descripcion[:280],
        "publicado_en": publicado,
        "antiguedad_dias": antiguedad,
        "duracion_iso": str((item.get("contentDetails") or {}).get("duration") or ""),
        "duracion_s": duracion_s,
        "views": _entero(stats.get("viewCount")),
        # None y 0 no son lo mismo: un canal puede tener los likes ocultos.
        "likes": _entero(stats.get("likeCount")),
        "comentarios": _entero(stats.get("commentCount")),
        "miniatura_url": url,
        "miniatura_calidad": calidad,
        "miniatura_ruta": "",
        "miniatura_clave": "",
        "mediana_canal": None,
        "videos_del_canal_en_ventana": 0,
        "outlier_score": None,
        "outlier_confiable": False,
        "motivo_sin_outlier": "",
        "origen_tipo": fuente.tipo,
        "origen_valor": fuente.valor,
        "ventana_dias": ventana_dias,
        "recolectado_en": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# --- entrada publica ---------------------------------------------------------
def recolectar(perfil: Perfil, cache: Cache | None = None, refrescar: bool = False,
               limite: int | None = None, transporte: Transporte | None = None,
               clave_api: str | None = None) -> ResumenRecoleccion:
    """Recolecta el corpus del perfil y escribe `corpus/videos.jsonl`.

    `limite` acota cuantos registros se escriben, quedandose con los de mayor
    outlier_score; la mediana se calcula igual sobre todo lo recolectado en la
    ventana, asi recortar el corpus no deforma el denominador.

    Sin `refrescar`, una segunda corrida se resuelve entera desde la cache y
    no hace ni una llamada de red.
    """
    cache = cache if cache is not None else Cache()
    llamadas_antes = red.LLAMADAS.total
    resumen = ResumenRecoleccion(perfil=perfil.slug, archivo=perfil.archivo_videos)

    fuentes = fuentes_del_perfil(perfil)
    resumen.fuentes = len(fuentes)
    if not fuentes:
        raise ErrorThumbforge(
            f"El perfil '{perfil.slug}' no declara nada que recolectar. "
            f"Cargale 'corpus.queries' o 'corpus.canales_referencia' en perfil.yaml: "
            f"el motor no inventa terminos de busqueda, los lee del perfil."
        )

    ventana_dias = int(perfil.get("corpus.ventana_dias") or VENTANA_DIAS_DEFECTO)
    max_por_fuente = int(perfil.get("corpus.max_por_fuente") or MAX_POR_FUENTE_DEFECTO)
    idioma = (perfil.idioma or "").split("-")[0] or None

    ahora = _ahora()
    # El borde de la ventana se redondea a medianoche UTC a proposito: entra en
    # la clave de cache, y si se moviera con el reloj, dos corridas separadas
    # por un segundo pedirian lo mismo dos veces y la segunda volveria a pagar
    # cuota.
    publicado_desde = (ahora - timedelta(days=ventana_dias)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    # Nada mas nuevo que esto puede entrar. Se filtra del lado del motor: la
    # API no distingue "recien publicado" de "todavia acumulando views".
    corte_antiguedad = ahora - timedelta(days=ANTIGUEDAD_MINIMA_DIAS)

    cliente = ClienteYouTube(cache, transporte=transporte, clave_api=clave_api,
                             refrescar=refrescar)

    # 1. ids por fuente. Se guarda de que fuente salio cada id la primera vez
    #    que aparece: si dos queries traen el mismo video, gana la primera.
    origen_de: dict[str, Fuente] = {}
    for fuente in fuentes:
        orden = str(perfil.get("corpus.orden") or
                    (ORDEN_CANAL_DEFECTO if fuente.tipo == "canal" else ORDEN_QUERY_DEFECTO))
        ids = cliente.buscar(fuente, max_por_fuente, publicado_desde, orden, idioma)
        resumen.ids_encontrados += len(ids)
        for vid in ids:
            origen_de.setdefault(vid, fuente)
    resumen.ids_unicos = len(origen_de)

    # 2. metadata en lotes de 50.
    items = cliente.detalles(list(origen_de))
    resumen.metadatos_leidos = len(items)

    # 3. filtros duros.
    registros: list[dict] = []
    for item in items:
        vid = str(item.get("id") or "")
        fuente = origen_de.get(vid) or Fuente("query", "")
        iso = str((item.get("contentDetails") or {}).get("duration") or "")
        try:
            duracion_s = duracion_iso_a_segundos(iso)
        except ValueError:
            # Sin duracion legible no se puede saber si es un Short.
            resumen.descartados_sin_duracion += 1
            continue
        if duracion_s < DURACION_MINIMA_S:
            resumen.descartados_shorts += 1
            continue
        publicado = str((item.get("snippet") or {}).get("publishedAt") or "")
        if not publicado or _fecha(publicado) > corte_antiguedad:
            resumen.descartados_recientes += 1
            continue
        registros.append(_registro(item, fuente, ahora, ventana_dias, duracion_s))

    # 4. mediana por canal y outlier_score.
    resumen.canales, resumen.canales_sin_mediana = calcular_outliers(registros)
    resumen.con_outlier = sum(1 for r in registros if r["outlier_score"] is not None)
    if resumen.canales_sin_mediana:
        resumen.avisos.append(
            f"{resumen.canales_sin_mediana} canal(es) aportaron menos de "
            f"{MINIMO_VIDEOS_PARA_MEDIANA} videos en la ventana: sus registros quedan sin "
            f"outlier_score ('{MOTIVO_POCOS_VIDEOS}') en vez de con una mediana inventada."
        )

    # 5. recorte por limite, priorizando los outliers medidos.
    registros.sort(key=lambda r: (r["outlier_score"] is None,
                                  -(r["outlier_score"] or 0.0),
                                  -(r["views"] or 0)))
    if limite is not None:
        registros = registros[:max(0, int(limite))]

    # 6. miniaturas a la cache: M2 las necesita y no vuelve a la red por ellas.
    for reg in registros:
        if not reg["miniatura_url"]:
            resumen.miniaturas_fallidas += 1
            continue
        try:
            clave, ruta = cliente.miniatura(reg["miniatura_url"])
        except (ErrorProveedor, OSError) as exc:
            # Una miniatura caida no puede tirar abajo la recoleccion entera:
            # el registro queda y M2 lo marcara como no anotable.
            resumen.miniaturas_fallidas += 1
            resumen.avisos.append(f"miniatura de {reg['video_id']}: {exc}")
            continue
        reg["miniatura_clave"] = clave
        reg["miniatura_ruta"] = str(ruta)
        resumen.miniaturas_ok += 1

    resumen.escritos = escribir_jsonl(perfil.archivo_videos, registros)
    resumen.llamadas_red = red.LLAMADAS.total - llamadas_antes
    return resumen
