"""El motor de politicas, evaluado con los tres perfiles opuestos.

La prueba central es la ultima: el mismo concepto, sin tocar una linea de
Python, recibe veredictos distintos segun el YAML del perfil.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import perfiles as mod_perfiles
from app import politicas

EJEMPLOS = Path(__file__).resolve().parent.parent / "ejemplos"


def cargar(nombre: str) -> list[dict]:
    return json.loads((EJEMPLOS / nombre).read_text("utf-8"))


def por_id(conceptos: list[dict], cid: str) -> dict:
    return next(c for c in conceptos if c["id"] == cid)


def codigos(veredicto) -> set[str]:
    return {v.codigo for v in veredicto.violaciones}


# --- aviacion ---------------------------------------------------------------
def test_aviacion_acepta_archivo_con_cielo_generado():
    perfil = mod_perfiles.cargar_perfil("gdc")
    v = politicas.evaluar_concepto(por_id(cargar("conceptos_aviacion.json"), "av-1-valido"), perfil)
    assert v.ok and not v.violaciones


def test_aviacion_rechaza_generar_la_aeronave():
    perfil = mod_perfiles.cargar_perfil("gdc")
    v = politicas.evaluar_concepto(
        por_id(cargar("conceptos_aviacion.json"), "av-2-ia-sobre-aeronave"), perfil)
    assert not v.ok
    assert "ia_prohibida_para_categoria" in codigos(v)
    # El rechazo explica el porque declarado en el perfil.
    assert any("P-51 mal renderizado" in viol.razon for viol in v.duras)


def test_aviacion_controles_de_copy():
    perfil = mod_perfiles.cargar_perfil("gdc")
    v = politicas.evaluar_concepto(
        por_id(cargar("conceptos_aviacion.json"), "av-3-copy-fuera-de-politica"), perfil)
    assert "copy_largo" in codigos(v)
    # "!", "increible" y "clickbait numerico" disparan por separado.
    assert sum(1 for x in v.violaciones if x.codigo == "copy_prohibido") == 3


def test_aviacion_exige_nombre_reconocible_en_el_texto():
    perfil = mod_perfiles.cargar_perfil("gdc")
    concepto = {
        "id": "x", "copy": {"texto": "El regreso final", "nombre_reconocible": "P-51"},
        "base_visual": {"origen": "foto_archivo", "categoria": "cielo"},
    }
    assert "copy_no_contiene_campo" in codigos(politicas.evaluar_concepto(concepto, perfil))


# --- true crime -------------------------------------------------------------
def test_true_crime_bloquea_rostro_generado_de_persona_real():
    """Criterio de aceptacion: el perfil rechaza con mensaje explicito
    cualquier concepto que intente generar con IA a una persona real."""
    perfil = mod_perfiles.cargar_perfil("true_crime")
    v = politicas.evaluar_concepto(
        por_id(cargar("conceptos_true_crime.json"), "tc-2-rostro-generado"), perfil)
    assert not v.ok
    assert "ia_sobre_persona_real" in codigos(v)
    assert "ia_prohibida_para_categoria" in codigos(v)
    texto = v.informe()
    assert "derecho de imagen" in texto and "difamacion" in texto


def test_true_crime_no_deja_nombrar_a_la_victima():
    perfil = mod_perfiles.cargar_perfil("true_crime")
    v = politicas.evaluar_concepto(
        por_id(cargar("conceptos_true_crime.json"), "tc-3-nombra-victima"), perfil)
    assert "entidad_prohibida" in codigos(v)
    assert "categoria_vetada" in codigos(v)     # la capa con 'sangre'


def test_true_crime_acepta_archivo_licenciado():
    perfil = mod_perfiles.cargar_perfil("true_crime")
    v = politicas.evaluar_concepto(
        por_id(cargar("conceptos_true_crime.json"), "tc-1-valido"), perfil)
    assert v.ok and not v.violaciones


def test_true_crime_licencia_faltante_es_diferida_no_dura():
    """Sin licencia el concepto no se rechaza: queda pendiente para M5."""
    perfil = mod_perfiles.cargar_perfil("true_crime")
    concepto = {
        "id": "x", "copy": {"texto": "Catorce anos despues"},
        "base_visual": {"origen": "foto_archivo", "categoria": "victima"},
    }
    v = politicas.evaluar_concepto(concepto, perfil)
    assert v.ok                       # no rechaza
    assert [x.codigo for x in v.diferidas] == ["licencia_pendiente"]


# --- tech reviews -----------------------------------------------------------
def test_tech_permite_numeros_y_generacion_de_fondo():
    perfil = mod_perfiles.cargar_perfil("tech")
    v = politicas.evaluar_concepto(por_id(cargar("conceptos_tech.json"), "tr-1-valido"), perfil)
    assert v.ok and not v.violaciones


def test_tech_rechaza_generar_el_producto():
    perfil = mod_perfiles.cargar_perfil("tech")
    v = politicas.evaluar_concepto(
        por_id(cargar("conceptos_tech.json"), "tr-2-producto-generado"), perfil)
    assert "ia_prohibida_para_categoria" in codigos(v)


def test_tech_usa_su_propio_campo_obligatorio():
    """`debe_incluir` es una clave del YAML, no una constante del motor."""
    perfil = mod_perfiles.cargar_perfil("tech")
    concepto = {
        "id": "x", "copy": {"texto": "Comparativa de gama media", "producto": "Pixel 9"},
        "base_visual": {"origen": "foto_archivo", "categoria": "producto_identificable"},
    }
    assert "copy_no_contiene_campo" in codigos(politicas.evaluar_concepto(concepto, perfil))


# --- la prueba de la abstraccion --------------------------------------------
@pytest.mark.parametrize("slug,esperado_ok", [
    ("aviacion_historica", True),
    ("true_crime", False),    # 'generada' no esta en su orden de preferencia
    ("tech_reviews", False),  # exige el campo 'producto' en el copy
])
def test_mismo_concepto_distinto_veredicto_segun_el_perfil(slug, esperado_ok):
    concepto = por_id(cargar("conceptos_aviacion.json"), "av-1-valido")
    perfil = mod_perfiles.cargar_perfil(slug)
    assert politicas.evaluar_concepto(concepto, perfil).ok is esperado_ok


def test_ningun_nicho_esta_cableado_en_el_motor():
    """Guardia de diseno: los modulos del motor no nombran ningun nicho."""
    raiz = Path(__file__).resolve().parent.parent / "app"
    prohibidas = ("aviacion", "true_crime", "tech_reviews", "gigantes_del_cielo",
                  "aeronave", "victima", "perpetrador", "producto_identificable")
    ofensas = []
    for py in raiz.rglob("*.py"):
        texto = py.read_text("utf-8").lower()
        for palabra in prohibidas:
            if palabra in texto:
                ofensas.append(f"{py.name}: '{palabra}'")
    assert not ofensas, f"el motor conoce nichos: {ofensas}"
