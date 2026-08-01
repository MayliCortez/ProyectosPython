"""Panel HTML de preview: como se veria en el feed movil de YouTube.

Herramientas como TubeBuddy o ViewStats muestran las variantes GRANDES en su
interfaz, que es el error. La decision de clic ocurre a 210x113 en un
telefono, apretado entre otras miniaturas.

Este panel muestra las variantes al tamano real del feed, junto a
miniaturas de referencia grises que simulan el ruido de la interfaz, y
adentro un boton para verlas grandes al tamano de edicion. Es lo que
MrBeast paga por ver antes de publicar.

El HTML sale autocontenido y monotema oscuro a proposito: el feed de
YouTube en movil es oscuro por defecto y ese es el contexto que importa.
"""

from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..rutas import dir_salida

TAMANO_FEED = (210, 118)
TAMANO_EDICION = (480, 270)  # se ve grande en el panel; abre a 1280x720 en nueva pestana


def _b64(imagen: Image.Image, tamano: tuple) -> str:
    """Data URI con la imagen reescalada al tamano pedido."""
    chica = imagen.convert("RGB").resize(tamano, Image.LANCZOS)
    buf = io.BytesIO()
    chica.save(buf, "JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _b64_completa(ruta: Path) -> str:
    """La imagen sin reescalar, para el modal a 1280x720."""
    return "data:image/jpeg;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def _distractoras(cantidad: int = 5) -> list[str]:
    """Cuadros grises con textura para simular otras miniaturas del feed.

    Sin foto real: no queremos que el operador se distraiga leyendo un titulo
    ajeno. Solo el ruido visual que hace que su miniatura se compare.
    """
    from PIL import ImageDraw

    salidas: list[str] = []
    grises = [(46, 46, 52), (62, 58, 55), (52, 55, 60), (58, 62, 58), (48, 50, 58)]
    for i in range(cantidad):
        base = grises[i % len(grises)]
        img = Image.new("RGB", TAMANO_FEED, base)
        d = ImageDraw.Draw(img)
        # unas bandas oblicuas para dar textura sin figuratividad
        for j in range(-40, TAMANO_FEED[0] + 40, 24):
            d.line([(j, 0), (j + 60, TAMANO_FEED[1])],
                   fill=tuple(min(255, c + 6) for c in base), width=1)
        # una barra inferior tipo badge de duracion
        d.rectangle([TAMANO_FEED[0] - 30, TAMANO_FEED[1] - 14,
                     TAMANO_FEED[0] - 6, TAMANO_FEED[1] - 4],
                    fill=(20, 20, 24))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82)
        salidas.append("data:image/jpeg;base64,"
                       + base64.b64encode(buf.getvalue()).decode("ascii"))
    return salidas


# --- html --------------------------------------------------------------------
def _card(variante: dict) -> str:
    """Una tarjeta del panel principal: la variante al tamano de edicion,
    su score, su desglose y los datos que M6 registro."""
    v = variante
    thumb = variante["thumb_edicion"]
    feed = variante["thumb_feed"]
    apti = v.get("aptitud")
    puntaje = f"{apti.puntaje:.0f}" if apti else "-"
    color_score = ("aprobada" if v.get("ok") else "rechazada")

    hallazgos = "".join(
        f"<li>{html.escape(h)}</li>" for h in v.get("hallazgos") or [])
    hallazgos_html = (f'<details class="hallazgos"><summary>'
                      f'{len(v.get("hallazgos") or [])} hallazgo(s) del QA</summary>'
                      f'<ul>{hallazgos}</ul></details>') if hallazgos else ""

    componentes = ""
    if apti:
        for c in apti.componentes:
            ancho = int(round(c.puntaje * 100))
            componentes += (
                f'<div class="comp"><div class="comp-head">'
                f'<span class="comp-nombre">{html.escape(c.nombre)}</span>'
                f'<span class="comp-peso">peso {int(c.peso*100)}%</span>'
                f'<span class="comp-puntaje">{int(c.puntaje*100)}</span>'
                f'</div><div class="barra"><div class="barra-fill" '
                f'style="width:{ancho}%"></div></div>'
                f'<p class="comp-motivo">{html.escape(c.motivo)}</p></div>')

    return f'''<article class="variante {color_score}">
  <header>
    <h2>{html.escape(v["id"])}</h2>
    <div class="score" data-estado="{color_score}">
      <span class="score-num">{puntaje}</span>
      <span class="score-den">/100</span>
    </div>
  </header>
  <a class="thumb-grande" href="{v["thumb_completa"]}" target="_blank"
     title="Abrir a 1280x720 en nueva pestana">
    <img src="{thumb}" width="{TAMANO_EDICION[0]}" height="{TAMANO_EDICION[1]}"
         alt="Miniatura {html.escape(v["id"])}">
    <span class="lupa">Ver a tamano completo</span>
  </a>
  <div class="feed-preview" aria-label="Como se veria en el feed movil">
    <span class="feed-label">Asi se ve en el feed movil (210x118):</span>
    <div class="feed-fila">
      {v["distractor_izq"]}
      <img class="miniatura-real" src="{feed}"
           width="{TAMANO_FEED[0]}" height="{TAMANO_FEED[1]}"
           alt="Preview en feed">
      {v["distractor_der"]}
    </div>
  </div>
  <section class="componentes">{componentes}</section>
  {hallazgos_html}
</article>'''


