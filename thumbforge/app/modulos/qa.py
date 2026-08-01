"""M6 - control de calidad.

Mira las tres miniaturas como las va a ver la audiencia: chiquitas, en un
feed, entre otras cincuenta. Lo que se ve bien a 1280x720 en un monitor no
dice nada; lo que importa es si a 210x118 todavia se lee y todavia se
distingue de las otras dos.

Tres controles independientes:

1. Legibilidad real: contraste sobre la region del texto -no sobre el fondo
   promedio- y supervivencia del trazo al reescalado del feed.
2. Encuadre: si al desenfocar fuerte la silueta del sujeto desaparece, la
   miniatura no tiene sujeto, tiene textura.
3. Distancia entre variantes: si dos se parecen demasiado, el trabajo de
   ofrecer tres opciones fue en vano y se pide reemplazo a M4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .. import aptitud as apt
from .. import color as col
from .. import composicion as comp
from ..perfiles import Perfil
from ..rutas import dir_salida

TAMANO_FEED = (210, 118)


@dataclass
class InformeVariante:
    concepto_id: str
    ruta: Path
    contraste_peor: float
    contraste_p5: float
    contraste_promedio: float
    contraste_fraccion_ok: float
    contraste_minimo: float
    legibilidad: comp.Legibilidad
    desenfoque: comp.PruebaDesenfoque
    composicion: dict
    bytes: int
    hallazgos: list = field(default_factory=list)
    # Aptitud para el feed: score compuesto derivado de factores que la
    # evidencia sostiene (rostro con emocion, palabras cortas, contraste,
    # legibilidad a 210x118, armonia del skin). NO es CTR predicho: sin
    # datos propios del canal nadie predice CTR. Se muestra desglosado.
    aptitud: apt.Aptitud | None = None

    @property
    def ok(self) -> bool:
        return not self.hallazgos


@dataclass
class ParVariantes:
    a: str
    b: str
    distancia_histograma: float
    distancia_composicion: float
    delta_e_paleta: float
    demasiado_parecidas: bool
    motivo: str = ""


@dataclass
class InformeQA:
    perfil: str
    variantes: list = field(default_factory=list)
    pares: list = field(default_factory=list)
    generado_en: str = ""

    @property
    def ok(self) -> bool:
        return (all(v.ok for v in self.variantes)
                and not [p for p in self.pares if p.demasiado_parecidas])

    def a_reemplazar(self) -> list:
        """Conceptos que M4 tiene que reemplazar."""
        ids: list = []
        for par in self.pares:
            if par.demasiado_parecidas and par.b not in ids:
                # Se pide reemplazo de la segunda del par: la primera se
                # conserva para no tirar dos variantes por un solo choque.
                ids.append(par.b)
        for v in self.variantes:
            if not v.ok and v.concepto_id not in ids:
                ids.append(v.concepto_id)
        return ids


# --- controles por variante --------------------------------------------------
def revisar_variante(imagen: Image.Image, concepto_id: str, ruta: Path,
                     perfil: Perfil, mascara_texto: Image.Image | None = None,
                     color_texto: str | None = None,
                     bytes_: int = 0,
                     palabras_texto: int | None = None,
                     anotacion: dict | None = None) -> InformeVariante:
    pol_color = col.politica_color(perfil)
    pol_comp = comp.politica_composicion(perfil)
    minimo = pol_color.contraste_minimo

    # 1. Contraste del texto contra lo que lo rodea, pixel a pixel.
    #
    # Dos errores de medicion que hay que evitar a la vez. Medir contra el
    # color PROMEDIO del fondo miente: un texto claro sobre un fondo mitad
    # claro mitad oscuro promedia gris y aprueba, cuando la mitad clara es
    # ilegible. Y medir bajo la mascara del texto sobre la imagen YA
    # renderizada miente al reves: devuelve el color del propio texto y da
    # 1.00:1. Lo correcto es el anillo que rodea al trazo.
    if mascara_texto is not None and color_texto:
        anillo = comp.anillo_mascara(mascara_texto, radio=6, interior=2)
        informe = col.contraste_sobre_fondo(color_texto, imagen, anillo, minimo)
        if informe.muestras == 0:
            informe = col.contraste_sobre_fondo(color_texto, imagen,
                                                mascara_texto, minimo)
    else:
        informe = col.InformeContraste(0.0, 0.0, 0.0, 0.0, minimo, 0)

    legibilidad = comp.legibilidad_en_feed(
        imagen, mascara_texto, color_texto, tamano=TAMANO_FEED,
        minimo=pol_comp.legibilidad_feed_minima,
        alto_texto_minimo=pol_comp.alto_texto_feed_minimo)
    desenfoque = comp.prueba_desenfoque(
        imagen, minimo=pol_comp.retencion_desenfoque_minima)
    evaluacion = comp.evaluar_composicion(
        imagen, pol_comp, mascara_texto=mascara_texto, color_texto=color_texto)

    hallazgos: list = []
    # Se juzga por el percentil 5, no por el pixel peor. Sobre un borde
    # suavizado siempre hay algun pixel intermedio: exigir que el minimo se
    # cumpla en el 100% absoluto reprueba cualquier texto real y no dice nada
    # util. Que el 95% de lo que rodea al trazo llegue al minimo si.
    if informe.muestras and informe.percentil_5 < minimo:
        hallazgos.append(
            f"contraste del texto {informe.percentil_5:.2f}:1 en el percentil 5, "
            f"bajo el minimo {minimo:.1f}:1 del perfil (cumple en el "
            f"{informe.fraccion_ok:.0%} de lo que rodea al texto; peor pixel "
            f"{informe.peor:.2f}:1)")
    if not legibilidad.cumple:
        hallazgos.append(
            f"a {TAMANO_FEED[0]}x{TAMANO_FEED[1]} la legibilidad da "
            f"{legibilidad.puntaje:.2f}, bajo el minimo "
            f"{pol_comp.legibilidad_feed_minima:.2f}")
        hallazgos.extend(f"  {m}" for m in legibilidad.motivos)
    if not desenfoque.cumple:
        hallazgos.append(f"la silueta no sobrevive al desenfoque: {desenfoque.resumen()}")
    hallazgos.extend(h for h in evaluacion["hallazgos"]
                     if "legibilidad" not in h and "desenfoque" not in h)

    # Aptitud para el feed. La anotacion (M2) es opcional: si no llega, los
    # componentes que dependen de ella no se calculan y se dice en el motivo.
    an = anotacion or {}
    aptitud = apt.puntuar(
        imagen, perfil,
        mascara_texto=mascara_texto, color_texto=color_texto,
        palabras_texto=palabras_texto,
        emocion=an.get("emocion"), hay_rostro=an.get("rostro_humano"),
        mirada=an.get("mirada"))

    return InformeVariante(
        concepto_id=concepto_id, ruta=ruta,
        contraste_peor=informe.peor, contraste_p5=informe.percentil_5,
        contraste_promedio=informe.promedio,
        contraste_fraccion_ok=informe.fraccion_ok, contraste_minimo=minimo,
        legibilidad=legibilidad, desenfoque=desenfoque, composicion=evaluacion,
        bytes=bytes_, hallazgos=hallazgos, aptitud=aptitud)


# --- distancia entre variantes -----------------------------------------------
def _centro_composicion(imagen: Image.Image) -> tuple:
    m = comp.mapa_detalle(imagen)
    b = comp.balance(m)
    return (b.desvio_x, b.desvio_y, comp.espacio_negativo(m))


def comparar(a: Image.Image, b: Image.Image, id_a: str, id_b: str,
             delta_e_minimo: float, distancia_minima: float = 0.12) -> ParVariantes:
    """Dos variantes que se parecen demasiado no son dos opciones.

    Se miran tres cosas a la vez porque cada una sola se engana facil. Dos
    encuadres distintos con la misma paleta dan histogramas parecidos; la
    misma foto con otro texto da composiciones parecidas. Solo si las tres
    coinciden se declara duplicado.
    """
    d_hist = col.distancia_histograma(a, b)

    ca, cb = _centro_composicion(a), _centro_composicion(b)
    d_comp = (sum((x - y) ** 2 for x, y in zip(ca, cb))) ** 0.5

    pa = col.paleta_dominante(a, maximo=3)
    pb = col.paleta_dominante(b, maximo=3)
    if pa and pb:
        color_a = pa[0][0] if isinstance(pa[0], (tuple, list)) else pa[0]
        color_b = pb[0][0] if isinstance(pb[0], (tuple, list)) else pb[0]
        d_color = col.delta_e(color_a, color_b)
    else:
        d_color = 0.0

    parecidas = (d_hist < distancia_minima
                 and d_comp < 0.25
                 and d_color < delta_e_minimo)
    motivo = ""
    if parecidas:
        motivo = (f"histograma {d_hist:.3f} (< {distancia_minima}), composicion "
                  f"{d_comp:.3f} (< 0.25) y delta E {d_color:.1f} "
                  f"(< {delta_e_minimo:.1f}): son la misma miniatura con otro texto")
    return ParVariantes(id_a, id_b, d_hist, d_comp, d_color, parecidas, motivo)


# --- entrada publica ---------------------------------------------------------
def revisar(resultados: list, perfil: Perfil) -> InformeQA:
    """Revisa los ResultadoRender de M5 y devuelve el informe."""
    pol_color = col.politica_color(perfil)
    informe = InformeQA(
        perfil=perfil.slug,
        generado_en=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    imagenes: dict = {}
    for r in resultados:
        imagen = r.imagen if r.imagen is not None else Image.open(r.ruta).convert("RGB")
        imagenes[r.concepto_id] = imagen
        palabras = len((r.bloque.lineas or []) and " ".join(r.bloque.lineas).split()) \
            if getattr(r, "bloque", None) else None
        informe.variantes.append(revisar_variante(
            imagen, r.concepto_id, r.ruta, perfil,
            mascara_texto=r.mascara_texto,
            color_texto=r.decision_texto.color if r.decision_texto else None,
            bytes_=r.bytes,
            palabras_texto=palabras,
            anotacion=getattr(r, "anotacion", None)))

    ids = list(imagenes)
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1:]:
            informe.pares.append(comparar(
                imagenes[id_a], imagenes[id_b], id_a, id_b,
                pol_color.delta_e_minimo_entre_variantes))

    return informe


def render_markdown(informe: InformeQA) -> str:
    lineas = [
        f"# QA de miniaturas - perfil `{informe.perfil}`",
        "",
        f"Generado el {informe.generado_en}.",
        "",
        "Las miniaturas se evaluan **al tamano real del feed movil "
        f"({TAMANO_FEED[0]}x{TAMANO_FEED[1]})**, no al tamano de edicion. El "
        "contraste se mide sobre los pixeles que ocupa el texto, no sobre el "
        "color promedio del fondo: un texto claro sobre un fondo mitad claro "
        "mitad oscuro promedia gris y aprobaria, cuando la mitad clara es "
        "ilegible.",
        "",
        f"**Resultado: {'aprobado' if informe.ok else 'con rechazos'}.**",
        "",
        "## Por variante",
        "",
    ]

    for v in informe.variantes:
        lineas.append(f"### {v.concepto_id} - {'OK' if v.ok else 'RECHAZADA'}")
        lineas.append("")
        lineas.append(f"- archivo: `{v.ruta.name}` ({v.bytes:,} bytes)")
        if v.contraste_p5 or v.contraste_peor:
            lineas.append(
                f"- contraste del texto contra lo que lo rodea: "
                f"percentil 5 **{v.contraste_p5:.2f}:1** (es el que decide), "
                f"promedio {v.contraste_promedio:.2f}:1, peor pixel "
                f"{v.contraste_peor:.2f}:1; cumple en el "
                f"{v.contraste_fraccion_ok:.0%} de la region "
                f"(minimo del perfil {v.contraste_minimo:.1f}:1)")
        lineas.append(
            f"- legibilidad en feed: {v.legibilidad.puntaje:.2f} "
            f"(minimo {v.legibilidad.minimo:.2f}), alto del texto reducido "
            f"{v.legibilidad.alto_texto_px:.1f} px")
        lineas.append(f"- prueba de desenfoque: {v.desenfoque.resumen()}")
        lineas.append(
            f"- espacio negativo: {v.composicion['espacio_negativo']:.2f}")
        if v.hallazgos:
            lineas.append("- hallazgos:")
            lineas.extend(f"  - {h}" for h in v.hallazgos)
        if v.aptitud and v.aptitud.componentes:
            lineas.append(
                f"- **aptitud para el feed: {v.aptitud.puntaje:.0f}/100**  "
                f"(no es CTR predicho; sin datos propios nadie predice CTR)")
            for c in v.aptitud.componentes:
                lineas.append(
                    f"  - {c.nombre}: {c.puntaje * 100:.0f}/100  "
                    f"(peso {c.peso:.0%}) - {c.motivo}")
        lineas.append("")

    lineas += ["## Aptitud para el feed - por que este score",
               "",
               "El puntaje resume que tan bien chequea cada variante contra los "
               "factores que la evidencia externa cross-referenciada sostiene: "
               "rostros con emocion legible, textos cortos (<4 palabras), "
               "contraste alto (Vidooly y otros: ~30% mas de CTR), y sobre todo "
               "legibilidad al tamano real del feed movil, que es donde ocurren "
               "el 70%+ de las decisiones de click.",
               "",
               "**Lo que este numero NO es**: no es CTR predicho. Sin datos "
               "propios del canal -export de YouTube Studio Modo Avanzado a "
               "`corpus/mi_ctr.csv`- nadie predice CTR real de una miniatura. "
               "Cualquier herramienta que diga hacerlo esta vendiendo humo. Con "
               "esos datos M3 saca reglas propias y M4 las cita en cada concepto; "
               "M6 usa ese puntaje solo como comparador entre las variantes de "
               "esta misma corrida y como red de deteccion de miniaturas flojas.",
               "",
               "## Distancia entre variantes", "",
               "Tres opciones que se parecen no son tres opciones. Se compara "
               "histograma, composicion y paleta a la vez: cada medida por "
               "separado se engana facil.", "",
               "| par | histograma | composicion | delta E | veredicto |",
               "|---|---|---|---|---|"]
    for p in informe.pares:
        lineas.append(
            f"| {p.a} vs {p.b} | {p.distancia_histograma:.3f} | "
            f"{p.distancia_composicion:.3f} | {p.delta_e_paleta:.1f} | "
            f"{'DEMASIADO PARECIDAS' if p.demasiado_parecidas else 'distintas'} |")
    lineas.append("")

    reemplazos = informe.a_reemplazar()
    if reemplazos:
        lineas += ["## Reemplazos pedidos a M4", "",
                   "Estos conceptos hay que rehacerlos:", ""]
        for cid in reemplazos:
            motivos = [p.motivo for p in informe.pares
                       if p.demasiado_parecidas and p.b == cid]
            motivos += [h for v in informe.variantes
                        if v.concepto_id == cid for h in v.hallazgos]
            lineas.append(f"- **{cid}**: {motivos[0] if motivos else 'no cumple'}")
        lineas.append("")

    return "\n".join(lineas)


def escribir_qa(informe: InformeQA, ruta: Path | None = None) -> Path:
    ruta = ruta or (dir_salida() / "qa.md")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(render_markdown(informe), "utf-8")
    return ruta
