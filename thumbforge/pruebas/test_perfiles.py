"""Carga y validacion de perfiles."""

from __future__ import annotations

import pytest

from app import perfiles as mod
from app.errores import ErrorPerfil

ESPERADOS = {"aviacion_historica", "true_crime", "tech_reviews"}


def test_los_tres_perfiles_de_prueba_existen():
    slugs = {p.slug for p in mod.cargar_todos()}
    assert ESPERADOS <= slugs


@pytest.mark.parametrize("slug", sorted(ESPERADOS))
def test_cada_perfil_valida_sin_errores(slug):
    perfil = mod.cargar_perfil(slug)
    errores = [p for p in perfil.validar() if p.nivel == "ERROR"]
    assert errores == [], [p.detalle for p in errores]


@pytest.mark.parametrize("referencia,slug", [
    ("gdc", "aviacion_historica"),              # alias
    ("gigantes_del_cielo", "aviacion_historica"),
    ("true_crime", "true_crime"),               # slug exacto
    ("tc", "true_crime"),                       # alias corto
    ("tech", "tech_reviews"),                   # alias
    ("aviacion", "aviacion_historica"),         # prefijo unico
])
def test_resolucion_de_referencia(referencia, slug):
    assert mod.cargar_perfil(referencia).slug == slug


def test_perfil_inexistente_lista_los_disponibles():
    with pytest.raises(ErrorPerfil) as exc:
        mod.cargar_perfil("no_existe")
    mensaje = str(exc.value)
    assert "Disponibles" in mensaje
    assert "true_crime" in mensaje


@pytest.mark.parametrize("slug", sorted(ESPERADOS))
def test_tipografias_por_ruta_de_archivo_y_cargables(slug):
    """Las fuentes viajan en el perfil y Pillow las abre: nunca por nombre
    de familia, que caeria en silencio a la default."""
    from PIL import ImageFont

    perfil = mod.cargar_perfil(slug)
    fuentes = perfil.fuentes_declaradas()
    assert fuentes, f"{slug} no declara tipografias"
    for rol, ruta in fuentes.items():
        assert ruta.is_file(), f"{slug}/{rol} -> {ruta}"
        assert ruta.is_relative_to(perfil.raiz), "la fuente tiene que vivir dentro del perfil"
        ImageFont.truetype(str(ruta), 40)


@pytest.mark.parametrize("slug", sorted(ESPERADOS))
def test_lienzo_minimo(slug):
    perfil = mod.cargar_perfil(slug)
    assert perfil.get_skin("lienzo.ancho") >= 1280
    assert perfil.get_skin("lienzo.alto") >= 720


def test_campos_extra_se_suman_al_esquema_base():
    from app.esquemas import ESQUEMA_ANOTACION_BASE

    perfil = mod.cargar_perfil("gdc")
    esquema = perfil.esquema_anotacion()
    assert set(ESQUEMA_ANOTACION_BASE) <= set(esquema)
    assert "epoca_aeronave" in esquema
    # Y no contamina a los demas perfiles.
    assert "epoca_aeronave" not in mod.cargar_perfil("true_crime").esquema_anotacion()
