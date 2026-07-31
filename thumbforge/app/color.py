"""Colorimetria generica.

Conversiones de espacio de color, contraste WCAG, diferencia de color,
lectura de paletas y metricas de imagen. Nada de lo que hay aca sabe a que
canal pertenece la miniatura: los umbrales entran por parametro y quien los
fija es el skin del perfil.

Toda la matematica va a mano con `math` y con las primitivas de Pillow. No
hay ni puede haber numpy: la imagen tiene que quedar por debajo de 600 MB y
correr en amd64 y arm64 sin GPU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from PIL import Image

Color = Any          # "#rrggbb" | (r, g, b) | (r, g, b, a)

# Iluminante D65, observador 2 grados. Es el blanco de sRGB.
BLANCO_D65 = (0.95047, 1.00000, 1.08883)

# Matriz sRGB lineal -> XYZ (D65) y su inversa, con los coeficientes de la
# especificacion IEC 61966-2-1.
_M_RGB_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_M_XYZ_RGB = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.9692660, 1.8760108, 0.0415560),
    (0.0556434, -0.2040259, 1.0572252),
)

# Defectos del proyecto. Son puntos de partida, no constantes de diseno: el
# perfil los pisa siempre que declare el bloque `colorimetria`.
CONTRASTE_MINIMO = 4.5
DELTA_E_MINIMO_VARIANTES = 12.0
SATURACION_MAXIMA = 0.85
CALIDEZ_OBJETIVO = 0.0
CALIDEZ_TOLERANCIA = 0.60

ESQUEMAS_ARMONIA: dict[str, tuple[float, ...]] = {
    # Del mas restrictivo al mas permisivo: en empate gana el primero.
    "monocromatico": (0.0,),
    "analogo": (0.0, 30.0, -30.0),
    "complementario": (0.0, 180.0),
    "split_complementario": (0.0, 150.0, 210.0),
    "triada": (0.0, 120.0, 240.0),
    "cuadrado": (0.0, 90.0, 180.0, 270.0),
}


# --- parseo y normalizacion --------------------------------------------------
def parsear_hex(texto: str) -> tuple:
    """'#rgb', '#rrggbb' o '#rrggbbaa' -> (r, g, b). El alfa se descarta."""
    s = str(texto).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    elif len(s) == 8:
        s = s[:6]
    if len(s) != 6:
        raise ValueError(f"color hex invalido: {texto!r}")
    try:
        valor = int(s, 16)
    except ValueError:
        raise ValueError(f"color hex invalido: {texto!r}") from None
    return ((valor >> 16) & 255, (valor >> 8) & 255, valor & 255)


def a_rgb(color: Color) -> tuple:
    """Acepta hex o tupla y devuelve (r, g, b) enteros recortados a 0..255."""
    if isinstance(color, str):
        return parsear_hex(color)
    try:
        r, g, b = (list(color) + [0, 0, 0])[:3]
    except TypeError:
        raise ValueError(f"no es un color: {color!r}") from None
    return tuple(max(0, min(255, int(round(float(c))))) for c in (r, g, b))


def a_hex(color: Color) -> str:
    r, g, b = a_rgb(color)
    return f"#{r:02x}{g:02x}{b:02x}"


# --- sRGB <-> lineal <-> XYZ <-> CIELAB --------------------------------------
def canal_a_lineal(c: float) -> float:
    """Quita la curva de transferencia de sRGB. Entrada y salida en 0..1."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def canal_a_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_a_lineal(color: Color) -> tuple:
    r, g, b = a_rgb(color)
    return tuple(canal_a_lineal(c / 255.0) for c in (r, g, b))


def lineal_a_rgb(lineal: Sequence[float]) -> tuple:
    return tuple(
        max(0, min(255, int(round(canal_a_srgb(max(0.0, min(1.0, c))) * 255))))
        for c in lineal
    )


def rgb_a_xyz(color: Color) -> tuple:
    lin = rgb_a_lineal(color)
    return tuple(sum(m[i] * lin[i] for i in range(3)) for m in _M_RGB_XYZ)


def xyz_a_rgb(xyz: Sequence[float]) -> tuple:
    lin = [sum(m[i] * xyz[i] for i in range(3)) for m in _M_XYZ_RGB]
    return lineal_a_rgb(lin)


def _f_lab(t: float) -> float:
    delta = 6.0 / 29.0
    return t ** (1.0 / 3.0) if t > delta ** 3 else t / (3 * delta ** 2) + 4.0 / 29.0


def _f_lab_inversa(t: float) -> float:
    delta = 6.0 / 29.0
    return t ** 3 if t > delta else 3 * delta ** 2 * (t - 4.0 / 29.0)


def xyz_a_lab(xyz: Sequence[float], blanco: Sequence[float] = BLANCO_D65) -> tuple:
    fx, fy, fz = (_f_lab(xyz[i] / blanco[i]) for i in range(3))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lab_a_xyz(lab: Sequence[float], blanco: Sequence[float] = BLANCO_D65) -> tuple:
    L, a, b = lab
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200
    return tuple(blanco[i] * _f_lab_inversa(f) for i, f in enumerate((fx, fy, fz)))


