"""Colorimetria.

Las conversiones se verifican contra valores publicados, no contra lo que
devuelve el codigo: CIEDE2000 contra los 34 pares de Sharma, Wu y Dalal, los
primarios sRGB contra sus coordenadas CIELAB conocidas y el contraste WCAG
contra el 21:1 de blanco sobre negro. Las imagenes son sinteticas.
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app import color as c
from app import perfiles as mod_perfiles

PERFILES = ("aviacion_historica", "true_crime", "tech_reviews")


# --- utilidades de imagen ----------------------------------------------------
def lienzo(color="#000000", tamano=(320, 180)) -> Image.Image:
    return Image.new("RGB", tamano, color)


def mitades(izquierda="#000000", derecha="#ffffff", tamano=(320, 180)) -> Image.Image:
    img = Image.new("RGB", tamano, izquierda)
    ImageDraw.Draw(img).rectangle([tamano[0] // 2, 0, tamano[0], tamano[1]], fill=derecha)
    return img


def mascara(tamano=(320, 180), caja=(40, 40, 280, 140)) -> Image.Image:
    msk = Image.new("L", tamano, 0)
    ImageDraw.Draw(msk).rectangle(list(caja), fill=255)
    return msk


# --- parseo ------------------------------------------------------------------
@pytest.mark.parametrize("texto,esperado", [
    ("#ffffff", (255, 255, 255)),
    ("000000", (0, 0, 0)),
    ("#f00", (255, 0, 0)),
    ("#0a1f3d", (10, 31, 61)),
    ("#0a1f3dff", (10, 31, 61)),      # el alfa se descarta
])
def test_parseo_hex(texto, esperado):
    assert c.parsear_hex(texto) == esperado


@pytest.mark.parametrize("malo", ["#12345", "no soy color", "#gggggg", ""])
def test_hex_invalido_explota(malo):
    with pytest.raises(ValueError):
        c.parsear_hex(malo)


def test_ida_y_vuelta_hex():
    for hx in ("#0a1f3d", "#e8b923", "#31d158", "#8c1c13", "#ededed"):
        assert c.a_hex(c.a_rgb(hx)) == hx


# --- conversiones contra valores publicados ----------------------------------
@pytest.mark.parametrize("hx,lab", [
    ("#ffffff", (100.0000, 0.0000, 0.0000)),
    ("#000000", (0.0000, 0.0000, 0.0000)),
    ("#ff0000", (53.2408, 80.0925, 67.2032)),
    ("#00ff00", (87.7347, -86.1827, 83.1793)),
    ("#0000ff", (32.2970, 79.1875, -107.8602)),
])
def test_srgb_a_cielab_d65(hx, lab):
    obtenido = c.rgb_a_lab(hx)
    for esperado, real in zip(lab, obtenido):
        assert abs(esperado - real) < 1e-3


def test_lab_ida_y_vuelta():
    for hx in ("#0a1f3d", "#e8b923", "#31d158", "#8c1c13", "#7f7f7f"):
        assert c.a_hex(c.lab_a_rgb(c.rgb_a_lab(hx))) == hx


def test_lineal_no_es_gamma():
    # 50% de senal sRGB es ~21.4% de luz: la confusion entre los dos espacios
    # es la que arruina cualquier promedio de color.
    assert abs(c.canal_a_lineal(0.5) - 0.2140) < 1e-3
    assert abs(c.canal_a_srgb(c.canal_a_lineal(0.5)) - 0.5) < 1e-9


@pytest.mark.parametrize("hx,hsl,hsv", [
    ("#ff0000", (0.0, 1.0, 0.5), (0.0, 1.0, 1.0)),
    ("#00ff00", (120.0, 1.0, 0.5), (120.0, 1.0, 1.0)),
    ("#0000ff", (240.0, 1.0, 0.5), (240.0, 1.0, 1.0)),
    ("#808080", (0.0, 0.0, 0.50196), (0.0, 0.0, 0.50196)),
])
def test_hsl_y_hsv(hx, hsl, hsv):
    for esperado, real in zip(hsl, c.rgb_a_hsl(hx)):
        assert abs(esperado - real) < 1e-3
    for esperado, real in zip(hsv, c.rgb_a_hsv(hx)):
        assert abs(esperado - real) < 1e-3


def test_hsl_y_hsv_ida_y_vuelta():
    for hx in ("#0a1f3d", "#e8b923", "#31d158", "#8c1c13"):
        assert c.a_hex(c.hsl_a_rgb(*c.rgb_a_hsl(hx))) == hx
        assert c.a_hex(c.hsv_a_rgb(*c.rgb_a_hsv(hx))) == hx


# --- contraste WCAG ----------------------------------------------------------
def test_contraste_blanco_negro_es_21():
    assert c.razon_contraste("#ffffff", "#000000") == pytest.approx(21.0, abs=1e-9)
    assert c.razon_contraste("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-9)


def test_contraste_consigo_mismo_es_1():
    assert c.razon_contraste("#31d158", "#31d158") == pytest.approx(1.0)


def test_luminancias_de_referencia():
    assert c.luminancia_relativa("#ffffff") == pytest.approx(1.0, abs=1e-9)
    assert c.luminancia_relativa("#000000") == pytest.approx(0.0, abs=1e-9)
    assert c.luminancia_relativa("#808080") == pytest.approx(0.2158, abs=1e-3)


def test_umbral_de_contraste_es_un_parametro_no_una_constante():
    """El 4.5 del proyecto es un defecto; el perfil puede exigir mas."""
    par = ("#767676", "#ffffff")          # 4.54:1, apenas sobre el minimo AA
    assert c.cumple_contraste(*par, minimo=4.5)
    assert not c.cumple_contraste(*par, minimo=7.0)


# --- diferencia de color -----------------------------------------------------
# Sharma, Wu y Dalal (2005), tabla de 34 pares de referencia para CIEDE2000.
PARES_SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,esperado", PARES_SHARMA)
def test_ciede2000_contra_los_pares_de_sharma(lab1, lab2, esperado):
    assert c.delta_e_2000(lab1, lab2) == pytest.approx(esperado, abs=1e-4)


def test_ciede2000_es_simetrica():
    for lab1, lab2, _ in PARES_SHARMA[:8]:
        assert c.delta_e_2000(lab1, lab2) == pytest.approx(c.delta_e_2000(lab2, lab1))


def test_delta_e_76_es_euclidea():
    assert c.delta_e_76((50, 0, 0), (50, 3, 4)) == pytest.approx(5.0)


def test_ciede2000_corrige_a_cie76_en_los_azules():
    """El caso que justifica implementar la formula completa: dos azules a
    4.3 de distancia euclidea que el ojo ve casi iguales."""
    lab1, lab2 = (50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)
    assert c.delta_e_76(lab1, lab2) > 3.9
    assert c.delta_e_2000(lab1, lab2) < 2.1


def test_delta_e_por_hex():
    assert c.delta_e("#000000", "#000000") == pytest.approx(0.0)
    assert c.delta_e("#ffffff", "#000000") > 95
    assert c.delta_e("#ffffff", "#000000", metodo="cie76") == pytest.approx(100.0)


# --- paleta ------------------------------------------------------------------
def test_paleta_de_color_solido():
    paleta = c.paleta_dominante(lienzo("#8c1c13"))
    assert len(paleta) == 1
    assert paleta[0][0] == "#8c1c13"
    assert paleta[0][1] == pytest.approx(1.0)


def test_paleta_de_tres_bandas_respeta_las_proporciones():
    img = Image.new("RGB", (300, 100), "#0a1f3d")
    d = ImageDraw.Draw(img)
    d.rectangle([150, 0, 249, 99], fill="#e8b923")
    d.rectangle([250, 0, 299, 99], fill="#f4efe2")
    paleta = dict(c.paleta_dominante(img, maximo=4))
    assert set(paleta) == {"#0a1f3d", "#e8b923", "#f4efe2"}
    assert paleta["#0a1f3d"] == pytest.approx(0.5, abs=0.03)
    assert paleta["#e8b923"] == pytest.approx(1 / 3, abs=0.03)


def test_la_paleta_ignora_el_ruido():
    """Una mancha de 20 px no es un color de la paleta."""
    img = lienzo("#111111", (400, 200))
    ImageDraw.Draw(img).rectangle([0, 0, 19, 19], fill="#31d158")
    colores = [hx for hx, _ in c.paleta_dominante(img, peso_minimo=0.05)]
    assert colores == ["#111111"]


def test_la_paleta_ignora_lo_transparente():
    img = Image.new("RGBA", (200, 100), (255, 255, 255, 0))
    ImageDraw.Draw(img).rectangle([0, 0, 99, 99], fill=(140, 28, 19, 255))
    paleta = c.paleta_dominante(img)
    assert paleta[0][0] == "#8c1c13"
    assert paleta[0][1] == pytest.approx(1.0)


def test_paleta_de_imagen_vacia_no_explota():
    assert c.paleta_dominante(Image.new("RGBA", (10, 10), (0, 0, 0, 0))) == []


# --- metricas ----------------------------------------------------------------
def test_saturacion_y_luminancia_de_referencia():
    assert c.saturacion_media(lienzo("#808080")) == pytest.approx(0.0, abs=1e-6)
    assert c.saturacion_media(lienzo("#ff0000")) == pytest.approx(1.0, abs=1e-6)
    assert c.luminancia_media(lienzo("#ffffff")) == pytest.approx(1.0, abs=1e-6)
    assert c.luminancia_media(lienzo("#000000")) == pytest.approx(0.0, abs=1e-6)


def test_calidez_separa_naranja_de_azul():
    assert c.calidez(lienzo("#e8891f")) > 0.8
    assert c.calidez(lienzo("#1f6fe8")) < -0.8
    assert c.calidez(lienzo("#7f7f7f")) == pytest.approx(0.0)


def test_temperatura_en_kelvin_ordena_calido_y_frio():
    calido = c.temperatura_kelvin("#ffb46b")
    frio = c.temperatura_kelvin("#9dc6ff")
    assert calido < 4000 < frio


def test_dispersion_cromatica():
    assert c.dispersion_cromatica(lienzo("#8c1c13")) == pytest.approx(0.0, abs=1e-6)
    arcoiris = Image.new("RGB", (360, 20))
    d = ImageDraw.Draw(arcoiris)
    for x in range(360):
        d.line([(x, 0), (x, 20)], fill=c.hsv_a_rgb(x, 1.0, 1.0))
    assert c.dispersion_cromatica(arcoiris) > 0.9


def test_metricas_de_imagen_completas():
    m = c.metricas_imagen(mitades("#000000", "#ffffff"))
    assert m.luminancia_media == pytest.approx(0.5, abs=0.02)
    assert m.contraste_interno > 0.9
    assert m.temperatura == "neutra"


# --- armonias ----------------------------------------------------------------
def test_complementario_gira_180_grados():
    assert c.rgb_a_hsl(c.complementario("#ff0000"))[0] == pytest.approx(180.0, abs=0.5)


def test_triada_y_split():
    matices = sorted(round(c.rgb_a_hsl(x)[0]) for x in c.triada("#ff0000"))
    assert matices == [120, 240]
    matices = sorted(round(c.rgb_a_hsl(x)[0]) for x in c.split_complementario("#ff0000"))
    assert matices == [150, 210]


def test_analogos_son_vecinos():
    matices = sorted(round(c.rgb_a_hsl(x)[0]) for x in c.analogos("#00ff00", 30))
    assert matices == [90, 150]


def test_generar_armonia_incluye_la_base():
    for esquema in c.ESQUEMAS_ARMONIA:
        paleta = c.generar_armonia("#8c1c13", esquema)
        assert paleta[0] == "#8c1c13"
        assert len(paleta) >= 2


def test_esquema_desconocido_explota():
    with pytest.raises(ValueError):
        c.generar_armonia("#ffffff", "espiral")


@pytest.mark.parametrize("esquema", ["complementario", "triada",
                                     "split_complementario", "analogo"])
def test_una_paleta_generada_clasifica_en_su_propio_esquema(esquema):
    paleta = c.generar_armonia("#c8321e", esquema)
    assert c.ajuste_armonia(paleta, esquema) > 0.98


def test_una_paleta_desordenada_no_encaja_en_ninguna_armonia_estrecha():
    paleta = ["#ff0000", "#00ff88", "#3300ff", "#ffee00"]
    assert c.ajuste_armonia(paleta, "monocromatico") < 0.3
    assert c.ajuste_armonia(paleta, "complementario") < 0.7


def test_los_neutros_no_contradicen_ninguna_armonia():
    assert c.ajuste_armonia(["#111111", "#888888", "#ededed"], "triada") == 1.0


def test_clasificar_prefiere_el_esquema_mas_estricto():
    assert c.clasificar_armonia(["#8c1c13", "#a02418"])[0] == "monocromatico"
    esquema, ajuste = c.clasificar_armonia(c.generar_armonia("#0a5fd4", "triada"))
    assert esquema == "triada" and ajuste > 0.98


# --- contraste contra fondo real ---------------------------------------------
def test_el_promedio_del_fondo_miente_y_el_peor_caso_no():
    """Blanco sobre mitad negro y mitad blanco: el color promedio da gris y
    aprueba; medir pixel a pixel muestra que la mitad del texto no se lee."""
    fondo = mitades("#000000", "#ffffff")
    informe = c.contraste_sobre_fondo("#ffffff", fondo, mascara(), minimo=4.5)
    assert informe.promedio > 4.5          # el promedio aprueba
    assert informe.peor == pytest.approx(1.0, abs=1e-6)
    assert not informe.cumple
    assert informe.fraccion_ok == pytest.approx(0.5, abs=0.05)
    # El color medio del fondo es gris y mentiria:
    assert c.razon_contraste("#ffffff", "#808080") < 21


def test_contraste_sobre_fondo_uniforme_coincide_con_el_par_de_colores():
    informe = c.contraste_sobre_fondo("#ffffff", lienzo("#000000"), minimo=4.5)
    assert informe.peor == pytest.approx(21.0)
    assert informe.promedio == pytest.approx(21.0)
    assert informe.cumple


def test_la_mascara_limita_la_medicion_a_los_pixeles_del_texto():
    fondo = mitades("#000000", "#ffffff", (400, 100))
    solo_izquierda = Image.new("L", (400, 100), 0)
    ImageDraw.Draw(solo_izquierda).rectangle([10, 10, 180, 90], fill=255)
    informe = c.contraste_sobre_fondo("#ffffff", fondo, solo_izquierda)
    assert informe.peor == pytest.approx(21.0)
    assert informe.fraccion_ok == 1.0


# --- eleccion de color de texto ----------------------------------------------
def test_elige_el_candidato_que_mas_contrasta():
    decision = c.elegir_color_texto(lienzo("#0a1f3d"), ["#0d1117", "#f4efe2", "#8c1c13"])
    assert decision.color == "#f4efe2"
    assert decision.cumple and not decision.necesita_placa


def test_fondo_disparejo_pide_placa():
    decision = c.elegir_color_texto(mitades("#000000", "#ffffff"),
                                    ["#ffffff", "#111111"], mascara=mascara())
    assert decision.necesita_placa and not decision.necesita_contorno
    assert "placa" in decision.motivo


def test_fondo_casi_bueno_pide_contorno():
    """Una mancha clara chica sobre fondo oscuro se resuelve con contorno."""
    fondo = lienzo("#0a1f3d", (400, 100))
    ImageDraw.Draw(fondo).rectangle([340, 0, 399, 99], fill="#f2f2f2")
    decision = c.elegir_color_texto(fondo, ["#f4efe2"], minimo=4.5,
                                    refuerzos=["#04101f"])
    assert decision.necesita_contorno and not decision.necesita_placa
    assert decision.cumple                  # el contorno lo resuelve
    assert "contorno" in decision.motivo


def test_el_minimo_lo_pone_quien_llama():
    fondo = lienzo("#767676")
    assert c.elegir_color_texto(fondo, ["#ffffff"], minimo=4.5).cumple
    exigente = c.elegir_color_texto(fondo, ["#ffffff"], minimo=7.0)
    assert exigente.necesita_contorno or exigente.necesita_placa


def test_sin_candidatos_explota():
    with pytest.raises(ValueError):
        c.elegir_color_texto(lienzo(), [])


# --- distancias entre imagenes y variantes -----------------------------------
def test_histograma_de_la_misma_imagen_da_cero():
    img = mitades()
    assert c.distancia_histograma(img, img) == pytest.approx(0.0, abs=1e-9)
    assert c.distancia_histograma(img, img, "chi2") == pytest.approx(0.0, abs=1e-9)


def test_histograma_de_imagenes_opuestas_da_uno():
    assert c.distancia_histograma(lienzo("#000000"), lienzo("#ffffff")) == pytest.approx(1.0)
    assert c.distancia_histograma(lienzo("#000000"), lienzo("#ffffff"),
                                  "chi2") == pytest.approx(1.0)


def test_histograma_ordena_lo_parecido_antes_que_lo_distinto():
    base = lienzo("#0a1f3d")
    parecida = lienzo("#0c2344")
    distinta = lienzo("#e8b923")
    assert c.distancia_histograma(base, parecida) < c.distancia_histograma(base, distinta)


def test_variantes_demasiado_parecidas_se_detectan():
    a = [("#0a1f3d", 0.8), ("#e8b923", 0.2)]
    b = [("#0c2143", 0.8), ("#e6b727", 0.2)]     # la misma con otro nombre
    d = [("#8c1c13", 0.8), ("#ededed", 0.2)]
    informe = c.separacion_de_variantes([a, b, d], minimo=10.0)
    assert not informe["cumple"]
    assert informe["par_mas_parecido"] == (0, 1)
    assert informe["minimo_observado"] < 3

    bueno = c.separacion_de_variantes([a, d], minimo=10.0)
    assert bueno["cumple"]


def test_delta_e_entre_paletas_es_simetrico():
    a = [("#0a1f3d", 1.0)]
    b = [("#8c1c13", 1.0)]
    assert c.delta_e_entre_paletas(a, b) == pytest.approx(c.delta_e_entre_paletas(b, a))


# --- lectura del skin --------------------------------------------------------
def test_skin_sin_bloque_de_colorimetria_sigue_funcionando():
    """Un skin viejo no puede romperse porque el motor aprendio claves nuevas."""
    politica = c.politica_color({"paleta": {"texto": "#ffffff"}})
    assert politica.contraste_minimo == c.CONTRASTE_MINIMO
    assert politica.colores_texto == ["#ffffff"]
    assert c.politica_color({}).colores_texto  # ni siquiera con el skin vacio


def test_valores_basura_en_el_skin_caen_al_defecto():
    politica = c.politica_color({"colorimetria": {"contraste_minimo": "mucho",
                                                  "armonia_preferida": "espiral"}})
    assert politica.contraste_minimo == c.CONTRASTE_MINIMO
    assert politica.armonia_preferida == "espiral"   # se lee tal cual...
    # ...y evaluar no explota: un esquema desconocido no invalida la imagen.
    assert c.evaluar_colorimetria(lienzo("#8c1c13"), politica)["ajuste_armonia"] == 1.0


@pytest.mark.parametrize("slug", PERFILES)
def test_cada_perfil_declara_su_colorimetria(slug):
    politica = c.politica_color(mod_perfiles.cargar_perfil(slug))
    assert politica.contraste_minimo >= 4.5
    assert politica.armonia_preferida in c.ESQUEMAS_ARMONIA
    assert 0.0 < politica.saturacion_maxima <= 1.0
    assert politica.delta_e_minimo_entre_variantes > 0
    assert politica.colores_texto and politica.colores_refuerzo


def test_los_tres_perfiles_piden_cosas_distintas():
    politicas = [c.politica_color(mod_perfiles.cargar_perfil(s)) for s in PERFILES]
    assert len({p.contraste_minimo for p in politicas}) == 3
    assert len({p.armonia_preferida for p in politicas}) == 3
    assert len({p.saturacion_maxima for p in politicas}) == 3
    assert len({p.delta_e_minimo_entre_variantes for p in politicas}) == 3


def test_evaluar_colorimetria_reporta_lo_que_el_perfil_no_tolera():
    politica = c.politica_color(mod_perfiles.cargar_perfil("true_crime"))
    informe = c.evaluar_colorimetria(lienzo("#ff2200"), politica)
    assert not informe["ok"]
    assert any("saturacion" in h for h in informe["hallazgos"])
    assert any("calidez" in h for h in informe["hallazgos"])