def construir(informe, resultados, salida: Path | None = None) -> Path:
    """Genera panel.html a partir del InformeQA y los ResultadoRender.

    informe: qa.InformeQA
    resultados: lista de render.ResultadoRender
    """
    salida = salida or (dir_salida() / "panel.html")

    # Distractoras compartidas: la misma coleccion para las tres, asi el
    # comparador es honesto.
    distractoras = _distractoras(6)
    variantes_html = []

    por_id = {r.concepto_id: r for r in resultados}
    for i, v in enumerate(informe.variantes):
        r = por_id.get(v.concepto_id)
        if r is None:
            continue
        imagen = r.imagen if r.imagen is not None else Image.open(r.ruta).convert("RGB")
        datos = {
            "id": v.concepto_id,
            "ok": v.ok,
            "hallazgos": v.hallazgos,
            "aptitud": v.aptitud,
            "thumb_edicion": _b64(imagen, TAMANO_EDICION),
            "thumb_feed": _b64(imagen, TAMANO_FEED),
            "thumb_completa": _b64_completa(r.ruta),
            "distractor_izq": (f'<img class="distractor" src="{distractoras[i*2 % len(distractoras)]}" '
                               f'width="{TAMANO_FEED[0]}" height="{TAMANO_FEED[1]}" alt="">'),
            "distractor_der": (f'<img class="distractor" src="{distractoras[(i*2+1) % len(distractoras)]}" '
                               f'width="{TAMANO_FEED[0]}" height="{TAMANO_FEED[1]}" alt="">'),
        }
        variantes_html.append(_card(datos))

    # Comparativa a-b-c en un solo bloque, para elegir la que llevar a
    # YouTube Test & Compare.
    pares_html = ""
    if informe.pares:
        filas = "".join(
            f'<tr><td>{html.escape(p.a)} vs {html.escape(p.b)}</td>'
            f'<td>{p.distancia_histograma:.3f}</td>'
            f'<td>{p.distancia_composicion:.3f}</td>'
            f'<td>{p.delta_e_paleta:.1f}</td>'
            f'<td class="{("mala" if p.demasiado_parecidas else "buena")}">'
            f'{"demasiado parecidas" if p.demasiado_parecidas else "distintas"}</td></tr>'
            for p in informe.pares)
        pares_html = f'''
<section class="distancia">
  <h2>Distancia entre variantes</h2>
  <p>Tres opciones que se parecen no son tres opciones. Se comparan
     histograma, composicion y paleta a la vez: cada medida por separado se
     engana facil.</p>
  <table>
    <thead><tr><th>par</th><th>histograma</th><th>composicion</th>
    <th>&Delta;E</th><th>veredicto</th></tr></thead>
    <tbody>{filas}</tbody>
  </table>
</section>'''

    generado = datetime.now(timezone.utc).isoformat(timespec="seconds")
    html_doc = _plantilla(
        perfil=informe.perfil, generado=generado,
        cuerpo="\n".join(variantes_html), pares=pares_html)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html_doc, "utf-8")
    return salida