def rgb_a_lab(color: Color) -> tuple:
    return xyz_a_lab(rgb_a_xyz(color))


def lab_a_rgb(lab: Sequence[float]) -> tuple:
    return xyz_a_rgb(lab_a_xyz(lab))


# --- HSL y HSV ---------------------------------------------------------------
def rgb_a_hsl(color: Color) -> tuple:
    """(matiz 0..360, saturacion 0..1, luminosidad 0..1)."""
    r, g, b = (c / 255.0 for c in a_rgb(color))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return (0.0, 0.0, l)
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return (h * 60.0, s, l)


def hsl_a_rgb(h: float, s: float, l: float) -> tuple:
    h = h % 360.0
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = l - c / 2
    sector = int(h // 60) % 6
    rgb = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))[sector]
    return tuple(max(0, min(255, int(round((v + m) * 255)))) for v in rgb)


def rgb_a_hsv(color: Color) -> tuple:
    """(matiz 0..360, saturacion 0..1, valor 0..1)."""
    r, g, b = (c / 255.0 for c in a_rgb(color))
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = (((g - b) / d) % 6) * 60
    elif mx == g:
        h = ((b - r) / d + 2) * 60
    else:
        h = ((r - g) / d + 4) * 60
    return (h, 0.0 if mx == 0 else d / mx, mx)


