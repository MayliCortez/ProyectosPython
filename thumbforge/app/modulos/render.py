"""M5 - render.

Toma un concepto aprobado por M4, resuelve su base visual segun la politica
del perfil, normaliza el lienzo, aplica el skin y compone el texto con Pillow.

Lo que decide este modulo NO es estetica de nicho: es geometria, contraste y
legibilidad. Que color, que tipografia y donde va el texto sale del skin; que
material esta permitido sale de la politica. Aca solo se ejecuta.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import color as col
from .. import composicion as comp
from .. import politicas
from ..cache import Cache, huella
from ..errores import ErrorThumbforge
from ..perfiles import Perfil
from ..rutas import dir_salida

# YouTube rechaza miniaturas de mas de 2 MB.
LIMITE_BYTES = 2 * 1024 * 1024
CALIDADES = (95, 92, 88, 84, 80, 75, 70, 65, 60)
ANCHO_MINIMO = 1280
ALTO_MINIMO = 720


class ErrorRender(ErrorThumbforge):
    """No se pudo componer la miniatura."""


@dataclass
class Atribucion:
    """De donde salio una imagen. Va a salida/creditos.txt."""

    concepto_id: str
    origen: str
    descripcion: str = ""
    fuente: str = ""
    licencia: str = ""
    autor: str = ""
    url: str = ""

    def linea(self) -> str:
        partes = [f"[{self.concepto_id}] {self.origen}"]
        if self.descripcion:
            partes.append(f"  descripcion: {self.descripcion}")
        if self.fuente:
            partes.append(f"  fuente: {self.fuente}")
        if self.autor:
            partes.append(f"  autor: {self.autor}")
        if self.licencia:
            partes.append(f"  licencia: {self.licencia}")
        if self.url:
            partes.append(f"  url: {self.url}")
        return "\n".join(partes)


@dataclass
class BloqueTexto:
    lineas: list
    tamano: int
    ancho: int
    alto: int
    interlineado: float
    interletrado: float


@dataclass
class ResultadoRender:
    concepto_id: str
    ruta: Path
    bytes: int
    calidad: int
    caja_texto: comp.Caja
    decision_texto: col.DecisionTexto
    eleccion: comp.EleccionCaja
    bloque: BloqueTexto
    atribuciones: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    mascara_texto: Any = None
    imagen: Any = None


# --- utilidades de skin ------------------------------------------------------
def _fraccion(valor: Any, defecto: float) -> float:
    """Acepta 62 (por ciento) o 0.62 (fraccion). Los skins usan las dos."""
    if valor is None:
        return defecto
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    return v / 100.0 if v > 1.0 else v


def _rgba(color_hex: str, opacidad: float) -> tuple:
    r, g, b = col.a_rgb(color_hex)
    return (r, g, b, max(0, min(255, int(round(opacidad * 255)))))


# --- base visual -------------------------------------------------------------
def normalizar_lienzo(imagen: Image.Image, ancho: int, alto: int) -> Image.Image:
    """Lleva la base al lienzo del skin recortando por el centro.

    Se recorta en vez de deformar: un rostro estirado se nota, un recorte
    no. Si la base es mas chica que el minimo, se amplia y se avisa aparte.
    """
    imagen = imagen.convert("RGB")
    o_ancho, o_alto = imagen.size
    escala = max(ancho / o_ancho, alto / o_alto)
    nuevo = (max(1, int(round(o_ancho * escala))), max(1, int(round(o_alto * escala))))
    imagen = imagen.resize(nuevo, Image.LANCZOS)
    izq = (nuevo[0] - ancho) // 2
    sup = (nuevo[1] - alto) // 2
    return imagen.crop((izq, sup, izq + ancho, sup + alto))


def resolver_base(concepto: dict, perfil: Perfil, cache: Cache,
                  imagen_local: Path | None = None) -> tuple:
    """Devuelve (imagen, [atribuciones]) para la base visual del concepto.

    Con `imagen_local` no se toca la red: es el camino que usa el paso 3 del
    orden de construccion y el que corre en las pruebas.
    """
    base = concepto.get("base_visual") or {}
    origen = str(base.get("origen") or "")
    cid = str(concepto.get("id") or "sin-id")

    if imagen_local is not None:
        ruta = Path(imagen_local)
        if not ruta.is_file():
            raise ErrorRender(f"No existe la imagen base {ruta}")
        atr = Atribucion(cid, origen or "local", base.get("descripcion", ""),
                         fuente=str(ruta),
                         licencia=str(base.get("licencia") or "sin declarar"))
        return Image.open(ruta), [atr]

    # Sin imagen local hace falta una fuente externa. Se falla con un mensaje
    # que dice exactamente que falta, en vez de devolver un cuadro vacio.
    raise ErrorRender(
        f"El concepto '{cid}' pide una base de origen '{origen}' y no se paso "
        f"ninguna imagen local. La resolucion automatica de archivo y la "
        f"generacion por API todavia no estan cableadas: pasale una imagen con "
        f"--imagen o completa base_visual.archivo_local en el concepto."
    )


# --- texto -------------------------------------------------------------------
def _sin_tildes_mayusculas(texto: str) -> str:
    return texto.upper()


def _medir(fuente: ImageFont.FreeTypeFont, texto: str, interletrado: float) -> int:
    if not texto:
        return 0
    ancho = int(fuente.getlength(texto))
    # getlength no conoce el interletrado: se suma aparte, una vez por hueco.
    return ancho + int(round(interletrado * max(0, len(texto) - 1)))


def _partir(texto: str, fuente: ImageFont.FreeTypeFont, ancho_max: int,
            interletrado: float) -> list:
    """Corta en lineas por palabra. Una palabra sola mas ancha que la caja se
    deja larga: partirla al medio se lee peor que desbordar un poco."""
    lineas: list = []
    actual = ""
    for palabra in texto.split():
        tentativa = f"{actual} {palabra}".strip()
        if actual and _medir(fuente, tentativa, interletrado) > ancho_max:
            lineas.append(actual)
            actual = palabra
        else:
            actual = tentativa
    if actual:
        lineas.append(actual)
    return lineas or [""]


def ajustar_texto(texto: str, ruta_fuente: Path, ancho_max: int, alto_max: int,
                  tamano_max: int = 128, tamano_min: int = 48,
                  interlineado: float = 1.05, interletrado: float = 0.0,
                  mayusculas: bool = False) -> BloqueTexto:
    """Busca el cuerpo mas grande que entra en la caja disponible.

    Baja de a un punto desde `tamano_max`. Si ni el minimo entra, devuelve el
    minimo igual: que el texto desborde es visible y corregible; que el
    modulo falle deja al operador sin nada.
    """
    if mayusculas:
        texto = _sin_tildes_mayusculas(texto)

    mejor: BloqueTexto | None = None
    for tamano in range(int(tamano_max), int(tamano_min) - 1, -1):
        fuente = ImageFont.truetype(str(ruta_fuente), tamano)
        lineas = _partir(texto, fuente, ancho_max, interletrado)
        alto_linea = int(round(tamano * interlineado))
        alto_total = alto_linea * len(lineas)
        ancho_total = max((_medir(fuente, l, interletrado) for l in lineas), default=0)
        bloque = BloqueTexto(lineas, tamano, ancho_total, alto_total,
                             interlineado, interletrado)
        if ancho_total <= ancho_max and alto_total <= alto_max:
            return bloque
        mejor = bloque
    return mejor  # type: ignore[return-value]


def _dibujar_linea(lienzo: ImageDraw.ImageDraw, xy: tuple, texto: str,
                   fuente: ImageFont.FreeTypeFont, relleno, interletrado: float,
                   contorno: int = 0, color_contorno=None) -> None:
    """Dibuja con interletrado. Pillow no lo soporta, asi que si hay tracking
    se dibuja caracter por caracter."""
    x, y = xy
    if not interletrado:
        lienzo.text((x, y), texto, font=fuente, fill=relleno,
                    stroke_width=contorno, stroke_fill=color_contorno)
        return
    for ch in texto:
        lienzo.text((x, y), ch, font=fuente, fill=relleno,
                    stroke_width=contorno, stroke_fill=color_contorno)
        x += fuente.getlength(ch) + interletrado


# --- capas del skin ----------------------------------------------------------
def _aplicar_gradiente(imagen: Image.Image, skin: dict) -> None:
    cfg = skin.get("gradiente") or {}
    if not cfg.get("activo"):
        return
    ancho, alto = imagen.size
    color_hex = cfg.get("color", "#000000")
    opacidad = float(cfg.get("opacidad", 0.6))
    direccion = str(cfg.get("direccion", "abajo"))
    fraccion = _fraccion(cfg.get("alto_pct"), 0.6)

    capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    px = capa.load()
    r, g, b = col.a_rgb(color_hex)

    if direccion == "izquierda":
        largo = max(1, int(ancho * fraccion))
        for x in range(largo):
            a = int(round(opacidad * 255 * (1 - x / largo)))
            for y in range(alto):
                px[x, y] = (r, g, b, a)
    elif direccion == "radial_desde_bordes":
        cx, cy = ancho / 2.0, alto / 2.0
        maximo = (cx ** 2 + cy ** 2) ** 0.5
        paso = 4  # el vineteado no necesita resolucion de pixel
        for y in range(0, alto, paso):
            for x in range(0, ancho, paso):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / maximo
                a = int(round(opacidad * 255 * max(0.0, d - 0.35) / 0.65))
                for yy in range(y, min(y + paso, alto)):
                    for xx in range(x, min(x + paso, ancho)):
                        px[xx, yy] = (r, g, b, a)
    else:  # abajo
        largo = max(1, int(alto * fraccion))
        inicio = alto - largo
        for y in range(inicio, alto):
            a = int(round(opacidad * 255 * (y - inicio) / largo))
            for x in range(ancho):
                px[x, y] = (r, g, b, a)

    imagen.alpha_composite(capa)


def _aplicar_logo(imagen: Image.Image, perfil: Perfil, skin: dict,
                  zonas: dict, avisos: list) -> None:
    cfg = skin.get("logo") or {}
    archivo = cfg.get("archivo")
    if not archivo:
        return
    ruta = perfil.ruta(archivo)
    if not ruta.is_file():
        avisos.append(f"el logo declarado no existe: {ruta}")
        return

    ancho, alto = imagen.size
    logo = Image.open(ruta).convert("RGBA")
    destino = max(16, int(ancho * _fraccion(cfg.get("ancho_pct"), 0.12)))
    escala = destino / logo.width
    logo = logo.resize((destino, max(1, int(logo.height * escala))), Image.LANCZOS)

    opacidad = float(cfg.get("opacidad", 1.0))
    if opacidad < 1.0:
        alfa = logo.getchannel("A").point(lambda v: int(v * opacidad))
        logo.putalpha(alfa)

    margen = int(ancho * _fraccion(cfg.get("margen_pct"), 0.03))
    pos = str(cfg.get("posicion", "izq_sup"))
    x = margen if pos.startswith("izq") else ancho - logo.width - margen
    y = margen if pos.endswith("sup") else alto - logo.height - margen

    caja = comp.Caja(x, y, logo.width, logo.height)
    ok, invadidas = comp.respeta_zonas_seguras(caja, zonas)
    if not ok:
        avisos.append(
            f"el logo cae sobre {', '.join(invadidas)}; se subio para despejarlo")
        y = alto - logo.height - margen - max(z.alto for z in zonas.values())
        y = max(margen, y)

    imagen.alpha_composite(logo, (int(x), int(y)))


# --- composicion -------------------------------------------------------------
def componer(concepto: dict, perfil: Perfil, base: Image.Image,
             avisos: list | None = None) -> tuple:
    """Compone la miniatura. Devuelve (imagen RGBA, datos del layout)."""
    avisos = avisos if avisos is not None else []
    skin = perfil.skin
    ancho = int(perfil.get_skin("lienzo.ancho", ANCHO_MINIMO))
    alto = int(perfil.get_skin("lienzo.alto", ALTO_MINIMO))

    if base.width < ANCHO_MINIMO or base.height < ALTO_MINIMO:
        avisos.append(
            f"la base mide {base.width}x{base.height}, por debajo del minimo "
            f"{ANCHO_MINIMO}x{ALTO_MINIMO}: se amplio y va a verse blanda")

    imagen = normalizar_lienzo(base, ancho, alto).convert("RGBA")
    zonas = comp.zonas_seguras_de_skin(perfil, ancho, alto)
    pol_color = col.politica_color(perfil)
    pol_comp = comp.politica_composicion(perfil)

    _aplicar_gradiente(imagen, skin)

    # --- texto: primero cuanto mide, despues donde va -----------------------
    texto = str((concepto.get("copy") or {}).get("texto") or "")
    cfg_texto = skin.get("texto") or {}
    tipo = (skin.get("tipografia") or {}).get("titular") or {}
    ruta_fuente = perfil.fuente("titular")

    ancho_max = int(ancho * _fraccion(cfg_texto.get("ancho_max_pct"), 0.6))
    bloque = ajustar_texto(
        texto, ruta_fuente, ancho_max, int(alto * 0.55),
        tamano_max=int(tipo.get("tamano_max", 120)),
        tamano_min=int(tipo.get("tamano_min", 48)),
        interlineado=float(cfg_texto.get("interlineado", 1.05)),
        interletrado=float(tipo.get("interletrado", 0)),
        mayusculas=bool(tipo.get("mayusculas", False)))

    cfg_placa = skin.get("placa") or {}
    pad_x, pad_y = 0, 0
    if cfg_placa.get("activa"):
        padding = cfg_placa.get("padding") or [24, 18]
        pad_x, pad_y = int(padding[0]), int(padding[1])

    tam_caja = (bloque.ancho + pad_x * 2, bloque.alto + pad_y * 2)
    eleccion = comp.elegir_caja_texto(
        imagen.convert("RGB"), tam_caja,
        posicion_preferida=cfg_texto.get("posicion"),
        ancho_max_pct=cfg_texto.get("ancho_max_pct"),
        zonas=zonas,
        color_texto=(pol_color.colores_texto or [None])[0],
        contraste_minimo=pol_color.contraste_minimo,
        margen_pct=pol_comp.margen_pct,
        punto_focal=pol_comp.punto_focal_preferido,
        alinear_a_tercios=pol_comp.alinear_a_tercios,
        pesos=pol_comp.pesos or None)
    caja = eleccion.caja
    if eleccion.zonas_invadidas:
        avisos.append(
            f"el bloque de texto no pudo evitar {', '.join(eleccion.zonas_invadidas)}: "
            f"probá un copy mas corto o un cuerpo menor")

    # --- color del texto, medido sobre el fondo real que le toco ------------
    caja_texto = comp.Caja(caja.x + pad_x, caja.y + pad_y, bloque.ancho, bloque.alto)
    mascara = Image.new("L", (ancho, alto), 0)
    dm = ImageDraw.Draw(mascara)
    fuente = ImageFont.truetype(str(ruta_fuente), bloque.tamano)
    alto_linea = int(round(bloque.tamano * bloque.interlineado))
    for i, linea in enumerate(bloque.lineas):
        _dibujar_linea(dm, (caja_texto.x, caja_texto.y + i * alto_linea), linea,
                       fuente, 255, bloque.interletrado)

    decision = col.elegir_color_texto(
        imagen.convert("RGB"),
        pol_color.colores_texto or ["#ffffff", "#000000"],
        minimo=pol_color.contraste_minimo,
        refuerzos=pol_color.colores_refuerzo,
        mascara=mascara)

    # --- placa ---------------------------------------------------------------
    quiere_placa = bool(cfg_placa.get("activa")) or decision.necesita_placa
    if quiere_placa:
        capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
        ImageDraw.Draw(capa).rectangle(
            caja.caja_pil(),
            fill=_rgba(cfg_placa.get("color", decision.color_refuerzo),
                       float(cfg_placa.get("opacidad", 0.55))))
        imagen.alpha_composite(capa)

    # --- sombra --------------------------------------------------------------
    cfg_sombra = cfg_texto.get("sombra") or {}
    if cfg_sombra:
        dx, dy = (cfg_sombra.get("desplazamiento") or [4, 4])[:2]
        capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
        ds = ImageDraw.Draw(capa)
        for i, linea in enumerate(bloque.lineas):
            _dibujar_linea(ds, (caja_texto.x + int(dx),
                                caja_texto.y + i * alto_linea + int(dy)),
                           linea, fuente,
                           _rgba(skin.get("paleta", {}).get("sombra", "#000000"),
                                 float(cfg_sombra.get("opacidad", 0.55))),
                           bloque.interletrado)
        radio = float(cfg_sombra.get("desenfoque", 0))
        if radio:
            capa = capa.filter(ImageFilter.GaussianBlur(radio))
        imagen.alpha_composite(capa)

    # --- barra de acento -----------------------------------------------------
    cfg_barra = skin.get("barra_acento") or {}
    if cfg_barra.get("activa"):
        grosor = int(cfg_barra.get("grosor_px", 6))
        y = caja.y - grosor - 8 if cfg_barra.get("posicion") == "sobre_texto" \
            else caja.y2 + 8
        y = max(0, min(alto - grosor, y))
        capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
        ImageDraw.Draw(capa).rectangle(
            [caja_texto.x, y, caja_texto.x + min(bloque.ancho, int(ancho * 0.22)),
             y + grosor],
            fill=_rgba(cfg_barra.get("color", "#ffffff"), 1.0))
        imagen.alpha_composite(capa)

    # --- el texto ------------------------------------------------------------
    cfg_contorno = cfg_texto.get("contorno") or {}
    grosor = int(cfg_contorno.get("grosor", 0))
    if decision.necesita_contorno and grosor == 0:
        grosor = max(3, bloque.tamano // 20)
    color_contorno = cfg_contorno.get("color") or decision.color_refuerzo

    capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    dt = ImageDraw.Draw(capa)
    for i, linea in enumerate(bloque.lineas):
        _dibujar_linea(dt, (caja_texto.x, caja_texto.y + i * alto_linea), linea,
                       fuente, decision.color, bloque.interletrado,
                       contorno=grosor,
                       color_contorno=color_contorno if grosor else None)
    imagen.alpha_composite(capa)

    _aplicar_logo(imagen, perfil, skin, zonas, avisos)

    return imagen, {"caja": caja, "caja_texto": caja_texto, "bloque": bloque,
                    "eleccion": eleccion, "decision": decision,
                    "mascara": mascara, "zonas": zonas}


# --- guardado ----------------------------------------------------------------
def guardar_jpg(imagen: Image.Image, ruta: Path,
                limite: int = LIMITE_BYTES) -> tuple:
    """Guarda iterando la calidad hasta entrar en el limite. (bytes, calidad)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    rgb = imagen.convert("RGB")
    ultimo = 0
    for calidad in CALIDADES:
        rgb.save(ruta, "JPEG", quality=calidad, optimize=True, progressive=True)
        ultimo = ruta.stat().st_size
        if ultimo <= limite:
            return ultimo, calidad
    return ultimo, CALIDADES[-1]


