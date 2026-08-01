"""M6 - control de calidad."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import color as col
from app import composicion as comp
from app import perfiles as mod_perfiles
from app.modulos import qa


def _fuente(perfil, tamano=110):
    return ImageFont.truetype(str(perfil.fuente("titular")), tamano)


def render_falso(perfil, texto="Texto de prueba", fondo="#0a1f3d",
                 color_texto="#f4efe2", contorno=0, ruta=Path("falsa.jpg")):
    """Una miniatura compuesta a mano, con su mascara de texto.

    Devuelve un objeto con la misma forma que el ResultadoRender de M5, que
    es lo unico que M6 necesita.
    """
    imagen = Image.new("RGB", (1280, 720), fondo)
    ImageDraw.Draw(imagen).ellipse([760, 90, 1180, 510], fill="#e8b923")
    fuente = _fuente(perfil)

    mascara = Image.new("L", (1280, 720), 0)
    ImageDraw.Draw(mascara).text((90, 430), texto, font=fuente, fill=255)
    d = ImageDraw.Draw(imagen)
    d.text((90, 430), texto, font=fuente, fill=color_texto,
           stroke_width=contorno, stroke_fill="#000000")

    class _Falso:
        pass

    r = _Falso()
    r.concepto_id = texto[:12]
    r.ruta = ruta
    r.bytes = 100_000
    r.imagen = imagen
    r.mascara_texto = mascara

    class _Dec:
        color = color_texto
    r.decision_texto = _Dec()
    return r


# --- el bug que hay que no repetir -------------------------------------------
def test_el_contraste_no_se_mide_contra_el_propio_texto():
    """Regresion: medir bajo la mascara sobre la imagen YA renderizada
    devuelve el color del texto y da 1.00:1 -el texto contra si mismo-, que
    parece un fallo total de contraste y es un error de medicion."""
    perfil = mod_perfiles.cargar_perfil("gdc")
    # Texto corto a proposito: tiene que caer entero sobre el fondo negro y
    # no rozar la mancha clara de la derecha, o la medicion seria de otra
    # cosa.
    r = render_falso(perfil, texto="BLANCO", fondo="#000000",
                     color_texto="#ffffff")
    informe = qa.revisar_variante(r.imagen, "c1", r.ruta, perfil,
                                  r.mascara_texto, r.decision_texto.color)
    # Blanco sobre negro es el contraste maximo posible: 21:1.
    assert informe.contraste_p5 > 15, (
        f"se midio {informe.contraste_p5:.2f}:1 para blanco sobre negro; "
        f"si da ~1.00 se esta midiendo el texto contra si mismo")


def test_detecta_texto_claro_sobre_una_mancha_clara():
    """El caso que justifica medir sobre la region del texto: un copy largo
    que empieza sobre fondo oscuro y termina cruzando una zona clara. El
    promedio del fondo aprueba; el tramo que cruza la mancha es ilegible."""
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render_falso(perfil, texto="TEXTO LARGO QUE CRUZA", fondo="#000000",
                     color_texto="#ffffff")
    informe = qa.revisar_variante(r.imagen, "c1", r.ruta, perfil,
                                  r.mascara_texto, r.decision_texto.color)
    assert informe.contraste_promedio > informe.contraste_p5, (
        "el promedio tiene que ser mejor que el percentil 5: si fueran "
        "iguales, el texto no estaria cruzando nada")
    assert not informe.ok


def test_el_anillo_excluye_el_trazo_y_su_antialias():
    mascara = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(mascara).rectangle([80, 80, 120, 120], fill=255)
    anillo = comp.anillo_mascara(mascara, radio=6, interior=2)

    # Nada del anillo cae sobre el trazo.
    solape = Image.composite(mascara, Image.new("L", (200, 200), 0), anillo)
    assert solape.getbbox() is None
    # Y el anillo existe.
    assert anillo.getbbox() is not None


def test_detecta_texto_ilegible_por_bajo_contraste():
    perfil = mod_perfiles.cargar_perfil("gdc")
    # Gris sobre gris apenas distinto: el ojo no lo lee y el motor tampoco.
    r = render_falso(perfil, texto="CASI INVISIBLE", fondo="#808080",
                     color_texto="#8a8a8a")
    informe = qa.revisar_variante(r.imagen, "c1", r.ruta, perfil,
                                  r.mascara_texto, r.decision_texto.color)
    assert not informe.ok
    assert any("contraste" in h for h in informe.hallazgos)


def test_aprueba_texto_con_contraste_sobrado():
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render_falso(perfil, texto="SE LEE BIEN", fondo="#04101f",
                     color_texto="#ffffff", contorno=6)
    informe = qa.revisar_variante(r.imagen, "c1", r.ruta, perfil,
                                  r.mascara_texto, r.decision_texto.color)
    assert informe.contraste_p5 >= perfil.get_skin("colorimetria.contraste_minimo", 4.5)


# --- distancia entre variantes -----------------------------------------------
def test_dos_variantes_identicas_se_marcan_como_parecidas():
    perfil = mod_perfiles.cargar_perfil("gdc")
    a = render_falso(perfil, texto="Uno").imagen
    par = qa.comparar(a, a.copy(), "c1", "c2", delta_e_minimo=10.0)
    assert par.demasiado_parecidas
    assert "misma miniatura" in par.motivo


def test_dos_variantes_distintas_no_se_marcan():
    perfil = mod_perfiles.cargar_perfil("gdc")
    a = render_falso(perfil, texto="Uno", fondo="#0a1f3d").imagen
    b = render_falso(perfil, texto="Otro muy distinto", fondo="#5a1a0a").imagen
    par = qa.comparar(a, b, "c1", "c2", delta_e_minimo=10.0)
    assert not par.demasiado_parecidas


def test_el_mismo_fondo_con_otro_texto_sigue_siendo_duplicado():
    """El caso que importa: tres variantes que son la misma foto con el copy
    cambiado no son tres opciones."""
    perfil = mod_perfiles.cargar_perfil("gdc")
    a = render_falso(perfil, texto="Uno", fondo="#0a1f3d").imagen
    b = render_falso(perfil, texto="Dos", fondo="#0a1f3d").imagen
    par = qa.comparar(a, b, "c1", "c2", delta_e_minimo=10.0)
    assert par.demasiado_parecidas


# --- informe -----------------------------------------------------------------
def test_el_informe_pide_reemplazo_de_la_duplicada():
    perfil = mod_perfiles.cargar_perfil("gdc")
    r1 = render_falso(perfil, texto="Uno", fondo="#0a1f3d")
    r2 = render_falso(perfil, texto="Dos", fondo="#0a1f3d")
    r1.concepto_id, r2.concepto_id = "c1", "c2"
    informe = qa.revisar([r1, r2], perfil)
    assert not informe.ok
    assert "c2" in informe.a_reemplazar()
    # Se conserva una de las dos: rechazar las dos por un choque es tirar
    # trabajo bueno.
    assert "c1" not in [p.b for p in informe.pares if p.demasiado_parecidas]


def test_escribe_qa_md_con_lo_que_importa(tmp_path):
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render_falso(perfil, texto="SE LEE BIEN", fondo="#04101f",
                     color_texto="#ffffff", contorno=6)
    r.concepto_id = "c1"
    informe = qa.revisar([r], perfil)
    ruta = qa.escribir_qa(informe, tmp_path / "qa.md")
    texto = ruta.read_text("utf-8")
    assert "210x118" in texto           # el tamano real del feed
    assert "percentil 5" in texto       # el umbral que decide
    assert "c1" in texto


@pytest.mark.parametrize("slug", ["aviacion_historica", "true_crime", "tech_reviews"])
def test_cada_perfil_impone_su_propio_minimo_de_contraste(slug):
    """El umbral sale del skin, no del motor: true_crime exige mas que gdc."""
    perfil = mod_perfiles.cargar_perfil(slug)
    esperado = perfil.get_skin("colorimetria.contraste_minimo")
    r = render_falso(perfil, texto="Prueba")
    informe = qa.revisar_variante(r.imagen, "c1", r.ruta, perfil,
                                  r.mascara_texto, r.decision_texto.color)
    assert informe.contraste_minimo == pytest.approx(esperado)
