"""M5 - render."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app import composicion as comp
from app import perfiles as mod_perfiles
from app.cache import Cache
from app.modulos import render

EJEMPLOS = Path(__file__).resolve().parent.parent / "ejemplos"


def base_con_estructura(tamano=(1600, 900)) -> Image.Image:
    """Una base con un sujeto claro y un fondo degradado."""
    img = Image.new("RGB", tamano, "#123a5a")
    d = ImageDraw.Draw(img)
    for y in range(tamano[1]):
        d.line([(0, y), (tamano[0], y)],
               fill=(18 + y // 12, 58 + y // 14, max(0, 90 - y // 20)))
    d.ellipse([tamano[0] * 0.58, tamano[1] * 0.12,
               tamano[0] * 0.94, tamano[1] * 0.62], fill="#e8b923")
    return img


@pytest.fixture
def base_png(tmp_path) -> Path:
    ruta = tmp_path / "base.png"
    base_con_estructura().save(ruta)
    return ruta


@pytest.fixture
def concepto() -> dict:
    return json.loads((EJEMPLOS / "conceptos_aviacion.json").read_text("utf-8"))[0]


def test_produce_un_jpg_valido_del_tamano_del_lienzo(tmp_path, base_png, concepto):
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / "salida")
    assert r.ruta.is_file()
    with Image.open(r.ruta) as img:
        assert img.format == "JPEG"
        assert img.size == (perfil.get_skin("lienzo.ancho"),
                            perfil.get_skin("lienzo.alto"))


def test_pesa_menos_de_dos_megas(tmp_path, base_png, concepto):
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / "salida")
    assert r.bytes < render.LIMITE_BYTES


def test_la_calidad_baja_hasta_entrar_en_el_limite(tmp_path):
    """Con un limite absurdo, la iteracion tiene que bajar la calidad."""
    img = base_con_estructura((1280, 720))
    ruta = tmp_path / "chica.jpg"
    bytes_, calidad = render.guardar_jpg(img, ruta, limite=20_000)
    assert calidad < render.CALIDADES[0]
    assert ruta.is_file()


def _proporcion_de_la_marca(imagen: Image.Image) -> float:
    """Ancho/alto de la mancha oscura dibujada sobre fondo claro."""
    caja = imagen.convert("L").point(lambda v: 255 if v < 40 else 0).getbbox()
    return (caja[2] - caja[0]) / float(caja[3] - caja[1])


def test_normalizar_recorta_en_vez_de_deformar(tmp_path):
    """Un rostro estirado se nota; un recorte no.

    Se dibuja una marca de proporcion conocida sobre una imagen de relacion
    de aspecto muy distinta a la del lienzo: si la normalizacion escalara los
    dos ejes por separado, la proporcion de la marca cambiaria.
    """
    ancha = Image.new("RGB", (2000, 500), "#ffffff")
    ImageDraw.Draw(ancha).ellipse([900, 100, 1100, 400], fill="#000000")
    antes = _proporcion_de_la_marca(ancha)

    salida = render.normalizar_lienzo(ancha, 1280, 720)
    assert salida.size == (1280, 720)
    despues = _proporcion_de_la_marca(salida)

    assert abs(despues - antes) <= 0.05, (
        f"la marca paso de una proporcion {antes:.3f} a {despues:.3f}: "
        f"se deformo en vez de recortarse")


def test_el_texto_no_invade_las_zonas_seguras(tmp_path, base_png, concepto):
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / "salida")
    zonas = comp.zonas_seguras_de_skin(perfil, 1280, 720)
    ok, invadidas = comp.respeta_zonas_seguras(r.caja_texto, zonas)
    assert ok, f"el texto pisa {invadidas}"


def test_respeta_la_posicion_de_texto_que_pide_el_skin(tmp_path, base_png, concepto):
    """aviacion_historica pide izq_inf: el texto tiene que caer abajo a la
    izquierda, no en cualquier lado."""
    perfil = mod_perfiles.cargar_perfil("gdc")
    assert perfil.get_skin("texto.posicion") == "izq_inf"
    r = render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / "salida")
    cx, cy = r.caja_texto.centro
    assert cx < 640, f"el texto quedo a la derecha: {r.caja_texto}"
    assert cy > 300, f"el texto quedo arriba: {r.caja_texto}"


def test_el_render_rechaza_un_concepto_que_viola_la_politica(tmp_path, base_png):
    """M4 deberia frenarlo antes, pero M5 tambien se puede invocar solo."""
    perfil = mod_perfiles.cargar_perfil("true_crime")
    concepto = json.loads(
        (EJEMPLOS / "conceptos_true_crime.json").read_text("utf-8"))[1]
    with pytest.raises(render.ErrorRender) as exc:
        render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / "salida")
    mensaje = str(exc.value)
    assert "ia_sobre_persona_real" in mensaje
    assert "derecho de imagen" in mensaje


def test_sin_imagen_local_dice_que_falta(tmp_path, concepto):
    perfil = mod_perfiles.cargar_perfil("gdc")
    with pytest.raises(render.ErrorRender) as exc:
        render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          salida=tmp_path / "salida")
    assert "--imagen" in str(exc.value)


def test_escribe_creditos_con_la_licencia_declarada(tmp_path, base_png, concepto):
    perfil = mod_perfiles.cargar_perfil("gdc")
    r = render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / "salida")
    ruta = render.escribir_creditos(r.atribuciones, tmp_path / "creditos.txt")
    texto = ruta.read_text("utf-8")
    assert r.concepto_id in texto
    assert "licencia" in texto
    # El motor registra lo declarado; no verifica derechos, y lo dice.
    assert "no verifica derechos" in texto


@pytest.mark.parametrize("slug", ["aviacion_historica", "true_crime", "tech_reviews"])
def test_los_tres_perfiles_renderizan_con_su_propio_skin(tmp_path, base_png, slug):
    """Mismo motor, tres identidades visuales, cero ramas por nicho."""
    perfil = mod_perfiles.cargar_perfil(slug)
    concepto = {
        "id": f"c-{slug}",
        "copy": {"texto": "Prueba de render", "nombre_reconocible": "Prueba",
                 "producto": "Prueba"},
        "base_visual": {"origen": perfil.get("politica_base_visual.orden_preferencia")[0],
                        "categoria": "textura", "licencia": "CC0"},
        "capas": [],
    }
    r = render.renderizar(concepto, perfil, Cache(tmp_path / "c"),
                          imagen_local=base_png, salida=tmp_path / slug)
    assert r.ruta.is_file()
    assert r.bytes < render.LIMITE_BYTES


def test_el_ajuste_de_texto_baja_el_cuerpo_hasta_entrar(tmp_path):
    perfil = mod_perfiles.cargar_perfil("gdc")
    fuente = perfil.fuente("titular")
    corto = render.ajustar_texto("Dos", fuente, 700, 300, 128, 48)
    largo = render.ajustar_texto(
        "Un copy mucho mas largo que no entra de ninguna manera en una linea",
        fuente, 700, 300, 128, 48)
    assert corto.tamano >= largo.tamano
    assert len(largo.lineas) > len(corto.lineas)
    assert largo.ancho <= 700 or largo.tamano == 48
