"""Resolucion de la base visual.

Hasta aca el motor sabia componer una miniatura pero no conseguir la imagen:
habia que pasarsela a mano. Eso lo ataba a un nicho, porque el operador tenia
que salir a buscar la foto.

Este modulo busca material de archivo con licencia verificable, lo puntua
contra la politica del perfil y elige el mejor. No sabe de que nicho se
trata: la consulta sale del concepto, y el concepto sale del guion.

Dos fuentes, ninguna con clave de API:

- Openverse: agregador de material con licencia Creative Commons.
- Wikimedia Commons: archivo con licencia verificable, fuerte en material
  historico y documental.

Elegir no es agarrar el primer resultado. Una foto sirve para una miniatura
si tiene resolucion, si tiene una zona limpia donde entre el texto, si el
sujeto se despega del fondo y si su color no pelea con el skin del canal.
Todo eso se mide antes de decidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from .. import color as col
from .. import composicion as comp
from .. import red
from ..cache import Cache, huella
from ..errores import ErrorThumbforge
from ..perfiles import Perfil, normalizar

# Licencias que permiten uso comercial y modificacion. Una miniatura recorta,
# superpone texto y se publica en un canal monetizable: las NC y las ND no
# sirven, y es mejor no ofrecerlas que dejar que el operador se entere despues.
LICENCIAS_ACEPTADAS = ("cc0", "pdm", "by", "by-sa")

MIN_ANCHO = 1280
MIN_ALTO = 720
MAXIMO_CANDIDATOS = 12
BYTES_MAXIMOS = 25 * 1024 * 1024

UA = "thumbforge/0.1 (motor de miniaturas; https://github.com/MayliCortez/ProyectosPython)"


class ErrorFuente(ErrorThumbforge):
    """No se pudo conseguir una base visual utilizable."""


@dataclass
class Candidato:
    url: str
    titulo: str = ""
    autor: str = ""
    licencia: str = ""
    version_licencia: str = ""
    url_origen: str = ""
    proveedor: str = ""
    ancho: int = 0
    alto: int = 0
    atribucion: str = ""
    puntaje: float = 0.0
    componentes: dict = field(default_factory=dict)
    descartado_por: str = ""

    @property
    def licencia_legible(self) -> str:
        if not self.licencia:
            return "sin declarar"
        base = self.licencia.upper()
        if base in ("CC0", "PDM"):
            return "CC0 / dominio publico"
        return f"CC {base}" + (f" {self.version_licencia}" if self.version_licencia else "")

    @property
    def verificada(self) -> bool:
        """El perfil puede exigir licencia verificada. Lo es si el proveedor
        la declara y ademas apunta a la pagina de origen, que es lo que
        permite comprobarla despues."""
        return bool(self.licencia) and bool(self.url_origen)


# --- busqueda ----------------------------------------------------------------
def _consultas(concepto: dict) -> list:
    """Consultas a probar, de la mas especifica a la mas general.

    Una sola consulta muy especifica devuelve cero resultados y deja al
    operador sin nada; una sola muy general devuelve cualquier cosa. Se
    prueban en orden y se corta en la primera que trae material.
    """
    base = concepto.get("base_visual") or {}
    copy = concepto.get("copy") or {}
    candidatas = [
        base.get("consulta_archivo"),
        base.get("descripcion"),
        copy.get("nombre_reconocible") or copy.get("producto"),
        str(base.get("categoria") or "").replace("_", " "),
    ]
    vistas, salida = set(), []
    for c in candidatas:
        texto = " ".join(str(c or "").split())[:120]
        if texto and normalizar(texto) not in vistas:
            vistas.add(normalizar(texto))
            salida.append(texto)
    return salida


def _buscar_openverse(consulta: str, cache: Cache, maximo: int) -> list:
    clave = huella("openverse", consulta, maximo)

    def traer():
        with red.cliente("openverse") as c:
            r = c.get("https://api.openverse.org/v1/images/",
                      params={"q": consulta, "page_size": maximo,
                              # Que el propio buscador filtre por licencia sale
                              # mas barato que traer y descartar.
                              "license_type": "commercial,modification"},
                      headers={"User-Agent": UA})
        return r.json() if r.status_code == 200 else {"results": []}

    datos = cache.memo("busquedas", clave, traer) or {}
    salida = []
    for it in datos.get("results", []):
        if not it.get("url"):
            continue
        salida.append(Candidato(
            url=it["url"], titulo=it.get("title") or "",
            autor=it.get("creator") or "", licencia=(it.get("license") or "").lower(),
            version_licencia=it.get("license_version") or "",
            url_origen=it.get("foreign_landing_url") or "",
            proveedor=f"Openverse/{it.get('source') or '?'}",
            ancho=int(it.get("width") or 0), alto=int(it.get("height") or 0),
            atribucion=it.get("attribution") or ""))
    return salida


def _buscar_commons(consulta: str, cache: Cache, maximo: int) -> list:
    clave = huella("commons", consulta, maximo)

    def traer():
        with red.cliente("commons") as c:
            r = c.get("https://commons.wikimedia.org/w/api.php",
                      params={"action": "query", "format": "json",
                              "generator": "search", "gsrnamespace": 6,
                              "gsrsearch": f"filetype:bitmap {consulta}",
                              "gsrlimit": maximo, "prop": "imageinfo",
                              "iiprop": "url|size|extmetadata",
                              "iiurlwidth": 1600},
                      headers={"User-Agent": UA})
        return r.json() if r.status_code == 200 else {}

    datos = cache.memo("busquedas", clave, traer) or {}
    salida = []
    for pagina in (datos.get("query") or {}).get("pages", {}).values():
        info = (pagina.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        licencia = (meta.get("License", {}).get("value") or "").lower()
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        salida.append(Candidato(
            url=url, titulo=pagina.get("title", "").replace("File:", ""),
            autor=_limpiar_html(meta.get("Artist", {}).get("value", "")),
            licencia=licencia,
            url_origen=info.get("descriptionurl") or "",
            proveedor="Wikimedia Commons",
            ancho=int(info.get("thumbwidth") or info.get("width") or 0),
            alto=int(info.get("thumbheight") or info.get("height") or 0),
            atribucion=_limpiar_html(
                meta.get("Attribution", {}).get("value", "")) or ""))
    return salida


def _limpiar_html(texto: str) -> str:
    import re
    return " ".join(re.sub(r"<[^>]+>", " ", texto or "").split())[:160]


def buscar(concepto: dict, cache: Cache, maximo: int = MAXIMO_CANDIDATOS,
           licencias: tuple = LICENCIAS_ACEPTADAS) -> tuple:
    """Devuelve ([candidatos], consulta_usada)."""
    def filtrar(crudos: list) -> list:
        utiles = []
        for c in crudos:
            # Match EXACTO, no de subcadena: la lista aceptada tiene 'by' y
            # las prohibidas ('by-nc', 'by-nd') lo contienen, asi que un
            # 'in' de cadena aceptaria las NC.
            if licencias and c.licencia not in licencias:
                c.descartado_por = f"licencia '{c.licencia or 'sin declarar'}' no admitida"
                continue
            if c.ancho and c.alto and (c.ancho < MIN_ANCHO // 2 or c.alto < MIN_ALTO // 2):
                c.descartado_por = f"resolucion {c.ancho}x{c.alto} demasiado baja"
                continue
            utiles.append(c)
        return utiles

    for consulta in _consultas(concepto):
        # Se prueba Openverse primero por variedad; solo se recurre a Commons
        # cuando la primera fuente no da suficientes CANDIDATOS UTILES, no
        # cuando trae resultados que despues se filtran.
        crudos = _buscar_openverse(consulta, cache, maximo)
        utiles = filtrar(crudos)
        if len(utiles) < 3:
            mas = _buscar_commons(consulta, cache, maximo)
            utiles.extend(filtrar(mas))
        if utiles:
            return utiles, consulta
    return [], ""


# --- descarga ----------------------------------------------------------------
def descargar(candidato: Candidato, cache: Cache) -> bytes:
    clave = huella("imagen", candidato.url)

    def traer():
        with red.cliente("descarga_imagen") as c:
            r = c.get(candidato.url, headers={"User-Agent": UA})
        if r.status_code != 200:
            raise ErrorFuente(f"HTTP {r.status_code} al bajar {candidato.url}")
        if len(r.content) > BYTES_MAXIMOS:
            raise ErrorFuente(f"{candidato.url} pesa mas de {BYTES_MAXIMOS} bytes")
        return r.content

    return cache.memo_bytes("imagenes", clave, traer, sufijo=".img")


# --- puntuacion --------------------------------------------------------------
def puntuar(imagen: Image.Image, perfil: Perfil) -> tuple:
    """Que tan bien sirve esta foto para una miniatura de ESTE perfil.

    No es calidad fotografica: es aptitud. Una foto preciosa sin una zona
    limpia donde entre el titular no sirve, y una correcta con aire y un
    sujeto que se despega, si.
    """
    pol_col = col.politica_color(perfil)
    pol_comp = comp.politica_composicion(perfil)

    mapa = comp.mapa_detalle(imagen)
    negativo = comp.espacio_negativo(mapa)
    separacion = comp.separacion_sujeto_fondo(imagen, mapa,
                                              minimo=pol_comp.separacion_sujeto_minima)
    metricas = col.metricas_imagen(imagen)

    # Aire donde poner el texto. Se premia llegar al minimo del perfil; pasarse
    # mucho tampoco suma: una foto vacia no tiene sujeto.
    aire = min(1.0, negativo / max(0.05, pol_comp.espacio_negativo_minimo))
    if negativo > 0.85:
        aire *= 0.6

    sujeto = min(1.0, separacion.puntaje / max(0.05, pol_comp.separacion_sujeto_minima))

    # Color: cuanto se acerca a lo que el skin pide, no cuanto "gusta".
    d_sat = abs(metricas.saturacion_media - min(pol_col.saturacion_maxima,
                                          max(pol_col.saturacion_minima,
                                              metricas.saturacion_media)))
    sat = 1.0 - min(1.0, d_sat / 0.4)
    d_cal = abs(metricas.calidez - pol_col.calidez_objetivo)
    calidez = 1.0 - min(1.0, d_cal / max(0.1, pol_col.calidez_tolerancia))
    d_lum = abs(metricas.luminancia_media - pol_col.luminancia_objetivo)
    luz = 1.0 - min(1.0, d_lum / max(0.05, pol_col.luminancia_tolerancia))

    resolucion = min(1.0, (imagen.width * imagen.height) / float(MIN_ANCHO * MIN_ALTO))

    componentes = {"aire": aire, "sujeto": sujeto, "saturacion": sat,
                   "calidez": calidez, "luminancia": luz, "resolucion": resolucion}
    pesos = {"aire": 0.26, "sujeto": 0.26, "saturacion": 0.12,
             "calidez": 0.12, "luminancia": 0.12, "resolucion": 0.12}
    puntaje = sum(pesos[k] * componentes[k] for k in pesos)
    return puntaje, {k: round(v, 3) for k, v in componentes.items()}


# --- entrada publica ---------------------------------------------------------
def resolver(concepto: dict, perfil: Perfil, cache: Cache,
             examinar: int = 5) -> tuple:
    """Busca, puntua y devuelve (imagen, candidato_elegido, [descartados]).

    `examinar` acota cuantas imagenes se bajan de verdad: puntuar exige
    tenerlas, y bajar doce para usar una es maltratar a la fuente.
    """
    exige_licencia = bool(perfil.get("personas_reales.solo_licencia_verificada"))
    candidatos, consulta = buscar(concepto, cache)
    if not candidatos:
        raise ErrorFuente(
            f"Ninguna fuente devolvio material para el concepto "
            f"'{concepto.get('id')}'. Consultas probadas: "
            f"{', '.join(_consultas(concepto)) or '(ninguna)'}. "
            f"Pasale una imagen con --imagen, o agregale al concepto un campo "
            f"'consulta_archivo' con terminos mas comunes (las fuentes indexan "
            f"sobre todo en ingles).")

    evaluados, descartados = [], []
    for candidato in candidatos[:examinar]:
        if exige_licencia and not candidato.verificada:
            candidato.descartado_por = (
                "el perfil exige licencia verificada y esta no trae licencia "
                "y pagina de origen comprobables")
            descartados.append(candidato)
            continue
        try:
            datos = descargar(candidato, cache)
            import io
            imagen = Image.open(io.BytesIO(datos)).convert("RGB")
        except Exception as exc:  # noqa: BLE001 - un candidato malo no corta la busqueda
            candidato.descartado_por = f"no se pudo abrir: {exc}"
            descartados.append(candidato)
            continue
        candidato.puntaje, candidato.componentes = puntuar(imagen, perfil)
        candidato.ancho, candidato.alto = imagen.size
        evaluados.append((candidato, imagen))

    if not evaluados:
        raise ErrorFuente(
            f"Se encontraron {len(candidatos)} imagenes para '{consulta}' pero "
            f"ninguna quedo utilizable:\n  - " +
            "\n  - ".join(f"{c.titulo or c.url}: {c.descartado_por}"
                          for c in descartados[:5]))

    evaluados.sort(key=lambda par: par[0].puntaje, reverse=True)
    elegido, imagen = evaluados[0]
    perdedores = [c for c, _ in evaluados[1:]] + descartados
    return imagen, elegido, perdedores
