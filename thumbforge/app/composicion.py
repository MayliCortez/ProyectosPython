"""Encuadre, ocupacion y enfoque.

Geometria de la miniatura: rejilla de tercios, zonas que la plataforma tapa,
donde esta el detalle, donde cae el texto y si la pieza sobrevive al tamano
real del feed. Como en `color`, aca no hay ninguna preferencia de canal: los
umbrales entran por parametro y el skin es quien los declara.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageChops, ImageFilter

from . import color as col

# El feed movil de YouTube muestra la miniatura a este tamano. Es el examen
# final: lo que no se lee aca no se lee en ningun lado.
TAMANO_FEED = (210, 118)

PUNTOS_FUERTES = ("superior_izquierdo", "superior_derecho",
                  "inferior_izquierdo", "inferior_derecho")

# Vocabulario de posiciones, el mismo que ya usa `texto.posicion` del skin.
POSICIONES = ("izq_sup", "centro_sup", "der_sup",
              "izq_centro", "centro", "der_centro",
              "izq_inf", "centro_inf", "der_inf")

PESOS_CAJA_TEXTO = {
    "limpieza": 0.30,     # que el texto no caiga sobre el detalle
    "contraste": 0.25,    # que se lea contra lo que tiene debajo
    "preferencia": 0.18,  # lo que pide el skin
    "foco_libre": 0.10,   # no tapar el punto focal
    "tercios": 0.09,
    "equilibrio": 0.08,
}


def _fraccion(valor: Any, defecto: float) -> float:
    """Acepta 18 o 0.18 y devuelve 0.18.

    Los skins declaran porcentajes en enteros y las funciones trabajan en
    fracciones; obligar a una sola convencion solo genera bugs silenciosos.
    """
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    if v < 0:
        return defecto
    return v / 100.0 if v > 1.0 else v


# --- geometria ---------------------------------------------------------------
@dataclass
class Caja:
    x: int
    y: int
    ancho: int
    alto: int

    @property
    def x2(self) -> int:
        return self.x + self.ancho

    @property
    def y2(self) -> int:
        return self.y + self.alto

    @property
    def area(self) -> int:
        return max(0, self.ancho) * max(0, self.alto)

    @property
    def centro(self) -> tuple:
        return (self.x + self.ancho / 2.0, self.y + self.alto / 2.0)

    def caja_pil(self) -> tuple:
        """(izq, sup, der, inf), lista para Image.crop."""
        return (int(self.x), int(self.y), int(self.x2), int(self.y2))

    def contiene(self, x: float, y: float) -> bool:
        return self.x <= x < self.x2 and self.y <= y < self.y2

    def area_solapada(self, otra: "Caja") -> int:
        ox = max(0, min(self.x2, otra.x2) - max(self.x, otra.x))
        oy = max(0, min(self.y2, otra.y2) - max(self.y, otra.y))
        return ox * oy

    def solape(self, otra: "Caja") -> float:
        """Porcion de ESTA caja que pisa la otra. 0..1."""
        return self.area_solapada(otra) / self.area if self.area else 0.0

    def dentro_de(self, ancho: int, alto: int) -> bool:
        return self.x >= 0 and self.y >= 0 and self.x2 <= ancho and self.y2 <= alto


@dataclass
class Rejilla:
    ancho: int
    alto: int
    verticales: list
    horizontales: list
    puntos: dict

    def punto(self, nombre: str) -> tuple:
        if nombre not in self.puntos:
            raise ValueError(
                f"punto fuerte desconocido: {nombre!r}; validos: {', '.join(PUNTOS_FUERTES)}")
        return self.puntos[nombre]


def rejilla_tercios(ancho: int, alto: int) -> Rejilla:
    """Lineas de tercios y los cuatro puntos fuertes, en pixeles."""
    vx = [round(ancho / 3.0), round(2 * ancho / 3.0)]
    hy = [round(alto / 3.0), round(2 * alto / 3.0)]
    puntos = {
        "superior_izquierdo": (vx[0], hy[0]),
        "superior_derecho": (vx[1], hy[0]),
        "inferior_izquierdo": (vx[0], hy[1]),
        "inferior_derecho": (vx[1], hy[1]),
    }
    return Rejilla(ancho=ancho, alto=alto, verticales=vx, horizontales=hy, puntos=puntos)


# --- zonas seguras -----------------------------------------------------------
def zonas_seguras(ancho: int, alto: int, inferior_pct: Any = 8,
                  inferior_derecha_pct: Any = 18) -> dict:
    """Cajas que la plataforma tapa y donde no puede caer nada relevante.

    `inferior_pct` es una franja de ancho completo (barra de progreso).
    `inferior_derecha_pct` es un cuadro anclado abajo a la derecha, con ese
    porcentaje de ancho y de alto (badge de duracion). Los dos valores salen
    del skin: aca solo hay defectos por si el skin no los declara.
    """
    fi = _fraccion(inferior_pct, 0.08)
    fd = _fraccion(inferior_derecha_pct, 0.18)
    alto_barra = int(round(alto * fi))
    ancho_badge = int(round(ancho * fd))
    alto_badge = int(round(alto * fd))
    return {
        "barra_progreso": Caja(0, alto - alto_barra, ancho, alto_barra),
        "badge_duracion": Caja(ancho - ancho_badge, alto - alto_badge,
                               ancho_badge, alto_badge),
    }


def zonas_seguras_de_skin(skin, ancho: int | None = None, alto: int | None = None) -> dict:
    """Las zonas del skin. Si el skin no las declara, se usan los defectos."""
    datos = getattr(skin, "skin", skin) or {}
    lienzo = datos.get("lienzo") or {}
    bloque = datos.get("zonas_seguras") or {}
    return zonas_seguras(
        int(ancho if ancho is not None else lienzo.get("ancho", 1280)),
        int(alto if alto is not None else lienzo.get("alto", 720)),
        bloque.get("inferior_pct", 8),
        bloque.get("inferior_derecha_pct", 18),
    )


def respeta_zonas_seguras(caja: Caja, zonas: dict, tolerancia: float = 0.0) -> tuple:
    """(cumple, [nombres invadidos]). `tolerancia` es solape aceptado 0..1."""
    invadidas = [nombre for nombre, zona in (zonas or {}).items()
                 if caja.solape(zona) > tolerancia]
    return (not invadidas, invadidas)


# --- mapa de detalle ---------------------------------------------------------
@dataclass
class MapaDetalle:
    """Cuanto 'pasa' en cada celda de una rejilla gruesa sobre la imagen.

    `celdas` esta en escala absoluta (energia media de alta frecuencia) y
    `relativas` esta normalizado por el maximo. Para decidir donde poner el
    texto interesa el relativo; para comparar dos imagenes, el absoluto.
    """

    columnas: int
    filas: int
    ancho: int
    alto: int
    celdas: list
    relativas: list
    maximo: float
    promedio: float

    def valor(self, columna: int, fila: int, relativo: bool = True) -> float:
        tabla = self.relativas if relativo else self.celdas
        return tabla[fila][columna]

    def detalle_en(self, caja: Caja, relativo: bool = True) -> float:
        """Detalle medio bajo una caja, ponderado por area de solape."""
        tabla = self.relativas if relativo else self.celdas
        cw = self.ancho / float(self.columnas)
        ch = self.alto / float(self.filas)
        total = 0.0
        peso = 0.0
        for f in range(self.filas):
            oy = max(0.0, min((f + 1) * ch, caja.y2) - max(f * ch, caja.y))
            if oy <= 0:
                continue
            for c in range(self.columnas):
                ox = max(0.0, min((c + 1) * cw, caja.x2) - max(c * cw, caja.x))
                if ox <= 0:
                    continue
                area = ox * oy
                total += tabla[f][c] * area
                peso += area
        return total / peso if peso else 0.0

    def celda_de(self, x: float, y: float) -> tuple:
        c = max(0, min(self.columnas - 1, int(x * self.columnas / self.ancho)))
        f = max(0, min(self.filas - 1, int(y * self.filas / self.alto)))
        return (c, f)


def mapa_detalle(imagen: Image.Image, columnas: int = 16, filas: int = 9,
                 radio: float = 2.0, lado_max: int = 256) -> MapaDetalle:
    """Ocupacion visual por celda: |imagen - imagen desenfocada|.

    La diferencia contra la version suave es una varianza local barata y sin
    artefactos de borde, que es lo que FIND_EDGES si tiene. Alcanza de sobra
    para distinguir cielo liso de follaje.
    """
    ancho, alto = imagen.size
    gris = imagen.convert("L")
    if max(gris.size) > lado_max:
        escala = lado_max / float(max(gris.size))
        gris = gris.resize((max(1, int(gris.size[0] * escala)),
                            max(1, int(gris.size[1] * escala))), Image.BILINEAR)
    detalle = ImageChops.difference(gris, gris.filter(ImageFilter.GaussianBlur(radio)))
    reducido = detalle.resize((columnas, filas), Image.BOX)
    datos = col.datos_planos(reducido)

    celdas = [[datos[f * columnas + c] / 255.0 for c in range(columnas)]
              for f in range(filas)]
    plano = [v for fila in celdas for v in fila]
    maximo = max(plano) if plano else 0.0
    promedio = sum(plano) / len(plano) if plano else 0.0
    relativas = ([[v / maximo for v in fila] for fila in celdas] if maximo > 0
                 else [[0.0] * columnas for _ in range(filas)])
    return MapaDetalle(columnas, filas, ancho, alto, celdas, relativas, maximo, promedio)


def _mapa_color(imagen: Image.Image, columnas: int, filas: int) -> list:
    chica = imagen.convert("RGB").resize((columnas, filas), Image.BOX)
    datos = col.datos_planos(chica)
    return [[datos[f * columnas + c] for c in range(columnas)] for f in range(filas)]


# --- peso visual y espacio negativo ------------------------------------------
@dataclass
class Balance:
    centro_x: float
    centro_y: float
    desvio_x: float      # -1 todo a la izquierda .. +1 todo a la derecha
    desvio_y: float      # -1 arriba .. +1 abajo
    desbalanceada: bool
    lado: str            # izquierda | derecha | arriba | abajo | equilibrada


def centro_de_masa(mapa: MapaDetalle, caja_texto: Caja | None = None,
                   peso_texto: float = 1.0) -> tuple:
    """Centro de masa del detalle, en coordenadas absolutas de la imagen.

    Si se pasa la caja del texto, su masa entra en la cuenta. No es un
    detalle: en la miniatura terminada el bloque de texto es uno de los
    elementos mas pesados que hay, y medir el equilibrio solo sobre el fondo
    da por desbalanceado el encuadre mas comun y mas eficaz que existe -el
    sujeto de un lado y el texto del otro-, que en realidad se compensa.
    """
    cw = mapa.ancho / float(mapa.columnas)
    ch = mapa.alto / float(mapa.filas)
    sx = sy = peso = 0.0
    for f in range(mapa.filas):
        for c in range(mapa.columnas):
            v = mapa.relativas[f][c]
            sx += v * (c + 0.5) * cw
            sy += v * (f + 0.5) * ch
            peso += v

    if caja_texto is not None and peso_texto > 0:
        # El texto se cuenta como detalle pleno sobre el area que ocupa,
        # escalado al tamano de celda para que sea comparable con el mapa.
        celdas_texto = (caja_texto.ancho * caja_texto.alto) / float(cw * ch)
        masa = celdas_texto * peso_texto
        tcx, tcy = caja_texto.centro
        sx += masa * tcx
        sy += masa * tcy
        peso += masa

    if peso <= 0:
        return (mapa.ancho / 2.0, mapa.alto / 2.0)
    return (sx / peso, sy / peso)


def balance(mapa: MapaDetalle, umbral: float = 0.35,
            caja_texto: Caja | None = None, peso_texto: float = 1.0) -> Balance:
    cx, cy = centro_de_masa(mapa, caja_texto, peso_texto)
    dx = (cx / mapa.ancho - 0.5) * 2
    dy = (cy / mapa.alto - 0.5) * 2
    lado = "equilibrada"
    if abs(dx) >= abs(dy) and abs(dx) > umbral:
        lado = "derecha" if dx > 0 else "izquierda"
    elif abs(dy) > umbral:
        lado = "abajo" if dy > 0 else "arriba"
    return Balance(cx, cy, dx, dy, lado != "equilibrada", lado)


def espacio_negativo(mapa: MapaDetalle, umbral: float = 0.18) -> float:
    """Porcion de la imagen sin detalle relevante. 0..1.

    El umbral es relativo al maximo de la propia imagen: una foto entera de
    poco contraste igual tiene zonas mas y menos ocupadas.
    """
    plano = [v for fila in mapa.relativas for v in fila]
    if not plano:
        return 1.0
    return sum(1 for v in plano if v <= umbral) / len(plano)


# --- separacion sujeto / fondo -----------------------------------------------
@dataclass
class SeparacionSujeto:
    delta_e: float
    contraste: float
    energia_borde: float
    color_sujeto: str
    color_fondo: str
    puntaje: float
    minimo: float

    @property
    def cumple(self) -> bool:
        return self.puntaje >= self.minimo


def separacion_sujeto_fondo(imagen: Image.Image, mapa: MapaDetalle | None = None,
                            corte_sujeto: float = 0.60, corte_fondo: float = 0.25,
                            minimo: float = 0.35) -> SeparacionSujeto:
    """Cuanto se despega lo que ocupa el encuadre de lo que hay detras.

    Sujeto = celdas con mas detalle; fondo = celdas planas. Si el color medio
    de unas y otras es el mismo, el sujeto esta camuflado por mas nitida que
    sea la foto: por eso pesa el delta E y no solo la energia de borde.
    """
    m = mapa or mapa_detalle(imagen)
    colores = _mapa_color(imagen, m.columnas, m.filas)

    sujeto, fondo = [], []
    for f in range(m.filas):
        for c in range(m.columnas):
            v = m.relativas[f][c]
            if v >= corte_sujeto:
                sujeto.append(colores[f][c])
            elif v <= corte_fondo:
                fondo.append(colores[f][c])
    if not sujeto or not fondo:
        # Sin dos poblaciones no hay separacion que medir: no hay sujeto.
        plano = colores[0][0] if colores and colores[0] else (0, 0, 0)
        return SeparacionSujeto(0.0, 1.0, m.promedio, col.a_hex(plano),
                                col.a_hex(plano), 0.0, minimo)

    def medio(px):
        n = len(px)
        return tuple(sum(p[i] for p in px) / n for i in range(3))

    cs, cf = medio(sujeto), medio(fondo)
    d_e = col.delta_e_2000(col.rgb_a_lab(cs), col.rgb_a_lab(cf))
    contraste = col.razon_contraste(cs, cf)
    energia = m.promedio

    puntaje = (0.45 * min(1.0, d_e / 25.0)
               + 0.35 * min(1.0, (contraste - 1.0) / 3.0)
               + 0.20 * min(1.0, energia * 8.0))
    return SeparacionSujeto(d_e, contraste, energia, col.a_hex(cs), col.a_hex(cf),
                            max(0.0, min(1.0, puntaje)), minimo)


@dataclass
class PruebaDesenfoque:
    radio_px: float
    retencion: float           # estructura que sobrevive al desenfoque, 0..1
    contraste_silueta: float   # razon WCAG entre sujeto y fondo, ya desenfocado
    puntaje: float
    minimo: float

    @property
    def cumple(self) -> bool:
        return self.puntaje >= self.minimo

    def resumen(self) -> str:
        return (f"con desenfoque de {self.radio_px:.0f} px sobrevive el "
                f"{self.retencion * 100:.0f}% de la estructura y la silueta "
                f"contrasta {self.contraste_silueta:.2f}:1")


def _estructura(imagen: Image.Image, columnas: int, filas: int) -> list:
    """Luminancia relativa media por celda."""
    colores = _mapa_color(imagen, columnas, filas)
    return [[col.luminancia_relativa(c) for c in fila] for fila in colores]


def prueba_desenfoque(imagen: Image.Image, radio_pct: float = 0.035,
                      minimo: float = 0.35, columnas: int = 16,
                      filas: int = 9) -> PruebaDesenfoque:
    """Desenfoca fuerte y mide que queda.

    Es la prueba del entrecerrar los ojos, hecha a maquina: si al desenfocar
    la silueta se disuelve en el fondo, el encuadre no tiene sujeto — tiene
    textura. Devuelve la medida, no un si o no.
    """
    ancho, alto = imagen.size
    radio_real = max(1.0, ancho * radio_pct)

    chica = col.reducir(imagen.convert("RGB"), 256)
    escala = chica.size[0] / float(ancho)
    radio_chico = max(1.0, radio_real * escala)
    borrosa = chica.filter(ImageFilter.GaussianBlur(radio_chico))

    m = mapa_detalle(chica, columnas, filas)
    original = _estructura(chica, columnas, filas)
    difusa = _estructura(borrosa, columnas, filas)

    def desvio(tabla):
        plano = [v for fila in tabla for v in fila]
        media = sum(plano) / len(plano)
        return math.sqrt(sum((v - media) ** 2 for v in plano) / len(plano))

    d_orig = desvio(original)
    retencion = min(1.0, desvio(difusa) / d_orig) if d_orig > 1e-6 else 0.0

    sujeto, fondo = [], []
    for f in range(filas):
        for c in range(columnas):
            (sujeto if m.relativas[f][c] >= 0.60 else fondo).append(difusa[f][c])
    if sujeto and fondo:
        ls = sum(sujeto) / len(sujeto)
        lf = sum(fondo) / len(fondo)
        contraste = (max(ls, lf) + 0.05) / (min(ls, lf) + 0.05)
    else:
        contraste = 1.0

    puntaje = 0.5 * retencion + 0.5 * min(1.0, (contraste - 1.0) / 2.0)
    return PruebaDesenfoque(radio_real, retencion, contraste,
                            max(0.0, min(1.0, puntaje)), minimo)


# --- legibilidad a tamano de feed --------------------------------------------
@dataclass
class Legibilidad:
    tamano: tuple
    retencion_sujeto: float
    contraste_silueta: float
    solidez_texto: float       # 1.0 = el trazo sobrevive entero al reescalado
    alto_texto_px: float       # alto del bloque de texto ya reducido
    contraste_texto: float     # peor caso contra el fondo reducido
    puntaje: float
    minimo: float
    motivos: list = field(default_factory=list)

    @property
    def cumple(self) -> bool:
        return self.puntaje >= self.minimo and not self.motivos


def anillo_mascara(mascara: Image.Image, radio: int = 4,
                   interior: int = 2) -> Image.Image:
    """La franja de fondo que rodea al trazo, sin el trazo ni su antialias.

    Es contra esto que hay que medir el contraste de un texto YA dibujado.
    Muestrear la imagen final bajo la mascara del texto devuelve el color del
    propio texto y da 1.00:1 -el texto comparado consigo mismo-, que parece
    un fallo catastrofico de contraste y en realidad es un error de medicion.

    `interior` descarta los primeros pixeles alrededor del trazo, que estan
    mezclados por el suavizado de bordes: son mitad texto y mitad fondo, y
    contra ellos cualquier texto mide pesimo sin que eso signifique nada
    sobre su legibilidad. Lo que interesa empieza pasada esa franja.

    El anillo ademas contempla lo que el ojo realmente ve: si hay contorno o
    placa, es eso lo que rodea a la letra, y es eso lo que la hace legible.
    """
    externo = mascara.filter(ImageFilter.MaxFilter(max(3, radio * 2 + 1)))
    interno = mascara.filter(ImageFilter.MaxFilter(max(3, interior * 2 + 1)))
    return ImageChops.subtract(externo, interno)


def legibilidad_en_feed(imagen: Image.Image, mascara_texto: Image.Image | None = None,
                        color_texto=None, tamano: tuple = TAMANO_FEED,
                        minimo: float = 0.55, contraste_minimo: float = 4.5,
                        alto_texto_minimo: float = 9.0,
                        solidez_minima: float = 0.55) -> Legibilidad:
    """Reescala al tamano real del feed movil y ve que sobrevive.

    Nadie mira una miniatura a 1280 px. Un titular de trazo fino y un sujeto
    de bajo contraste desaparecen al reducir, y el defecto no se ve nunca en
    el archivo original.
    """
    chica = imagen.convert("RGB").resize(tamano, Image.LANCZOS)
    motivos: list = []

    prueba = prueba_desenfoque(imagen, minimo=0.0)
    m_grande = mapa_detalle(imagen)
    m_chica = mapa_detalle(chica)
    retencion = (min(1.0, m_chica.promedio / m_grande.promedio)
                 if m_grande.promedio > 1e-6 else 0.0)

    solidez = 1.0
    alto_texto = 0.0
    contraste_texto = 0.0
    if mascara_texto is not None:
        msk = mascara_texto.convert("L")
        if msk.size != imagen.size:
            msk = msk.resize(imagen.size, Image.NEAREST)
        caja = msk.getbbox()
        escala_y = tamano[1] / float(imagen.size[1])
        alto_texto = (caja[3] - caja[1]) * escala_y if caja else 0.0

        grandes = col.datos_planos(msk)
        solidos_grandes = sum(1 for v in grandes if v >= 128)
        msk_chica = msk.resize(tamano, Image.LANCZOS)
        solidos_chicos = sum(1 for v in col.datos_planos(msk_chica) if v >= 190)
        escala_area = (tamano[0] * tamano[1]) / float(imagen.size[0] * imagen.size[1])
        esperado = solidos_grandes * escala_area
        solidez = min(1.0, solidos_chicos / esperado) if esperado > 0 else 0.0

        if color_texto is not None:
            # Contra el anillo que rodea al trazo, no contra el trazo mismo:
            # `imagen` ya trae el texto dibujado encima.
            anillo = anillo_mascara(msk_chica, 2, 1)
            informe = col.contraste_sobre_fondo(color_texto, chica, anillo,
                                                contraste_minimo)
            if informe.muestras == 0:  # trazo tan fino que no dejo anillo
                informe = col.contraste_sobre_fondo(color_texto, chica, msk_chica,
                                                    contraste_minimo)
            # Percentil 5 y no el pixel peor: a este tamano casi todo el
            # borde es antialias, y el minimo absoluto no seria medible.
            contraste_texto = informe.percentil_5
            if informe.muestras and informe.percentil_5 < contraste_minimo:
                motivos.append(
                    f"a {tamano[0]}x{tamano[1]} el texto cae a "
                    f"{informe.percentil_5:.2f}:1 contra su fondo "
                    f"(minimo {contraste_minimo:.1f}:1)")
        if alto_texto < alto_texto_minimo:
            motivos.append(
                f"el bloque de texto mide {alto_texto:.1f} px en el feed, menos de "
                f"los {alto_texto_minimo:.0f} px que hacen falta para leerlo")
        if solidez < solidez_minima:
            motivos.append(
                f"el trazo pierde el {100 - solidez * 100:.0f}% de su cuerpo al "
                f"reducir: la tipografia es demasiado fina para este tamano")

    partes = [0.4 * retencion, 0.3 * min(1.0, (prueba.contraste_silueta - 1.0) / 2.0)]
    partes.append(0.3 * solidez if mascara_texto is not None else 0.3)
    puntaje = max(0.0, min(1.0, sum(partes)))
    return Legibilidad(tamano, retencion, prueba.contraste_silueta, solidez,
                       alto_texto, contraste_texto, puntaje, minimo, motivos)


# --- eleccion de la caja de texto --------------------------------------------
@dataclass
class Candidata:
    nombre: str
    caja: Caja
    puntaje: float
    componentes: dict
    descartada_por: str = ""


@dataclass
class EleccionCaja:
    caja: Caja
    nombre: str
    puntaje: float
    componentes: dict
    motivo: str
    candidatas: list = field(default_factory=list)
    zonas_invadidas: list = field(default_factory=list)


def _anclas(ancho: int, alto: int, w: int, h: int, margen: int,
            margen_inferior: int | None = None) -> dict:
    """Las nueve anclas clasicas.

    `margen_inferior` va aparte porque la franja de la barra de progreso se
    mide sobre el alto y el margen general sobre el ancho: con un solo valor,
    las anclas de abajo caen dentro de la zona segura y se descartan siempre.
    """
    mi = margen if margen_inferior is None else margen_inferior
    xs = {"izq": margen, "centro": int((ancho - w) / 2), "der": ancho - w - margen}
    ys = {"sup": margen, "centro": int((alto - h) / 2), "inf": alto - h - mi}
    salida = {}
    for cx, x in xs.items():
        for cy, y in ys.items():
            if cx == "centro" and cy == "centro":
                nombre = "centro"
            elif cx == "centro":
                nombre = f"centro_{cy}"
            elif cy == "centro":
                nombre = f"{cx}_centro"
            else:
                nombre = f"{cx}_{cy}"
            salida[nombre] = Caja(x, y, w, h)
    return salida


def elegir_caja_texto(imagen: Image.Image, tamano: tuple,
                      posicion_preferida: str | None = None,
                      ancho_max_pct: Any = None,
                      zonas: dict | None = None,
                      mapa: MapaDetalle | None = None,
                      color_texto=None,
                      contraste_minimo: float = col.CONTRASTE_MINIMO,
                      margen_pct: Any = 4,
                      punto_focal: str | None = None,
                      alinear_a_tercios: bool = True,
                      pesos: dict | None = None,
                      tolerancia_zonas: float = 0.0) -> EleccionCaja:
    """Elige donde va el bloque de texto y explica por que gano.

    Puntua nueve anclas mas los cuatro puntos fuertes de la rejilla contra
    cinco criterios: que la zona este limpia, que el color se lea encima, que
    respete lo que pide el skin, que no tape el punto focal y que equilibre
    el peso visual. Las zonas seguras no puntuan: descartan.
    """
    ancho, alto = imagen.size
    w, h = int(tamano[0]), int(tamano[1])
    pesos = dict(PESOS_CAJA_TEXTO if pesos is None else pesos)
    margen = int(round(ancho * _fraccion(margen_pct, 0.04)))
    m = mapa or mapa_detalle(imagen)
    zonas = zonas_seguras(ancho, alto) if zonas is None else zonas
    rejilla = rejilla_tercios(ancho, alto)
    peso_visual = balance(m)

    limite = None
    if ancho_max_pct is not None:
        limite = int(round(ancho * _fraccion(ancho_max_pct, 1.0)))

    # Las anclas de abajo tienen que quedar POR ENCIMA de la barra de
    # progreso. Con el margen general (un porcentaje del ancho) una caja
    # anclada abajo cae dentro de la franja inferior (un porcentaje del alto)
    # y se descarta: la posicion 'inf' que pide el skin quedaba inalcanzable
    # y el texto terminaba en otro lado sin que nadie se enterara.
    alto_barra = max((z.alto for n, z in zonas.items() if "barra" in n), default=0)
    margen_inferior = max(margen, alto_barra + max(4, int(alto * 0.01)))
    candidatas_geo = _anclas(ancho, alto, w, h, margen, margen_inferior)
    if alinear_a_tercios:
        for nombre in PUNTOS_FUERTES:
            px, py = rejilla.punto(nombre)
            candidatas_geo[f"punto_{nombre}"] = Caja(int(px - w / 2), int(py - h / 2), w, h)

    foco = rejilla.punto(punto_focal) if punto_focal in rejilla.puntos else None
    diagonal = math.hypot(ancho, alto)
    ref = candidatas_geo.get(posicion_preferida) if posicion_preferida else None

    evaluadas: list = []
    for nombre, caja in candidatas_geo.items():
        if not caja.dentro_de(ancho, alto):
            evaluadas.append(Candidata(nombre, caja, 0.0, {}, "se sale del lienzo"))
            continue
        ok_zonas, invadidas = respeta_zonas_seguras(caja, zonas, tolerancia_zonas)

        limpieza = 1.0 - m.detalle_en(caja)

        if color_texto is not None:
            recorte = imagen.crop(caja.caja_pil())
            informe = col.contraste_sobre_fondo(color_texto, recorte,
                                                minimo=contraste_minimo)
            contraste = min(1.0, informe.peor / contraste_minimo) * 0.5 + \
                min(1.0, informe.fraccion_ok) * 0.5
        else:
            contraste = 1.0
            informe = None

        if ref is None:
            preferencia = 1.0
        elif nombre == posicion_preferida:
            preferencia = 1.0
        else:
            d = math.dist(caja.centro, ref.centro)
            preferencia = max(0.0, 1.0 - d / diagonal)

        if foco is None:
            foco_libre = 1.0
        else:
            foco_libre = 0.0 if caja.contiene(*foco) else 1.0

        cx, cy = caja.centro
        d_punto = min(math.dist((cx, cy), p) for p in rejilla.puntos.values())
        tercios = max(0.0, 1.0 - d_punto / (diagonal * 0.35))

        dx = (cx / ancho - 0.5) * 2
        dy = (cy / alto - 0.5) * 2
        equilibrio = (0.7 * (1 - peso_visual.desvio_x * dx)
                      + 0.3 * (1 - peso_visual.desvio_y * dy)) / 2.0

        componentes = {
            "limpieza": round(limpieza, 4),
            "contraste": round(contraste, 4),
            "preferencia": round(preferencia, 4),
            "foco_libre": round(foco_libre, 4),
            "tercios": round(tercios, 4),
            "equilibrio": round(max(0.0, min(1.0, equilibrio)), 4),
        }
        if informe is not None:
            componentes["contraste_peor"] = round(informe.peor, 3)
            componentes["contraste_promedio"] = round(informe.promedio, 3)
        if limite is not None and w > limite:
            componentes["excede_ancho_max"] = True

        total = sum(pesos.values()) or 1.0
        puntaje = sum(pesos.get(k, 0.0) * componentes[k] for k in
                      ("limpieza", "contraste", "preferencia", "foco_libre",
                       "tercios", "equilibrio")) / total

        evaluadas.append(Candidata(
            nombre, caja, puntaje, componentes,
            "" if ok_zonas else f"invade {', '.join(invadidas)}"))

    validas = [c for c in evaluadas if not c.descartada_por]
    if validas:
        ganadora = max(validas, key=lambda c: c.puntaje)
        invadidas: list = []
        nota = ""
    else:
        # Ninguna ancla entra limpia: gana la que menos invade, y se avisa.
        def solape_total(c: Candidata) -> float:
            return sum(c.caja.solape(z) for z in zonas.values())

        ganadora = min(evaluadas, key=lambda c: (solape_total(c), -c.puntaje))
        invadidas = respeta_zonas_seguras(ganadora.caja, zonas)[1]
        nota = (" Ninguna ubicacion respeta las zonas seguras con este tamano de "
                "bloque: se eligio la que menos invade.")

    # El motivo nombra los criterios que mas aportaron al puntaje ganador.
    aportes = [(k, pesos.get(k, 0.0) * float(ganadora.componentes.get(k, 0.0)))
               for k in pesos]
    aportes.sort(key=lambda kv: -kv[1])
    razones = ", ".join(
        f"{k} {ganadora.componentes.get(k, 0.0):.2f}" for k, _ in aportes[:3])
    motivo = (f"'{ganadora.nombre}' gana con {ganadora.puntaje:.3f}: {razones}."
              f"{nota}")

    return EleccionCaja(ganadora.caja, ganadora.nombre, ganadora.puntaje,
                        ganadora.componentes, motivo,
                        sorted(evaluadas, key=lambda c: -c.puntaje), invadidas)


# --- lectura del skin --------------------------------------------------------
@dataclass
class PoliticaComposicion:
    """Bloque `composicion` del skin, ya resuelto con defectos.

    Igual que en color: ninguna clave es obligatoria. Un skin anterior a este
    bloque tiene que renderizar exactamente como antes.
    """

    posicion_preferida: str = "izq_inf"
    ancho_max_pct: float = 60.0
    margen_pct: float = 4.0
    punto_focal_preferido: str = "superior_derecho"
    espacio_negativo_minimo: float = 0.30
    detalle_maximo_bajo_texto: float = 0.35
    desbalance_maximo: float = 0.45
    separacion_sujeto_minima: float = 0.35
    retencion_desenfoque_minima: float = 0.35
    legibilidad_feed_minima: float = 0.55
    alto_texto_feed_minimo: float = 9.0
    alinear_a_tercios: bool = True
    zona_inferior_pct: float = 8.0
    zona_inferior_derecha_pct: float = 18.0
    pesos: dict = field(default_factory=lambda: dict(PESOS_CAJA_TEXTO))


def politica_composicion(skin) -> PoliticaComposicion:
    datos = getattr(skin, "skin", skin) or {}
    bloque = datos.get("composicion") or {}
    texto = datos.get("texto") or {}
    zonas = datos.get("zonas_seguras") or {}
    defecto = PoliticaComposicion()

    def num(clave, base, fuente=None):
        valor = (fuente if fuente is not None else bloque).get(clave, base)
        try:
            return float(valor)
        except (TypeError, ValueError):
            return base

    pesos = dict(PESOS_CAJA_TEXTO)
    for clave, valor in (bloque.get("pesos") or {}).items():
        try:
            pesos[str(clave)] = float(valor)
        except (TypeError, ValueError):
            continue

    focal = str(bloque.get("punto_focal_preferido", defecto.punto_focal_preferido))
    if focal not in PUNTOS_FUERTES:
        focal = defecto.punto_focal_preferido

    posicion = str(texto.get("posicion", defecto.posicion_preferida))

    return PoliticaComposicion(
        posicion_preferida=posicion if posicion in POSICIONES else defecto.posicion_preferida,
        ancho_max_pct=num("ancho_max_pct", texto.get("ancho_max_pct", defecto.ancho_max_pct)),
        margen_pct=num("margen_pct", defecto.margen_pct),
        punto_focal_preferido=focal,
        espacio_negativo_minimo=num("espacio_negativo_minimo", defecto.espacio_negativo_minimo),
        detalle_maximo_bajo_texto=num("detalle_maximo_bajo_texto",
                                      defecto.detalle_maximo_bajo_texto),
        desbalance_maximo=num("desbalance_maximo", defecto.desbalance_maximo),
        separacion_sujeto_minima=num("separacion_sujeto_minima",
                                     defecto.separacion_sujeto_minima),
        retencion_desenfoque_minima=num("retencion_desenfoque_minima",
                                        defecto.retencion_desenfoque_minima),
        legibilidad_feed_minima=num("legibilidad_feed_minima",
                                    defecto.legibilidad_feed_minima),
        alto_texto_feed_minimo=num("alto_texto_feed_minimo", defecto.alto_texto_feed_minimo),
        alinear_a_tercios=bool(bloque.get("alinear_a_tercios", defecto.alinear_a_tercios)),
        zona_inferior_pct=num("inferior_pct", defecto.zona_inferior_pct, zonas),
        zona_inferior_derecha_pct=num("inferior_derecha_pct",
                                      defecto.zona_inferior_derecha_pct, zonas),
        pesos=pesos,
    )


def evaluar_composicion(imagen: Image.Image,
                        politica: PoliticaComposicion | None = None,
                        caja_texto: Caja | None = None,
                        mascara_texto: Image.Image | None = None,
                        color_texto=None) -> dict:
    """Contrasta un encuadre contra la politica. Insumo directo de QA."""
    pol = politica or PoliticaComposicion()
    ancho, alto = imagen.size
    m = mapa_detalle(imagen)
    zonas = zonas_seguras(ancho, alto, pol.zona_inferior_pct, pol.zona_inferior_derecha_pct)

    # El equilibrio se mide con el texto adentro. Si no llego la caja pero si
    # la mascara, se deduce de sus limites: lo que importa es que la masa del
    # texto entre en la cuenta, no como se la paso quien llama.
    caja_peso = caja_texto
    if caja_peso is None and mascara_texto is not None:
        limites = mascara_texto.getbbox()
        if limites:
            mx, my = mascara_texto.size
            ex, ey = ancho / float(mx), alto / float(my)
            x0, y0, x1, y1 = limites
            caja_peso = Caja(int(x0 * ex), int(y0 * ey),
                             int((x1 - x0) * ex), int((y1 - y0) * ey))
    bal = balance(m, pol.desbalance_maximo, caja_peso)
    negativo = espacio_negativo(m)
    separacion = separacion_sujeto_fondo(imagen, m, minimo=pol.separacion_sujeto_minima)
    desenfoque = prueba_desenfoque(imagen, minimo=pol.retencion_desenfoque_minima)
    feed = legibilidad_en_feed(imagen, mascara_texto, color_texto,
                               minimo=pol.legibilidad_feed_minima,
                               alto_texto_minimo=pol.alto_texto_feed_minimo)

    hallazgos: list = []
    if negativo < pol.espacio_negativo_minimo:
        hallazgos.append(
            f"espacio negativo {negativo:.2f} bajo el minimo "
            f"{pol.espacio_negativo_minimo:.2f}: el encuadre esta lleno")
    if bal.desbalanceada:
        hallazgos.append(
            f"peso visual corrido hacia {bal.lado} "
            f"(desvio x {bal.desvio_x:+.2f}, y {bal.desvio_y:+.2f})")
    if not separacion.cumple:
        hallazgos.append(
            f"el sujeto no se despega del fondo (puntaje {separacion.puntaje:.2f}, "
            f"delta E {separacion.delta_e:.1f}, minimo {pol.separacion_sujeto_minima:.2f})")
    if not desenfoque.cumple:
        hallazgos.append(f"la silueta no sobrevive al desenfoque: {desenfoque.resumen()}")
    if not feed.cumple:
        hallazgos.append(
            f"legibilidad en feed {feed.puntaje:.2f} bajo el minimo "
            f"{pol.legibilidad_feed_minima:.2f}")
        hallazgos.extend(feed.motivos)
    if caja_texto is not None:
        ok, invadidas = respeta_zonas_seguras(caja_texto, zonas)
        if not ok:
            hallazgos.append(f"el bloque de texto invade {', '.join(invadidas)}")
        detalle = m.detalle_en(caja_texto)
        if detalle > pol.detalle_maximo_bajo_texto:
            hallazgos.append(
                f"detalle bajo el texto {detalle:.2f} sobre el maximo "
                f"{pol.detalle_maximo_bajo_texto:.2f}")

    return {
        "mapa": m,
        "balance": bal,
        "espacio_negativo": negativo,
        "separacion": separacion,
        "desenfoque": desenfoque,
        "legibilidad": feed,
        "zonas_seguras": zonas,
        "hallazgos": hallazgos,
        "ok": not hallazgos,
    }