# --- plantilla: contenido y estilos ------------------------------------------
def _plantilla(perfil: str, generado: str, cuerpo: str, pares: str) -> str:
    return f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>thumbforge — panel del perfil {html.escape(perfil)}</title>
<style>
:root {{
  --tinta: #f5f2eb;
  --tinta-suave: #b8b3a6;
  --tinta-marca: #78706060;
  --fondo: #14120f;
  --fondo-carta: #1c1a15;
  --fondo-carta-alta: #24211b;
  --acento: #d94b1f;
  --acento-suave: #f7a06b;
  --ok: #3f8f5c;
  --mala: #b0463e;
  --barra: #2e2b25;
  --barra-fill: #7d6c4a;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; }}
body {{
  background: var(--fondo);
  color: var(--tinta);
  font: 15px/1.5 'IBM Plex Sans', 'Helvetica Neue', system-ui, sans-serif;
  padding: 40px 24px 80px;
}}
header.panel {{
  max-width: 1280px;
  margin: 0 auto 48px;
  border-bottom: 1px solid var(--tinta-marca);
  padding-bottom: 24px;
}}
header.panel .eyebrow {{
  color: var(--acento-suave);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-size: 12px;
  font-weight: 600;
}}
header.panel h1 {{
  margin: 8px 0 4px;
  font: 700 clamp(28px, 4vw, 44px)/1.1 'IBM Plex Serif', Georgia, serif;
  text-wrap: balance;
}}
header.panel h1 code {{
  font-family: 'IBM Plex Mono', 'Menlo', monospace;
  background: var(--fondo-carta);
  padding: 0 10px;
  border-radius: 4px;
  color: var(--acento-suave);
}}
header.panel .fecha {{ color: var(--tinta-suave); font-size: 13px; }}

.aviso {{
  max-width: 1280px;
  margin: 0 auto 32px;
  padding: 16px 20px;
  background: var(--fondo-carta);
  border-left: 3px solid var(--acento);
  color: var(--tinta-suave);
  font-size: 13.5px;
}}
.aviso strong {{ color: var(--tinta); }}

main.rejilla {{
  max-width: 1280px;
  margin: 0 auto;
  display: grid;
  gap: 28px;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
}}

article.variante {{
  background: var(--fondo-carta);
  border-radius: 6px;
  padding: 20px 22px 22px;
  border: 1px solid transparent;
}}
article.variante.rechazada {{ border-color: #b0463e40; }}
article.variante header {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 14px;
}}
article.variante h2 {{
  margin: 0;
  font: 600 15px/1 'IBM Plex Mono', monospace;
  letter-spacing: 0.02em;
}}
.score {{ font-variant-numeric: tabular-nums; }}
.score .score-num {{
  font: 700 34px/1 'IBM Plex Serif', Georgia, serif;
}}
.score .score-den {{ color: var(--tinta-suave); font-size: 14px; }}
.score[data-estado="rechazada"] .score-num {{ color: var(--mala); }}
.score[data-estado="aprobada"] .score-num {{ color: var(--ok); }}

.thumb-grande {{
  display: block;
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 4px;
  background: #000;
}}
.thumb-grande img {{ display: block; width: 100%; height: auto; }}
.thumb-grande .lupa {{
  position: absolute;
  bottom: 8px; right: 8px;
  padding: 4px 10px;
  background: #000c;
  color: var(--tinta);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  opacity: 0;
  transition: opacity .18s ease;
}}
.thumb-grande:hover .lupa,
.thumb-grande:focus-visible .lupa {{ opacity: 1; }}

.feed-preview {{
  margin: 16px 0 18px;
}}
.feed-label {{
  display: block;
  color: var(--tinta-suave);
  font-size: 11.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 6px;
}}
.feed-fila {{
  display: grid;
  grid-template-columns: 210px 210px 210px;
  gap: 6px;
  overflow-x: auto;
  padding: 6px;
  background: #000;
  border-radius: 4px;
}}
.feed-fila img {{ display: block; border-radius: 2px; }}
.feed-fila .miniatura-real {{
  outline: 2px solid var(--acento);
  outline-offset: 1px;
}}
.feed-fila .distractor {{ opacity: 0.55; }}

.componentes {{ margin-top: 10px; }}
.comp {{
  padding: 10px 0;
  border-top: 1px solid var(--fondo-carta-alta);
}}
.comp:first-child {{ border-top: none; }}
.comp-head {{
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 10px;
  align-items: baseline;
  font-size: 13px;
}}
.comp-nombre {{ font-family: 'IBM Plex Mono', monospace; }}
.comp-peso {{ color: var(--tinta-suave); font-size: 11.5px; }}
.comp-puntaje {{
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  min-width: 3ch;
  text-align: right;
}}
.barra {{
  height: 4px;
  background: var(--barra);
  border-radius: 2px;
  margin: 6px 0 6px;
  overflow: hidden;
}}
.barra-fill {{
  height: 100%;
  background: linear-gradient(90deg, var(--acento) 0%, var(--acento-suave) 100%);
}}
.comp-motivo {{
  margin: 0;
  color: var(--tinta-suave);
  font-size: 12.5px;
  line-height: 1.4;
}}

details.hallazgos {{
  margin-top: 14px;
  padding: 12px 14px;
  background: #b0463e18;
  border-radius: 4px;
  font-size: 13px;
}}
details.hallazgos summary {{
  cursor: pointer;
  color: var(--mala);
  font-weight: 600;
  list-style: none;
}}
details.hallazgos summary::-webkit-details-marker {{ display: none; }}
details.hallazgos ul {{ margin: 10px 0 2px; padding-left: 20px; }}
details.hallazgos li {{ margin-bottom: 4px; }}

section.distancia {{
  max-width: 1280px;
  margin: 40px auto 0;
  padding-top: 32px;
  border-top: 1px solid var(--tinta-marca);
}}
section.distancia h2 {{
  font: 600 22px/1.2 'IBM Plex Serif', Georgia, serif;
  margin: 0 0 10px;
}}
section.distancia p {{
  color: var(--tinta-suave);
  max-width: 62ch;
  margin-bottom: 20px;
}}
section.distancia table {{
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
  font-size: 13.5px;
}}
section.distancia th, section.distancia td {{
  text-align: left;
  padding: 10px 8px;
  border-bottom: 1px solid var(--fondo-carta-alta);
}}
section.distancia th {{
  color: var(--tinta-suave);
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-size: 11px;
}}
td.buena {{ color: var(--ok); }}
td.mala {{ color: var(--mala); font-weight: 600; }}

footer {{
  max-width: 1280px;
  margin: 60px auto 0;
  padding-top: 24px;
  border-top: 1px solid var(--tinta-marca);
  color: var(--tinta-suave);
  font-size: 12px;
}}
</style>
</head>
<body>
<header class="panel">
  <p class="eyebrow">Panel de decision</p>
  <h1>Perfil <code>{html.escape(perfil)}</code></h1>
  <p class="fecha">Generado el {html.escape(generado)}</p>
</header>

<div class="aviso">
  <p>El puntaje de aptitud <strong>no es CTR predicho</strong>. Sin datos
  propios del canal -export de YouTube Studio Modo Avanzado a
  <code>corpus/mi_ctr.csv</code>- nadie predice CTR real. Sirve para elegir
  entre las tres variantes de esta corrida y para detectar miniaturas
  flojas antes de publicar.</p>
</div>

<main class="rejilla">
{cuerpo}
</main>

{pares}

<footer>
  Cada preview se muestra a 210x118, que es el tamano real del feed movil
  donde el 70%+ del trafico decide el click. El recuadro naranja marca
  cual de las tres es la miniatura real, entre placeholders grises que
  simulan otras miniaturas del feed. Para YouTube Test &amp; Compare,
  llevate las dos o tres de mayor puntaje &mdash; YouTube elige la
  ganadora por watch time, no por CTR.
</footer>
</body>
</html>'''
