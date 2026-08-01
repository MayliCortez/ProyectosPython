"""Encuadre, ocupacion y enfoque.

Todas las imagenes se construyen en el momento: un fondo liso no tiene
detalle, un bloque de ruido si, y de esa diferencia salen todas las
mediciones. No hay assets nuevos en el repo.
"""

from __future__ import annotations

import random

import pytest
from PIL import Image, ImageDraw

from app import color as c
from app import composicion as comp
from app import perfiles as mod_perfiles

PERFILES = ("aviacion_historica", "true_crime", "tech_reviews")


# --- imagenes sinteticas -----------------------------------------------------
def liso(color="#0a1f3d", tamano=(640, 360)) -> Image.Image:
    return Image.new("RGB", tamano, color)


def ruido(tamano=(640, 360), semilla=7, bloque=8, fondo="#0a1f3d") -> Image.Image:
    """Textura de bloques al azar: sobrevive al reescalado del mapa."""
    rnd = random.Random(semilla)
    ancho = max(1, tamano[0] // bloque)
    alto = max(1, tamano[1] // bloque)
    chica = Image.new("RGB", (ancho, alto))
    chica.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                   for _ in range(ancho * alto)])
    grande = Image.new("RGB", tamano, fondo)
    grande.paste(chica.resize(tamano, Image.NEAREST), (0, 0))
    return grande