def escribir_creditos(atribuciones: list, ruta: Path | None = None) -> Path:
    """salida/creditos.txt. Se reescribe entero en cada corrida."""
    ruta = ruta or (dir_salida() / "creditos.txt")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cabecera = [
        "Atribuciones de las imagenes usadas en esta corrida.",
        f"Generado el {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",
        "",
        "Revisa que cada licencia permita el uso antes de publicar: el motor",
        "registra lo que se le declaro, no verifica derechos.",
        "",
    ]
    cuerpo = [a.linea() for a in atribuciones] or ["(sin imagenes externas)"]
    ruta.write_text("\n".join(cabecera + cuerpo) + "\n", "utf-8")
    return ruta


# --- entrada publica ---------------------------------------------------------
def renderizar(concepto: dict, perfil: Perfil, cache: Cache,
               imagen_local: Path | None = None,
               salida: Path | None = None) -> ResultadoRender:
    """Concepto + perfil + base -> un JPG en salida/."""
    cid = str(concepto.get("id") or "sin-id")
    avisos: list = []

    # Ultima linea de defensa: si un concepto llego hasta aca con una
    # violacion dura, no se compone. M4 ya deberia haberlo frenado, pero el
    # render tambien puede invocarse solo.
    veredicto = politicas.evaluar_concepto(concepto, perfil)
    if not veredicto.ok:
        raise ErrorRender(
            f"El concepto '{cid}' viola la politica del perfil '{perfil.slug}' "
            f"y no se compone:\n{veredicto.informe()}")
    for pendiente in veredicto.diferidas:
        avisos.append(f"pendiente: {pendiente.mensaje}")

    base, atribuciones = resolver_base(concepto, perfil, cache, imagen_local)
    imagen, layout = componer(concepto, perfil, base, avisos)

    salida = salida or dir_salida()
    ruta = salida / f"{perfil.slug}_{cid}.jpg"
    bytes_, calidad = guardar_jpg(imagen, ruta)
    if calidad < CALIDADES[0]:
        avisos.append(f"se bajo la calidad JPG a {calidad} para entrar en 2 MB")

    return ResultadoRender(
        concepto_id=cid, ruta=ruta, bytes=bytes_, calidad=calidad,
        caja_texto=layout["caja_texto"], decision_texto=layout["decision"],
        eleccion=layout["eleccion"], bloque=layout["bloque"],
        atribuciones=atribuciones, avisos=avisos,
        mascara_texto=layout["mascara"], imagen=imagen.convert("RGB"))
