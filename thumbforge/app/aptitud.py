"""Puntaje de aptitud para el feed.

**No es CTR predicho.** Sin datos propios de la audiencia real de este canal
nadie puede predecir el CTR de una miniatura, ni un modelo grande ni una
formula. Cualquier herramienta que diga hacerlo esta vendiendo humo.

Lo que si se puede medir es como una miniatura chequea contra los factores
que la evidencia externa cross-referenciada sostiene:

- Rostros con emocion legible atrapan la mirada mas rapido que otros
  elementos (eye-tracking real).
- Menos de 4 palabras rinde consistentemente mas que textos largos.
- Contraste alto (WCAG y complementarios) rinde ~30% mas segun estudios de
  Vidooly y otros.
- El 70%+ del trafico es movil: la miniatura se juzga a 210x113, no a
  1280x720.

Cada factor se pondera segun el peso que la evidencia le da y se muestra
DESGLOSADO. Un score alto no es garantia, pero un score bajo en varios
factores importantes es una miniatura que va a rendir mal casi seguro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from . import color as col
from . import composicion as comp
from .perfiles import Perfil


@dataclass
class Componente:
    """Un solo criterio de aptitud."""

    nombre: str
    puntaje: float           # 0..1
    peso: float              # cuanto pesa este criterio, 0..1
    motivo: str              # que se midio y cual fue el resultado

    @property
    def aporte(self) -> float:
        return self.puntaje * self.peso


@dataclass
class Aptitud:
    componentes: list[Componente] = field(default_factory=list)

    @property
    def puntaje(self) -> float:
        """0..100 para leerlo facil."""
        total_peso = sum(c.peso for c in self.componentes) or 1
        return sum(c.aporte for c in self.componentes) / total_peso * 100

    @property
    def flojos(self) -> list[Componente]:
        """Componentes por debajo de 0.5 con peso relevante: donde tiene
        sentido reemplazar la variante."""
        return [c for c in self.componentes if c.puntaje < 0.5 and c.peso >= 0.10]

    def resumen(self) -> str:
        return f"{self.puntaje:.0f}/100"


# --- criterios ---------------------------------------------------------------
def _contraste_a_puntaje(razon: float, minimo: float) -> float:
    """Escala WCAG a 0..1 usando el minimo del perfil como referencia.

    - Debajo del minimo: penaliza rapido.
    - Justo en el minimo: 0.6.
    - Del doble en adelante: 1.0.
    """
    if razon <= 1.0:
        return 0.0
    if razon < minimo:
        return max(0.0, 0.6 * (razon - 1.0) / (minimo - 1.0))
    return min(1.0, 0.6 + 0.4 * (razon - minimo) / max(1.0, minimo))


def _palabras_a_puntaje(palabras: int) -> float:
    """La evidencia dice: <4 palabras rinde ~30% mas. 1-3 es el rango ideal,
    4-5 aceptable, 6+ pierde fuerte."""
    if palabras == 0:
        return 0.4              # sin texto tampoco es lo mejor
    if palabras <= 3:
        return 1.0
    if palabras <= 5:
        return 0.75
    if palabras <= 8:
        return 0.45
    return 0.15


def _emocion_a_puntaje(emocion: str, hay_rostro: bool, mirada: str) -> float:
    """Rostros con emocion legible y mirada dirigida (a camara o a un objeto
    de interes) rinden mejor. Sin rostro no descarta la miniatura -hay generos
    donde no aplica-, pero para los que aplican, este componente pesa."""
    if not hay_rostro:
        return 0.5  # neutro: puede ser un canal que no muestra personas
    fuertes = {"asombro", "miedo", "determinacion", "dolor"}
    debiles = {"neutra", "ninguna"}
    if emocion in fuertes:
        base = 1.0
    elif emocion in debiles:
        base = 0.4
    else:
        base = 0.7  # otros valores del esquema
    # Mirada a camara suma; mirada perdida quita.
    if mirada == "a_camara":
        base = min(1.0, base + 0.1)
    elif mirada == "fuera_de_cuadro":
        base = base * 0.85
    return base


def _armonia_a_puntaje(ajuste: float, minimo: float) -> float:
    """Cumplir con la armonia declarada del skin. `ajuste` viene 0..1."""
    if ajuste >= minimo:
        return min(1.0, 0.7 + 0.3 * (ajuste - minimo) / max(0.01, 1 - minimo))
    return max(0.0, 0.7 * ajuste / max(0.01, minimo))


# --- entrada publica ---------------------------------------------------------
def puntuar(imagen: Image.Image, perfil: Perfil, *,
            mascara_texto: Image.Image | None = None,
            color_texto: str | None = None,
            palabras_texto: int | None = None,
            emocion: str | None = None,
            hay_rostro: bool | None = None,
            mirada: str | None = None) -> Aptitud:
    """Puntua una miniatura por su aptitud para el feed.

    Los datos de rostro y emocion vienen idealmente del anotador M2, que ya
    los mira sobre la miniatura. Si no vienen, se juzgan como neutros y se
    dice explicitamente.
    """
    pol_color = col.politica_color(perfil)
    pol_comp = comp.politica_composicion(perfil)
    componentes: list[Componente] = []

    # --- 1. Contraste del texto contra su fondo real -----------------------
    if mascara_texto is not None and color_texto:
        anillo = comp.anillo_mascara(mascara_texto, radio=6, interior=2)
        informe = col.contraste_sobre_fondo(color_texto, imagen, anillo,
                                            pol_color.contraste_minimo)
        if informe.muestras:
            puntaje = _contraste_a_puntaje(informe.percentil_5,
                                           pol_color.contraste_minimo)
            componentes.append(Componente(
                "contraste_texto", puntaje, 0.22,
                f"texto contra su fondo a percentil 5: {informe.percentil_5:.2f}:1 "
                f"(minimo del perfil {pol_color.contraste_minimo:.1f}:1)"))

    # --- 2. Legibilidad a tamano real del feed -----------------------------
    legibilidad = comp.legibilidad_en_feed(
        imagen, mascara_texto, color_texto,
        minimo=pol_comp.legibilidad_feed_minima,
        alto_texto_minimo=pol_comp.alto_texto_feed_minimo)
    componentes.append(Componente(
        "legibilidad_feed", min(1.0, legibilidad.puntaje / 0.8), 0.20,
        f"a 210x118 el puntaje da {legibilidad.puntaje:.2f} "
        f"(minimo del perfil {pol_comp.legibilidad_feed_minima:.2f}); "
        f"70% del trafico es movil y ahi es donde se decide el click"))

    # --- 3. Cantidad de palabras del titulo --------------------------------
    if palabras_texto is not None:
        componentes.append(Componente(
            "palabras", _palabras_a_puntaje(palabras_texto), 0.16,
            f"{palabras_texto} palabra(s); la evidencia dice que <4 rinde "
            f"~30% mas"))

    # --- 4. Rostro con emocion y mirada ------------------------------------
    if hay_rostro is not None or emocion is not None:
        puntaje_emocion = _emocion_a_puntaje(emocion or "ninguna",
                                              bool(hay_rostro),
                                              mirada or "sin_rostro")
        motivo = (f"rostro humano visible con emocion '{emocion or 'no anotada'}' "
                  f"y mirada '{mirada or 'no anotada'}'" if hay_rostro
                  else "sin rostro humano (aceptable en canales de objeto/escena)")
        componentes.append(Componente("rostro_emocion", puntaje_emocion, 0.18,
                                       motivo))

    # --- 5. Sujeto que se despega del fondo -------------------------------
    mapa = comp.mapa_detalle(imagen)
    separacion = comp.separacion_sujeto_fondo(
        imagen, mapa, minimo=pol_comp.separacion_sujeto_minima)
    puntaje_sep = min(1.0, separacion.puntaje / max(0.05,
                                                     pol_comp.separacion_sujeto_minima))
    componentes.append(Componente(
        "separacion_sujeto", puntaje_sep, 0.12,
        f"separacion sujeto-fondo {separacion.puntaje:.2f} "
        f"(minimo {pol_comp.separacion_sujeto_minima:.2f}); si al desenfocar "
        f"la silueta desaparece, la miniatura no tiene sujeto"))

    # --- 6. Encaje con la armonia declarada por el skin --------------------
    paleta = col.paleta_dominante(imagen, maximo=pol_color.max_colores_paleta)
    if paleta:
        colores = [p[0] if isinstance(p, (tuple, list)) else p for p in paleta]
        try:
            ajuste = col.ajuste_armonia(colores, pol_color.armonia_preferida)
        except Exception:  # noqa: BLE001 - una armonia mal declarada no rompe
            ajuste = 0.5
        componentes.append(Componente(
            "armonia_skin", _armonia_a_puntaje(ajuste, pol_color.armonia_ajuste_minimo),
            0.12,
            f"la paleta encaja {ajuste:.2f} con la armonia '{pol_color.armonia_preferida}' "
            f"que pide el skin (minimo {pol_color.armonia_ajuste_minimo:.2f})"))

    return Aptitud(componentes=componentes)


def rankear(variantes: list[dict]) -> list[dict]:
    """Anota cada variante con su ranking. Espera que cada elemento tenga
    'aptitud'; devuelve la misma lista ordenada por puntaje descendente y
    con la posicion sumada."""
    con_puntaje = [(v.get("aptitud"), v) for v in variantes if v.get("aptitud")]
    con_puntaje.sort(key=lambda t: t[0].puntaje, reverse=True)
    for i, (_, v) in enumerate(con_puntaje):
        v["ranking"] = i + 1
    return [v for _, v in con_puntaje]