def mitad_ocupada(lado="izquierda", tamano=(640, 360)) -> Image.Image:
    """Una mitad con textura y la otra limpia."""
    img = liso("#0a1f3d", tamano)
    textura = ruido(tamano).crop((0, 0, tamano[0] // 2, tamano[1]))
    img.paste(textura, (0, 0) if lado == "izquierda" else (tamano[0] // 2, 0))
    return img


def sujeto_arriba_derecha(tamano=(640, 360)) -> Image.Image:
    img = liso("#0a1f3d", tamano)
    ImageDraw.Draw(img).ellipse([380, 40, 580, 240], fill="#e8b923")
    return img


def mascara_texto(tamano=(1280, 720), caja=(80, 480, 700, 620)) -> Image.Image:
    msk = Image.new("L", tamano, 0)
    ImageDraw.Draw(msk).rectangle(list(caja), fill=255)
    return msk


def mascara_filiforme(tamano=(1280, 720)) -> Image.Image:
    """Trazo de 1 px: el caso que el feed movil destruye."""
    msk = Image.new("L", tamano, 0)
    d = ImageDraw.Draw(msk)
    for y in range(480, 620, 6):
        d.line([(80, y), (700, y)], fill=255, width=1)
    return msk


# --- rejilla de tercios ------------------------------------------------------
def test_rejilla_de_tercios_en_el_lienzo_del_proyecto():
    r = comp.rejilla_tercios(1280, 720)
    assert r.verticales == [427, 853]
    assert r.horizontales == [240, 480]
    assert r.punto("superior_izquierdo") == (427, 240)
    assert r.punto("inferior_derecho") == (853, 480)
    assert set(r.puntos) == set(comp.PUNTOS_FUERTES)


def test_punto_fuerte_desconocido_explota():
    with pytest.raises(ValueError):
        comp.rejilla_tercios(1280, 720).punto("centro")


# --- zonas seguras -----------------------------------------------------------
def test_zonas_seguras_salen_de_los_porcentajes_pedidos():
    zonas = comp.zonas_seguras(1280, 720, 8, 18)
    barra = zonas["barra_progreso"]
    badge = zonas["badge_duracion"]
    assert (barra.x, barra.ancho) == (0, 1280)
    assert barra.alto == round(720 * 0.08)
    assert barra.y2 == 720
    assert (badge.ancho, badge.alto) == (round(1280 * 0.18), round(720 * 0.18))
    assert (badge.x2, badge.y2) == (1280, 720)


def test_los_porcentajes_valen_como_entero_o_como_fraccion():
    assert comp.zonas_seguras(1280, 720, 8, 18) == comp.zonas_seguras(1280, 720, 0.08, 0.18)


@pytest.mark.parametrize("slug", PERFILES)
def test_las_zonas_salen_del_skin_no_del_codigo(slug):
    perfil = mod_perfiles.cargar_perfil(slug)
    zonas = comp.zonas_seguras_de_skin(perfil)
    esperado = perfil.get_skin("zonas_seguras.inferior_pct")
    assert zonas["barra_progreso"].alto == round(720 * esperado / 100.0)


def test_un_skin_sin_zonas_declaradas_usa_los_defectos():
    zonas = comp.zonas_seguras_de_skin({})
    assert zonas["barra_progreso"].alto == round(720 * 0.08)


def test_deteccion_de_invasion():
    zonas = comp.zonas_seguras(1280, 720)
    dentro = comp.Caja(100, 100, 400, 200)
    encima_del_badge = comp.Caja(1100, 620, 150, 80)
    assert comp.respeta_zonas_seguras(dentro, zonas)[0]
    ok, invadidas = comp.respeta_zonas_seguras(encima_del_badge, zonas)
    assert not ok
    assert set(invadidas) == {"badge_duracion", "barra_progreso"}


def test_geometria_de_caja():
    a = comp.Caja(0, 0, 100, 100)
    b = comp.Caja(50, 50, 100, 100)
    assert a.area == 10000
    assert a.area_solapada(b) == 2500
    assert a.solape(b) == pytest.approx(0.25)
    assert a.centro == (50.0, 50.0)
    assert a.caja_pil() == (0, 0, 100, 100)
    assert a.dentro_de(100, 100) and not b.dentro_de(100, 100)


# --- mapa de detalle ---------------------------------------------------------
def test_un_fondo_liso_no_tiene_detalle():
    m = comp.mapa_detalle(liso())
    assert m.maximo == 0.0
    assert comp.espacio_negativo(m) == 1.0


def test_el_mapa_encuentra_la_mitad_ocupada():
    m = comp.mapa_detalle(mitad_ocupada("izquierda"))
    izquierda = comp.Caja(0, 0, 320, 360)
    derecha = comp.Caja(320, 0, 320, 360)
    assert m.detalle_en(izquierda) > 0.5
    assert m.detalle_en(derecha) < 0.1


def test_espacio_negativo_mide_la_mitad_limpia():
    m = comp.mapa_detalle(mitad_ocupada("derecha"))
    assert comp.espacio_negativo(m) == pytest.approx(0.5, abs=0.12)


def test_dimensiones_del_mapa():
    m = comp.mapa_detalle(liso(tamano=(1280, 720)), columnas=16, filas=9)
    assert (m.columnas, m.filas) == (16, 9)
    assert len(m.celdas) == 9 and len(m.celdas[0]) == 16
    assert (m.ancho, m.alto) == (1280, 720)
    assert m.celda_de(0, 0) == (0, 0)
    assert m.celda_de(1279, 719) == (15, 8)


# --- peso visual -------------------------------------------------------------
def test_el_peso_visual_detecta_hacia_donde_esta_corrido():
    izq = comp.balance(comp.mapa_detalle(mitad_ocupada("izquierda")))
    assert izq.desvio_x < -0.3 and izq.lado == "izquierda" and izq.desbalanceada
    der = comp.balance(comp.mapa_detalle(mitad_ocupada("derecha")))
    assert der.desvio_x > 0.3 and der.lado == "derecha"


def test_una_imagen_pareja_esta_equilibrada():
    b = comp.balance(comp.mapa_detalle(ruido()))
    assert not b.desbalanceada and b.lado == "equilibrada"


def test_el_umbral_de_desbalance_es_un_parametro():
    m = comp.mapa_detalle(mitad_ocupada("izquierda"))
    assert comp.balance(m, umbral=0.2).desbalanceada
    assert not comp.balance(m, umbral=0.9).desbalanceada


# --- separacion sujeto / fondo -----------------------------------------------
def test_un_sujeto_claro_sobre_fondo_oscuro_se_despega():
    s = comp.separacion_sujeto_fondo(sujeto_arriba_derecha())
    assert s.delta_e > 20
    assert s.contraste > 2
    assert s.cumple


def test_sin_sujeto_no_hay_separacion():
    s = comp.separacion_sujeto_fondo(liso())
    assert s.puntaje == 0.0 and not s.cumple


def test_el_minimo_de_separacion_lo_pone_quien_llama():
    img = sujeto_arriba_derecha()
    assert comp.separacion_sujeto_fondo(img, minimo=0.3).cumple
    assert not comp.separacion_sujeto_fondo(img, minimo=0.99).cumple


# --- prueba de desenfoque ----------------------------------------------------
def test_una_silueta_grande_sobrevive_al_desenfoque():
    p = comp.prueba_desenfoque(sujeto_arriba_derecha())
    assert p.cumple
    assert p.contraste_silueta > 1.5
    assert 0.0 <= p.retencion <= 1.0
    assert "desenfoque" in p.resumen()


def test_una_textura_sin_sujeto_no_sobrevive():
    """Ruido fino: mucho detalle, ninguna silueta. Al desenfocar no queda nada."""
    p = comp.prueba_desenfoque(ruido(bloque=4))
    assert p.retencion < 0.5
    assert not p.cumple


def test_la_prueba_devuelve_una_medida_y_no_solo_un_booleano():
    p = comp.prueba_desenfoque(sujeto_arriba_derecha())
    q = comp.prueba_desenfoque(ruido(bloque=4))
    assert p.puntaje > q.puntaje          # ordena, no solo aprueba o rechaza
    assert p.radio_px > 1


# --- legibilidad en el feed --------------------------------------------------
def test_un_titular_grueso_sobrevive_al_tamano_del_feed():
    img = Image.new("RGB", (1280, 720), "#0a1f3d")
    ImageDraw.Draw(img).ellipse([700, 80, 1200, 580], fill="#e8b923")
    msk = mascara_texto()
    l = comp.legibilidad_en_feed(img, msk, "#f4efe2")
    assert l.tamano == comp.TAMANO_FEED
    assert l.solidez_texto > 0.9
    assert l.alto_texto_px > 20
    assert l.cumple and not l.motivos


def test_un_trazo_de_un_pixel_desaparece_en_el_feed():
    img = Image.new("RGB", (1280, 720), "#0a1f3d")
    ImageDraw.Draw(img).ellipse([700, 80, 1200, 580], fill="#e8b923")
    l = comp.legibilidad_en_feed(img, mascara_filiforme(), "#f4efe2")
    assert l.solidez_texto < 0.5
    assert not l.cumple
    assert any("fina" in m for m in l.motivos)


def test_el_feed_delata_el_texto_sin_contraste():
    img = Image.new("RGB", (1280, 720), "#f2f2f2")
    l = comp.legibilidad_en_feed(img, mascara_texto(), "#ffffff", contraste_minimo=4.5)
    assert not l.cumple
    assert any("contra su fondo" in m for m in l.motivos)


def test_sin_mascara_solo_se_evalua_el_sujeto():
    l = comp.legibilidad_en_feed(sujeto_arriba_derecha())
    assert l.motivos == []
    assert 0.0 <= l.puntaje <= 1.0


# --- eleccion de la caja de texto --------------------------------------------
def test_la_caja_elegida_nunca_pisa_las_zonas_seguras():
    img = ruido(tamano=(1280, 720))
    zonas = comp.zonas_seguras(1280, 720)
    eleccion = comp.elegir_caja_texto(img, (520, 140), posicion_preferida="der_inf",
                                      zonas=zonas)
    assert comp.respeta_zonas_seguras(eleccion.caja, zonas)[0]
    assert eleccion.zonas_invadidas == []


def test_el_texto_se_va_a_la_mitad_limpia():
    eleccion = comp.elegir_caja_texto(mitad_ocupada("izquierda", (1280, 720)),
                                      (400, 120), alinear_a_tercios=False)
    assert eleccion.caja.centro[0] > 640
    assert eleccion.componentes["limpieza"] > 0.8


def test_respeta_la_posicion_que_pide_el_skin_cuando_todo_lo_demas_empata():
    img = liso(tamano=(1280, 720))
    for posicion, cuadrante in (("izq_inf", (0, 360)), ("der_sup", (640, 0))):
        eleccion = comp.elegir_caja_texto(img, (400, 120), posicion_preferida=posicion,
                                          alinear_a_tercios=False)
        cx, cy = eleccion.caja.centro
        assert (cx > 640) is (cuadrante[0] > 0)
        assert (cy > 360) is (cuadrante[1] > 0)


def test_no_tapa_el_punto_focal():
    img = liso(tamano=(1280, 720))
    foco = comp.rejilla_tercios(1280, 720).punto("inferior_izquierdo")
    eleccion = comp.elegir_caja_texto(img, (500, 200), punto_focal="inferior_izquierdo")
    assert not eleccion.caja.contiene(*foco)
    assert eleccion.componentes["foco_libre"] == 1.0


def test_prefiere_donde_el_texto_se_lee():
    """Mitad clara y mitad oscura, texto claro: tiene que irse a la oscura."""
    img = Image.new("RGB", (1280, 720), "#0a1f3d")
    ImageDraw.Draw(img).rectangle([640, 0, 1279, 719], fill="#f2f2f2")
    eleccion = comp.elegir_caja_texto(img, (400, 120), color_texto="#f4efe2",
                                      alinear_a_tercios=False)
    assert eleccion.caja.centro[0] < 640
    assert eleccion.componentes["contraste_peor"] > 4.5


def test_la_eleccion_explica_por_que_gano():
    eleccion = comp.elegir_caja_texto(sujeto_arriba_derecha((1280, 720)), (400, 120),
                                      posicion_preferida="izq_inf")
    assert eleccion.nombre
    assert 0.0 <= eleccion.puntaje <= 1.0
    assert "gana con" in eleccion.motivo
    assert len(eleccion.candidatas) >= 9
    assert eleccion.candidatas[0].puntaje >= eleccion.candidatas[-1].puntaje


def test_un_bloque_que_no_entra_devuelve_la_menos_mala_y_lo_dice():
    """Si el bloque tapa el lienzo entero no hay ubicacion legal: se avisa."""
    eleccion = comp.elegir_caja_texto(liso(tamano=(1280, 720)), (1280, 720))
    assert eleccion.zonas_invadidas
    assert "Ninguna ubicacion respeta" in eleccion.motivo


def test_los_pesos_cambian_el_ganador():
    img = mitad_ocupada("izquierda", (1280, 720))
    solo_preferencia = comp.elegir_caja_texto(
        img, (400, 120), posicion_preferida="izq_sup", alinear_a_tercios=False,
        pesos={"limpieza": 0.0, "contraste": 0.0, "preferencia": 1.0,
               "foco_libre": 0.0, "tercios": 0.0, "equilibrio": 0.0})
    assert solo_preferencia.nombre == "izq_sup"
    solo_limpieza = comp.elegir_caja_texto(
        img, (400, 120), posicion_preferida="izq_sup", alinear_a_tercios=False,
        pesos={"limpieza": 1.0, "contraste": 0.0, "preferencia": 0.0,
               "foco_libre": 0.0, "tercios": 0.0, "equilibrio": 0.0})
    assert solo_limpieza.caja.centro[0] > 640


# --- lectura del skin --------------------------------------------------------
def test_skin_sin_bloque_de_composicion_sigue_funcionando():
    politica = comp.politica_composicion({})
    assert politica.punto_focal_preferido in comp.PUNTOS_FUERTES
    assert politica.espacio_negativo_minimo > 0
    assert politica.pesos == comp.PESOS_CAJA_TEXTO


def test_la_posicion_preferida_sigue_saliendo_de_texto_posicion():
    politica = comp.politica_composicion({"texto": {"posicion": "der_inf",
                                                    "ancho_max_pct": 40}})
    assert politica.posicion_preferida == "der_inf"
    assert politica.ancho_max_pct == 40


def test_un_punto_focal_invalido_cae_al_defecto():
    politica = comp.politica_composicion({"composicion": {"punto_focal_preferido": "centro"}})
    assert politica.punto_focal_preferido == comp.PoliticaComposicion().punto_focal_preferido


@pytest.mark.parametrize("slug", PERFILES)
def test_cada_perfil_declara_su_composicion(slug):
    politica = comp.politica_composicion(mod_perfiles.cargar_perfil(slug))
    assert politica.punto_focal_preferido in comp.PUNTOS_FUERTES
    assert 0.0 < politica.espacio_negativo_minimo < 1.0
    assert politica.posicion_preferida in comp.POSICIONES
    assert sum(politica.pesos.values()) > 0


def test_los_tres_perfiles_encuadran_distinto():
    politicas = [comp.politica_composicion(mod_perfiles.cargar_perfil(s)) for s in PERFILES]
    assert len({p.punto_focal_preferido for p in politicas}) == 3
    assert len({p.espacio_negativo_minimo for p in politicas}) == 3
    assert len({p.posicion_preferida for p in politicas}) == 3


def test_un_skin_puede_repesar_los_criterios():
    politica = comp.politica_composicion(mod_perfiles.cargar_perfil("tech_reviews"))
    assert politica.pesos["contraste"] > politica.pesos["limpieza"]


# --- evaluacion completa -----------------------------------------------------
def test_evaluar_composicion_aprueba_un_encuadre_sano():
    img = Image.new("RGB", (1280, 720), "#0a1f3d")
    ImageDraw.Draw(img).ellipse([700, 80, 1200, 580], fill="#e8b923")
    informe = comp.evaluar_composicion(img, mascara_texto=mascara_texto(),
                                       color_texto="#f4efe2")
    assert informe["ok"], informe["hallazgos"]


def test_evaluar_composicion_denuncia_el_encuadre_lleno():
    informe = comp.evaluar_composicion(ruido(tamano=(1280, 720), bloque=4))
    assert not informe["ok"]
    assert any("espacio negativo" in h for h in informe["hallazgos"])
    assert any("desenfoque" in h for h in informe["hallazgos"])


def test_evaluar_composicion_denuncia_el_texto_en_zona_tapada():
    img = Image.new("RGB", (1280, 720), "#0a1f3d")
    ImageDraw.Draw(img).ellipse([700, 80, 1200, 580], fill="#e8b923")
    caja = comp.Caja(1000, 640, 260, 70)
    informe = comp.evaluar_composicion(img, caja_texto=caja)
    assert any("invade" in h for h in informe["hallazgos"])


def test_la_politica_del_perfil_cambia_el_veredicto():
    """El mismo encuadre, dos perfiles: gana o pierde segun el YAML."""
    img = mitad_ocupada("izquierda", (1280, 720))
    laxa = comp.PoliticaComposicion(espacio_negativo_minimo=0.10, desbalance_maximo=0.90)
    estricta = comp.PoliticaComposicion(espacio_negativo_minimo=0.80, desbalance_maximo=0.10)
    assert len(comp.evaluar_composicion(img, laxa)["hallazgos"]) < \
        len(comp.evaluar_composicion(img, estricta)["hallazgos"])