def hsv_a_rgb(h: float, s: float, v: float) -> tuple:
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    sector = int(h // 60) % 6
    rgb = ((c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x))[sector]
    return tuple(max(0, min(255, int(round((val + m) * 255)))) for val in rgb)


# --- contraste WCAG 2.x ------------------------------------------------------
def luminancia_relativa(color: Color) -> float:
    r, g, b = rgb_a_lineal(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def razon_contraste(color_a: Color, color_b: Color) -> float:
    """Razon WCAG 2.x. Blanco contra negro da exactamente 21.0."""
    la, lb = luminancia_relativa(color_a), luminancia_relativa(color_b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def cumple_contraste(color_a: Color, color_b: Color,
                     minimo: float = CONTRASTE_MINIMO) -> bool:
    return razon_contraste(color_a, color_b) >= minimo


# --- diferencia de color -----------------------------------------------------
def delta_e_76(lab1: Sequence[float], lab2: Sequence[float]) -> float:
    """CIE76: distancia euclidea en Lab. Rapida y grosera."""
    return math.sqrt(sum((lab1[i] - lab2[i]) ** 2 for i in range(3)))


def delta_e_2000(lab1: Sequence[float], lab2: Sequence[float],
                 kl: float = 1.0, kc: float = 1.0, kh: float = 1.0) -> float:
    """CIEDE2000 completa, con el termino de rotacion de tono.

    Es la que decide si dos variantes se parecen demasiado: CIE76 miente
    justo en la zona azul, que es donde caen la mitad de los fondos.
    """
    L1, a1, b1 = (float(v) for v in lab1)
    L2, a2, b2 = (float(v) for v in lab2)

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    C_medio = (C1 + C2) / 2.0
    c7 = C_medio ** 7
    G = 0.5 * (1 - math.sqrt(c7 / (c7 + 25.0 ** 7)))

    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def _matiz(a: float, b: float) -> float:
        if a == 0 and b == 0:
            return 0.0
        return math.degrees(math.atan2(b, a)) % 360.0

    h1p, h2p = _matiz(a1p, b1), _matiz(a2p, b2)

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)

    Lp_medio = (L1 + L2) / 2.0
    Cp_medio = (C1p + C2p) / 2.0

    if C1p * C2p == 0:
        hp_medio = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_medio = (h1p + h2p) / 2.0
    elif h1p + h2p < 360:
        hp_medio = (h1p + h2p + 360) / 2.0
    else:
        hp_medio = (h1p + h2p - 360) / 2.0

    T = (1
         - 0.17 * math.cos(math.radians(hp_medio - 30))
         + 0.24 * math.cos(math.radians(2 * hp_medio))
         + 0.32 * math.cos(math.radians(3 * hp_medio + 6))
         - 0.20 * math.cos(math.radians(4 * hp_medio - 63)))

    d_theta = 30 * math.exp(-(((hp_medio - 275) / 25.0) ** 2))
    cp7 = Cp_medio ** 7
    R_C = 2 * math.sqrt(cp7 / (cp7 + 25.0 ** 7))
    R_T = -math.sin(math.radians(2 * d_theta)) * R_C

    S_L = 1 + (0.015 * (Lp_medio - 50) ** 2) / math.sqrt(20 + (Lp_medio - 50) ** 2)
    S_C = 1 + 0.045 * Cp_medio
    S_H = 1 + 0.015 * Cp_medio * T

    tL = dLp / (kl * S_L)
    tC = dCp / (kc * S_C)
    tH = dHp / (kh * S_H)
    return math.sqrt(tL * tL + tC * tC + tH * tH + R_T * tC * tH)


def delta_e(color_a: Color, color_b: Color, metodo: str = "ciede2000") -> float:
    """Diferencia entre dos colores dados en hex o RGB."""
    lab1, lab2 = rgb_a_lab(color_a), rgb_a_lab(color_b)
    if metodo in ("cie76", "76"):
        return delta_e_76(lab1, lab2)
    return delta_e_2000(lab1, lab2)


# --- paleta ------------------------------------------------------------------
def datos_planos(imagen: Image.Image) -> list:
    """Pixeles de la imagen como lista.

    `getdata()` quedo deprecada en Pillow 12 y desaparece en la 14; el
    fallback mantiene el modulo utilizable con versiones anteriores.
    """
    lector = getattr(imagen, "get_flattened_data", None)
    return list(lector() if lector is not None else imagen.getdata())


def reducir(imagen: Image.Image, lado_max: int) -> Image.Image:
    ancho, alto = imagen.size
    if max(ancho, alto) <= lado_max:
        return imagen
    escala = lado_max / float(max(ancho, alto))
    nuevo = (max(1, int(ancho * escala)), max(1, int(alto * escala)))
    return imagen.resize(nuevo, Image.BILINEAR)


def paleta_dominante(imagen: Image.Image, maximo: int = 6,
                     peso_minimo: float = 0.02, delta_fusion: float = 8.0,
                     muestreo: int = 160) -> list:
    """Colores dominantes como [(hex, peso)], de mayor a menor peso.

    Cuantiza con Pillow sobre una copia reducida, descarta los cubos que no
    llegan a `peso_minimo` (ruido de compresion y bordes antialiaseados) y
    funde los que quedan a menos de `delta_fusion` de CIEDE2000, porque dos
    entradas indistinguibles a ojo no son dos colores de la paleta.
    """
    if maximo < 1:
        return []
    chica = reducir(imagen, muestreo)
    alfa = chica.getchannel("A") if "A" in chica.getbands() else None
    rgb = chica.convert("RGB")

    # Se pide de mas para poder fusionar despues sin quedarse corto.
    cubos = max(2, min(256, maximo * 4))
    cuantizada = rgb.quantize(colors=cubos, method=Image.Quantize.MEDIANCUT)
    tabla = cuantizada.getpalette() or []
    indices = datos_planos(cuantizada)
    opacidad = datos_planos(alfa) if alfa is not None else None

    conteo: dict = {}
    total = 0
    for i, idx in enumerate(indices):
        if opacidad is not None and opacidad[i] < 128:
            continue
        conteo[idx] = conteo.get(idx, 0) + 1
        total += 1
    if not total:
        return []

    crudos = []
    for idx, n in conteo.items():
        base = idx * 3
        if base + 2 >= len(tabla):
            continue
        crudos.append((tuple(tabla[base:base + 3]), n / total))
    crudos.sort(key=lambda par: par[1], reverse=True)

    fundidos: list = []
    for color, peso in crudos:
        for i, (otro, peso_otro) in enumerate(fundidos):
            if delta_e_2000(rgb_a_lab(otro), rgb_a_lab(color)) < delta_fusion:
                # El dominante manda el color; el peso se acumula.
                fundidos[i] = (otro, peso_otro + peso)
                break
        else:
            fundidos.append((color, peso))

    fundidos = [par for par in fundidos if par[1] >= peso_minimo] or fundidos[:1]
    fundidos.sort(key=lambda par: par[1], reverse=True)
    fundidos = fundidos[:maximo]
    suma = sum(p for _, p in fundidos) or 1.0
    return [(a_hex(c), p / suma) for c, p in fundidos]


def _pares_paleta(paleta: Iterable) -> list:
    """Normaliza una paleta a [(hex, peso)] tolerando listas de colores."""
    salida = []
    for entrada in paleta or []:
        if isinstance(entrada, (tuple, list)) and len(entrada) == 2 and \
                isinstance(entrada[1], (int, float)) and not isinstance(entrada[0], (int, float)):
            salida.append((a_hex(entrada[0]), float(entrada[1])))
        else:
            salida.append((a_hex(entrada), 1.0))
    total = sum(p for _, p in salida)
    if total <= 0:
        return [(c, 1.0 / len(salida)) for c, _ in salida] if salida else []
    return [(c, p / total) for c, p in salida]


# --- metricas de imagen ------------------------------------------------------
@dataclass
class MetricasImagen:
    saturacion_media: float      # 0..1
    luminancia_media: float      # 0..1, luminancia relativa WCAG
    contraste_interno: float     # desvio de la luminancia, 0..1
    calidez: float               # -1 frio .. +1 calido
    kelvin: float                # temperatura correlacionada del color medio
    dispersion_cromatica: float  # 0 monocroma .. 1 matices repartidos

    @property
    def temperatura(self) -> str:
        if self.calidez > 0.15:
            return "calido"
        return "frio" if self.calidez < -0.15 else "neutra"


def _muestras(imagen: Image.Image, lado_max: int = 128) -> list:
    return datos_planos(reducir(imagen.convert("RGB"), lado_max))


def saturacion_media(imagen: Image.Image, lado_max: int = 128) -> float:
    px = _muestras(imagen, lado_max)
    if not px:
        return 0.0
    return sum(rgb_a_hsv(p)[1] for p in px) / len(px)


def luminancia_media(imagen: Image.Image, lado_max: int = 128) -> float:
    px = _muestras(imagen, lado_max)
    if not px:
        return 0.0
    return sum(luminancia_relativa(p) for p in px) / len(px)


def calidez(imagen: Image.Image, lado_max: int = 128) -> float:
    """-1 (frio) .. +1 (calido), ponderado por saturacion.

    Los grises no votan: una foto desaturada no es ni calida ni fria, y si
    se los contara arrastrarian el indice a cero por peso muerto.
    """
    px = _muestras(imagen, lado_max)
    if not px:
        return 0.0
    acumulado = 0.0
    peso = 0.0
    for p in px:
        h, s, v = rgb_a_hsv(p)
        w = s * v
        if w <= 0.02:
            continue
        # Coseno centrado en 45 grados (naranja) contra 225 (azul cielo).
        acumulado += w * math.cos(math.radians(h - 45))
        peso += w
    return acumulado / peso if peso else 0.0


def temperatura_kelvin(color_o_imagen) -> float:
    """Temperatura correlacionada (McCamy) del color medio, en kelvin.

    Se satura fuera de 1667..25000 K: la aproximacion deja de tener sentido
    lejos del lugar de Planck y no conviene reportar un numero inventado.
    """
    if isinstance(color_o_imagen, Image.Image):
        px = _muestras(color_o_imagen)
        if not px:
            return 6500.0
        n = len(px)
        medio = tuple(sum(p[i] for p in px) / n for i in range(3))
    else:
        medio = a_rgb(color_o_imagen)
    X, Y, Z = rgb_a_xyz(medio)
    suma = X + Y + Z
    if suma <= 0:
        return 6500.0
    x, y = X / suma, Y / suma
    if abs(0.1858 - y) < 1e-9:
        return 6500.0
    n = (x - 0.3320) / (0.1858 - y)
    cct = 449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33
    return max(1667.0, min(25000.0, cct))


def dispersion_cromatica(imagen: Image.Image, lado_max: int = 128) -> float:
    """Varianza circular del matiz, ponderada por saturacion. 0..1.

    Cerca de 0 la imagen gira sobre un solo matiz; cerca de 1 los matices
    estan repartidos y ninguna armonia va a dar bien.
    """
    px = _muestras(imagen, lado_max)
    sx = sy = peso = 0.0
    for p in px:
        h, s, v = rgb_a_hsv(p)
        w = s * v
        if w <= 0.02:
            continue
        rad = math.radians(h)
        sx += w * math.cos(rad)
        sy += w * math.sin(rad)
        peso += w
    if peso <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - math.hypot(sx, sy) / peso))


def metricas_imagen(imagen: Image.Image, lado_max: int = 128) -> MetricasImagen:
    px = _muestras(imagen, lado_max)
    if not px:
        return MetricasImagen(0.0, 0.0, 0.0, 0.0, 6500.0, 0.0)
    lum = [luminancia_relativa(p) for p in px]
    media = sum(lum) / len(lum)
    varianza = sum((v - media) ** 2 for v in lum) / len(lum)
    return MetricasImagen(
        saturacion_media=sum(rgb_a_hsv(p)[1] for p in px) / len(px),
        luminancia_media=media,
        contraste_interno=min(1.0, math.sqrt(varianza) * 2),
        calidez=calidez(imagen, lado_max),
        kelvin=temperatura_kelvin(imagen),
        dispersion_cromatica=dispersion_cromatica(imagen, lado_max),
    )


# --- armonias ----------------------------------------------------------------
def _girar(color: Color, grados: float) -> str:
    h, s, l = rgb_a_hsl(color)
    return a_hex(hsl_a_rgb(h + grados, s, l))


def complementario(color: Color) -> str:
    return _girar(color, 180)


def analogos(color: Color, separacion: float = 30.0) -> list:
    return [_girar(color, -separacion), _girar(color, separacion)]


def triada(color: Color) -> list:
    return [_girar(color, 120), _girar(color, 240)]


def split_complementario(color: Color, separacion: float = 30.0) -> list:
    return [_girar(color, 180 - separacion), _girar(color, 180 + separacion)]


def generar_armonia(base: Color, esquema: str = "complementario",
                    separacion: float = 30.0) -> list:
    """Paleta de la armonia pedida, con el color base primero."""
    clave = str(esquema).strip().lower()
    if clave not in ESQUEMAS_ARMONIA:
        raise ValueError(
            f"esquema de armonia desconocido: {esquema!r}; "
            f"validos: {', '.join(ESQUEMAS_ARMONIA)}")
    if clave == "analogo":
        return [a_hex(base)] + analogos(base, separacion)
    if clave == "split_complementario":
        return [a_hex(base)] + split_complementario(base, separacion)
    if clave == "monocromatico":
        h, s, l = rgb_a_hsl(base)
        return [a_hex(base),
                a_hex(hsl_a_rgb(h, s, max(0.06, l * 0.55))),
                a_hex(hsl_a_rgb(h, s, min(0.94, l + (1 - l) * 0.45)))]
    return [a_hex(base)] + [_girar(base, g) for g in ESQUEMAS_ARMONIA[clave][1:]]


def _cromaticos(paleta, saturacion_minima: float) -> list:
    """[(matiz, peso)] de los colores que efectivamente tienen matiz."""
    salida = []
    for color, peso in _pares_paleta(paleta):
        h, s, l = rgb_a_hsl(color)
        if s >= saturacion_minima and 0.04 < l < 0.96:
            salida.append((h, peso))
    return salida


def _distancia_angular(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def ajuste_armonia(paleta, esquema: str, tolerancia: float = 22.0,
                   saturacion_minima: float = 0.12) -> float:
    """Que tan bien encaja una paleta en un esquema de armonia. 0..1.

    Los neutros no cuentan: un gris no contradice ninguna armonia. Si la
    paleta entera es neutra el ajuste es 1.0, que es la lectura honesta —
    no hay evidencia en contra.
    """
    clave = str(esquema).strip().lower()
    if clave not in ESQUEMAS_ARMONIA:
        raise ValueError(f"esquema de armonia desconocido: {esquema!r}")
    matices = _cromaticos(paleta, saturacion_minima)
    if len(matices) <= 1:
        return 1.0
    offsets = ESQUEMAS_ARMONIA[clave]
    total = sum(p for _, p in matices) or 1.0
    mejor = 0.0
    for base, _ in matices:
        acumulado = 0.0
        for h, peso in matices:
            objetivos = [base + o for o in offsets]
            d = min(_distancia_angular(h, o) for o in objetivos)
            acumulado += peso * max(0.0, 1.0 - d / tolerancia)
        mejor = max(mejor, acumulado / total)
    return max(0.0, min(1.0, mejor))


def clasificar_armonia(paleta, tolerancia: float = 22.0,
                       saturacion_minima: float = 0.12) -> tuple:
    """(esquema que mejor encaja, ajuste 0..1). En empate gana el mas estricto."""
    mejor_nombre = "monocromatico"
    mejor_valor = -1.0
    for nombre in ESQUEMAS_ARMONIA:
        valor = ajuste_armonia(paleta, nombre, tolerancia, saturacion_minima)
        if valor > mejor_valor + 1e-9:
            mejor_nombre, mejor_valor = nombre, valor
    return (mejor_nombre, mejor_valor)


# --- contraste contra un fondo real ------------------------------------------
@dataclass
class InformeContraste:
    """Contraste de un color contra un fondo que no es uniforme."""

    promedio: float
    peor: float
    percentil_5: float
    fraccion_ok: float     # porcion de la region que llega al minimo
    minimo: float
    muestras: int

    @property
    def cumple(self) -> bool:
        return self.peor >= self.minimo

    def resumen(self) -> str:
        return (f"contraste promedio {self.promedio:.2f}:1, peor caso "
                f"{self.peor:.2f}:1, {self.fraccion_ok * 100:.0f}% de la region "
                f"llega a {self.minimo:.1f}:1")


def _muestras_fondo(fondo, mascara: Image.Image | None = None,
                    maximo: int = 20000) -> list:
    """Pixeles representativos del fondo, SIN promediar.

    Reduce con NEAREST a proposito: promediar es justamente la mentira que
    este modulo existe para evitar. Un texto blanco sobre un fondo mitad
    negro mitad blanco promedia gris y aprueba un contraste que no existe.
    """
    if isinstance(fondo, Image.Image):
        img = fondo.convert("RGB")
        if mascara is not None:
            msk = mascara.convert("L")
            if msk.size != img.size:
                msk = msk.resize(img.size, Image.NEAREST)
        else:
            msk = None
        ancho, alto = img.size
        pixeles = ancho * alto
        if pixeles > maximo:
            escala = math.sqrt(maximo / float(pixeles))
            destino = (max(1, int(ancho * escala)), max(1, int(alto * escala)))
            img = img.resize(destino, Image.NEAREST)
            if msk is not None:
                msk = msk.resize(destino, Image.NEAREST)
        datos = datos_planos(img)
        if msk is None:
            return datos
        alfa = datos_planos(msk)
        return [p for p, a in zip(datos, alfa) if a >= 128]
    return [a_rgb(fondo)]


def contraste_sobre_fondo(color_texto: Color, fondo, mascara: Image.Image | None = None,
                          minimo: float = CONTRASTE_MINIMO) -> InformeContraste:
    """Contraste de `color_texto` contra cada pixel del fondo bajo la mascara.

    `mascara` es una imagen L donde >=128 marca los pixeles que el texto va
    a ocupar. Sin mascara se evalua el fondo entero.
    """
    px = _muestras_fondo(fondo, mascara)
    if not px:
        return InformeContraste(0.0, 0.0, 0.0, 0.0, minimo, 0)
    valores = sorted(razon_contraste(color_texto, p) for p in px)
    n = len(valores)
    idx = max(0, min(n - 1, int(0.05 * n)))
    ok = sum(1 for v in valores if v >= minimo)
    return InformeContraste(
        promedio=sum(valores) / n,
        peor=valores[0],
        percentil_5=valores[idx],
        fraccion_ok=ok / n,
        minimo=minimo,
        muestras=n,
    )


# --- eleccion del color de texto ---------------------------------------------
@dataclass
class DecisionTexto:
    color: str
    informe: InformeContraste
    necesita_contorno: bool
    necesita_placa: bool
    color_refuerzo: str
    contraste_refuerzo: float
    motivo: str
    descartados: list = field(default_factory=list)

    @property
    def cumple(self) -> bool:
        """Si el refuerzo resuelve, el conjunto cumple aunque el color solo no."""
        if self.informe.cumple:
            return True
        if self.necesita_contorno or self.necesita_placa:
            return self.contraste_refuerzo >= self.informe.minimo
        return False


def elegir_color_texto(fondo, candidatos: Sequence[Color],
                       minimo: float = CONTRASTE_MINIMO,
                       refuerzos: Sequence[Color] = ("#000000", "#ffffff"),
                       mascara: Image.Image | None = None,
                       fraccion_para_contorno: float = 0.65) -> DecisionTexto:
    """Elige el color de texto que mas contrasta y decide el refuerzo.

    Ordena por porcion de fondo que llega al minimo, despues por peor caso y
    despues por promedio: un color que gana en promedio pero se hunde en un
    cuarto de la caja es peor que uno parejo.

    El refuerzo se decide por cuanto fondo falla, no por cuanto falla: si el
    color aguanta en casi toda la caja, un contorno tapa los huecos; si se
    cae en media caja, hace falta placa.
    """
    if not candidatos:
        raise ValueError("elegir_color_texto necesita al menos un candidato")

    evaluados = []
    for candidato in candidatos:
        informe = contraste_sobre_fondo(candidato, fondo, mascara, minimo)
        evaluados.append((a_hex(candidato), informe))
    evaluados.sort(
        key=lambda par: (par[1].fraccion_ok, par[1].peor, par[1].promedio),
        reverse=True)

    color, informe = evaluados[0]
    descartados = [
        {"color": c, "peor": round(i.peor, 3), "fraccion_ok": round(i.fraccion_ok, 3)}
        for c, i in evaluados[1:]
    ]

    mejor_refuerzo = ""
    contraste_refuerzo = 0.0
    for refuerzo in refuerzos or ():
        valor = razon_contraste(color, refuerzo)
        if valor > contraste_refuerzo:
            mejor_refuerzo, contraste_refuerzo = a_hex(refuerzo), valor

    if informe.cumple:
        return DecisionTexto(
            color, informe, False, False, mejor_refuerzo, contraste_refuerzo,
            f"{color} llega a {informe.peor:.2f}:1 en el peor pixel del fondo, "
            f"por encima del minimo {minimo:.1f}:1; no hace falta refuerzo.",
            descartados)

    if informe.fraccion_ok >= fraccion_para_contorno:
        return DecisionTexto(
            color, informe, True, False, mejor_refuerzo, contraste_refuerzo,
            f"{color} cumple en el {informe.fraccion_ok * 100:.0f}% del fondo y cae a "
            f"{informe.peor:.2f}:1 en el resto; un contorno {mejor_refuerzo} "
            f"({contraste_refuerzo:.2f}:1 contra el texto) cierra los huecos.",
            descartados)

    return DecisionTexto(
        color, informe, False, True, mejor_refuerzo, contraste_refuerzo,
        f"{color} solo cumple en el {informe.fraccion_ok * 100:.0f}% del fondo "
        f"(peor caso {informe.peor:.2f}:1); el fondo es demasiado disparejo para "
        f"un contorno, hace falta placa {mejor_refuerzo}.",
        descartados)


# --- distancia entre imagenes y entre variantes ------------------------------
def _reparto(valor: int, cubos: int) -> tuple:
    """Reparte un canal entre los dos cubos vecinos (interpolacion lineal).

    Con cubos duros, dos azules casi iguales pueden caer en cubos distintos y
    la distancia salta a 1: el reparto blando hace que la medida varie de a
    poco, que es lo que se espera al comparar variantes de una misma pieza.
    """
    p = valor * cubos / 256.0 - 0.5
    base = math.floor(p)
    frac = p - base
    i0 = min(cubos - 1, max(0, base))
    i1 = min(cubos - 1, max(0, base + 1))
    return ((i0, 1.0 - frac), (i1, frac))


def histograma_rgb(imagen: Image.Image, cubos: int = 8, lado_max: int = 96) -> list:
    """Histograma 3D de RGB normalizado a suma 1, en `cubos` por canal."""
    px = _muestras(imagen, lado_max)
    total = len(px)
    tabla = [0.0] * (cubos ** 3)
    if not total:
        return tabla
    cache: dict = {}
    for r, g, b in px:
        for canal, valor in ((0, r), (1, g), (2, b)):
            if (canal, valor) not in cache:
                cache[(canal, valor)] = _reparto(valor, cubos)
        for ir, wr in cache[(0, r)]:
            if wr <= 0:
                continue
            for ig, wg in cache[(1, g)]:
                if wg <= 0:
                    continue
                for ib, wb in cache[(2, b)]:
                    if wb <= 0:
                        continue
                    tabla[(ir * cubos + ig) * cubos + ib] += wr * wg * wb
    suma = sum(tabla) or 1.0
    return [v / suma for v in tabla]


def distancia_histograma(imagen_a: Image.Image, imagen_b: Image.Image,
                         metodo: str = "bhattacharyya", cubos: int = 8) -> float:
    """Distancia 0..1 entre dos imagenes. 0 identicas, 1 sin nada en comun."""
    ha = histograma_rgb(imagen_a, cubos)
    hb = histograma_rgb(imagen_b, cubos)
    if metodo in ("chi2", "chi_cuadrado"):
        acumulado = 0.0
        for p, q in zip(ha, hb):
            if p + q > 0:
                acumulado += (p - q) ** 2 / (p + q)
        return max(0.0, min(1.0, acumulado / 2.0))
    coeficiente = sum(math.sqrt(p * q) for p, q in zip(ha, hb))
    return max(0.0, min(1.0, math.sqrt(max(0.0, 1.0 - coeficiente))))


def delta_e_entre_paletas(paleta_a, paleta_b) -> float:
    """Distancia CIEDE2000 entre dos paletas, simetrica y ponderada.

    Para cada color de una paleta se toma el mas parecido de la otra: dos
    variantes se parecen si cada color de una tiene su gemelo en la otra.
    """
    pa, pb = _pares_paleta(paleta_a), _pares_paleta(paleta_b)
    if not pa or not pb:
        return 0.0
    labs_a = [(rgb_a_lab(c), p) for c, p in pa]
    labs_b = [(rgb_a_lab(c), p) for c, p in pb]

    def dirigida(origen, destino) -> float:
        total = sum(p for _, p in origen) or 1.0
        acumulado = 0.0
        for lab, peso in origen:
            acumulado += peso * min(delta_e_2000(lab, otro) for otro, _ in destino)
        return acumulado / total

    return (dirigida(labs_a, labs_b) + dirigida(labs_b, labs_a)) / 2.0


def separacion_de_variantes(paletas: Sequence, minimo: float = DELTA_E_MINIMO_VARIANTES) -> dict:
    """Separacion cromatica del lote de variantes.

    Devuelve el par mas parecido y si el lote llega al delta E pedido. M6 lo
    usa para rechazar tres miniaturas que son la misma miniatura.
    """
    pares = []
    for i in range(len(paletas)):
        for j in range(i + 1, len(paletas)):
            pares.append(((i, j), delta_e_entre_paletas(paletas[i], paletas[j])))
    if not pares:
        return {"minimo_observado": 0.0, "par_mas_parecido": None,
                "cumple": True, "minimo_exigido": minimo, "pares": []}
    peor = min(pares, key=lambda par: par[1])
    return {
        "minimo_observado": peor[1],
        "par_mas_parecido": peor[0],
        "cumple": peor[1] >= minimo,
        "minimo_exigido": minimo,
        "pares": [{"par": p, "delta_e": round(d, 3)} for p, d in pares],
    }


# --- lectura del skin --------------------------------------------------------
@dataclass
class PoliticaColor:
    """Bloque `colorimetria` del skin, ya resuelto con defectos.

    Un skin viejo que no declara el bloque tiene que seguir funcionando: por
    eso cada clave tiene un valor por defecto y ninguna es obligatoria.
    """

    contraste_minimo: float = CONTRASTE_MINIMO
    contraste_objetivo: float = 7.0
    armonia_preferida: str = "complementario"
    armonia_ajuste_minimo: float = 0.5
    calidez_objetivo: float = CALIDEZ_OBJETIVO
    calidez_tolerancia: float = CALIDEZ_TOLERANCIA
    saturacion_maxima: float = SATURACION_MAXIMA
    saturacion_minima: float = 0.0
    luminancia_objetivo: float = 0.35
    luminancia_tolerancia: float = 0.30
    delta_e_minimo_entre_variantes: float = DELTA_E_MINIMO_VARIANTES
    colores_texto: list = field(default_factory=list)
    colores_refuerzo: list = field(default_factory=lambda: ["#000000", "#ffffff"])
    refuerzo_preferido: str = "auto"
    max_colores_paleta: int = 6
    peso_minimo_paleta: float = 0.02


def politica_color(skin) -> PoliticaColor:
    """Lee `colorimetria` de un skin (dict o perfil) y completa lo que falte."""
    datos = getattr(skin, "skin", skin) or {}
    bloque = datos.get("colorimetria") or {}
    paleta = datos.get("paleta") or {}
    texto = datos.get("texto") or {}

    # Sin lista declarada, los candidatos salen de la paleta que el skin ya
    # tenia: agregar el bloque no puede ser obligatorio para renderizar.
    candidatos = bloque.get("colores_texto")
    if not candidatos:
        candidatos = [c for c in (texto.get("color"), paleta.get("texto"),
                                  paleta.get("acento")) if c]
    refuerzos = bloque.get("colores_refuerzo")
    if not refuerzos:
        contorno = (texto.get("contorno") or {}).get("color")
        placa = (datos.get("placa") or {}).get("color")
        refuerzos = [c for c in (contorno, placa, paleta.get("sombra"),
                                 "#000000", "#ffffff") if c]

    defecto = PoliticaColor()

    def hexes(valores):
        # Sin duplicados y en orden: la lista se recorre entera en cada
        # eleccion de color y repetir candidatos solo cuesta tiempo.
        salida = []
        for v in valores:
            h = a_hex(v)
            if h not in salida:
                salida.append(h)
        return salida

    def num(clave, base):
        valor = bloque.get(clave, base)
        try:
            return float(valor)
        except (TypeError, ValueError):
            return base

    return PoliticaColor(
        contraste_minimo=num("contraste_minimo", defecto.contraste_minimo),
        contraste_objetivo=num("contraste_objetivo", defecto.contraste_objetivo),
        armonia_preferida=str(bloque.get("armonia_preferida",
                                         defecto.armonia_preferida)).lower(),
        armonia_ajuste_minimo=num("armonia_ajuste_minimo", defecto.armonia_ajuste_minimo),
        calidez_objetivo=num("calidez_objetivo", defecto.calidez_objetivo),
        calidez_tolerancia=num("calidez_tolerancia", defecto.calidez_tolerancia),
        saturacion_maxima=num("saturacion_maxima", defecto.saturacion_maxima),
        saturacion_minima=num("saturacion_minima", defecto.saturacion_minima),
        luminancia_objetivo=num("luminancia_objetivo", defecto.luminancia_objetivo),
        luminancia_tolerancia=num("luminancia_tolerancia", defecto.luminancia_tolerancia),
        delta_e_minimo_entre_variantes=num("delta_e_minimo_entre_variantes",
                                           defecto.delta_e_minimo_entre_variantes),
        colores_texto=hexes(candidatos) or ["#ffffff", "#000000"],
        colores_refuerzo=hexes(refuerzos) or list(defecto.colores_refuerzo),
        refuerzo_preferido=str(bloque.get("refuerzo_preferido",
                                          defecto.refuerzo_preferido)).lower(),
        max_colores_paleta=int(num("max_colores_paleta", defecto.max_colores_paleta)),
        peso_minimo_paleta=num("peso_minimo_paleta", defecto.peso_minimo_paleta),
    )


def evaluar_colorimetria(imagen: Image.Image, politica: PoliticaColor | None = None) -> dict:
    """Contrasta una imagen contra la politica de color. Insumo directo de QA.

    Devuelve hallazgos, no un veredicto: quien decide que hacer con una
    saturacion alta es el paso siguiente, no este modulo.
    """
    pol = politica or PoliticaColor()
    metricas = metricas_imagen(imagen)
    paleta = paleta_dominante(imagen, maximo=pol.max_colores_paleta,
                              peso_minimo=pol.peso_minimo_paleta)
    ajuste = ajuste_armonia(paleta, pol.armonia_preferida) \
        if pol.armonia_preferida in ESQUEMAS_ARMONIA else 1.0
    detectada, ajuste_detectada = clasificar_armonia(paleta)

    hallazgos = []
    if metricas.saturacion_media > pol.saturacion_maxima:
        hallazgos.append(
            f"saturacion media {metricas.saturacion_media:.2f} sobre el maximo "
            f"{pol.saturacion_maxima:.2f}")
    if metricas.saturacion_media < pol.saturacion_minima:
        hallazgos.append(
            f"saturacion media {metricas.saturacion_media:.2f} bajo el minimo "
            f"{pol.saturacion_minima:.2f}")
    if abs(metricas.calidez - pol.calidez_objetivo) > pol.calidez_tolerancia:
        hallazgos.append(
            f"calidez {metricas.calidez:+.2f} lejos del objetivo "
            f"{pol.calidez_objetivo:+.2f} (tolerancia {pol.calidez_tolerancia:.2f})")
    if abs(metricas.luminancia_media - pol.luminancia_objetivo) > pol.luminancia_tolerancia:
        hallazgos.append(
            f"luminancia media {metricas.luminancia_media:.2f} lejos del objetivo "
            f"{pol.luminancia_objetivo:.2f}")
    if ajuste < pol.armonia_ajuste_minimo:
        hallazgos.append(
            f"la paleta encaja {ajuste:.2f} en '{pol.armonia_preferida}' "
            f"(minimo {pol.armonia_ajuste_minimo:.2f}); se parece mas a "
            f"'{detectada}' ({ajuste_detectada:.2f})")

    return {
        "paleta": paleta,
        "metricas": metricas,
        "armonia_preferida": pol.armonia_preferida,
        "ajuste_armonia": ajuste,
        "armonia_detectada": detectada,
        "ajuste_detectada": ajuste_detectada,
        "hallazgos": hallazgos,
        "ok": not hallazgos,
    }
