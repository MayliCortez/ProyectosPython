"""M5 - resolucion de la base visual."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app import perfiles as mod_perfiles
from app.cache import Cache
from app.modulos import fuentes


def _imagen_bytes(color="#123a5a", sujeto="#e8b923", tamano=(1600, 900)) -> bytes:
    img = Image.new("RGB", tamano, color)
    d = ImageDraw.Draw(img)
    d.ellipse([tamano[0] * 0.6, tamano[1] * 0.1,
               tamano[0] * 0.95, tamano[1] * 0.6], fill=sujeto)
    b = io.BytesIO()
    img.save(b, "JPEG", quality=88)
    return b.getvalue()


class _RespuestaFalsa:
    def __init__(self, data, status=200):
        self.status_code = status
        self.content = data if isinstance(data, bytes) else None
        self._json = data if not isinstance(data, bytes) else None
        self.text = str(data)[:200]

    def json(self):
        return self._json


class _ClienteFalso:
    """Ruta HTTP en memoria. Openverse y Commons se consultan casi siempre
    juntos -Commons es el fallback cuando Openverse trae poco- asi que si el
    test declaro uno, el otro devuelve vacio por defecto en vez de fallar."""

    VACIOS = {
        "openverse": {"results": []},
        "commons": {"query": {"pages": {}}},
    }

    def __init__(self, rutas: dict):
        self.rutas = rutas

    def get(self, url, params=None, headers=None):
        for patron, respuesta in self.rutas.items():
            if patron in url:
                if callable(respuesta):
                    return respuesta(url, params or {})
                return _RespuestaFalsa(respuesta)
        for pista, vacio in self.VACIOS.items():
            if pista in url:
                return _RespuestaFalsa(vacio)
        raise AssertionError(f"URL no esperada en el test: {url}")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def fingir(monkeypatch):
    """Reemplaza red.cliente y desactiva TF_SIN_RED."""
    from app import red as mod_red
    monkeypatch.delenv("TF_SIN_RED", raising=False)

    def registrar(rutas: dict):
        def _cliente(destino: str, **kw):
            mod_red.LLAMADAS.registrar(destino)
            return _ClienteFalso(rutas)
        monkeypatch.setattr(mod_red, "cliente", _cliente)
    mod_red.LLAMADAS.reiniciar()
    return registrar


# --- busqueda y filtrado ------------------------------------------------------
def test_las_no_comerciales_no_llegan_al_candidato(fingir, tmp_path):
    fingir({"openverse": {"results": [

        {"url": "https://x/a.jpg", "title": "A", "license": "by-nc",
         "creator": "n", "foreign_landing_url": "https://x/a",
         "width": 2000, "height": 1200},
        {"url": "https://x/b.jpg", "title": "B", "license": "by",
         "creator": "n", "foreign_landing_url": "https://x/b",
         "width": 2000, "height": 1200},
    ]}})
    concepto = {"id": "c", "base_visual": {"descripcion": "algo"}, "copy": {}}
    cs, _ = fuentes.buscar(concepto, Cache(tmp_path / "c"))
    licencias = [c.licencia for c in cs]
    assert "by-nc" not in licencias
    assert "by" in licencias


def test_las_de_baja_resolucion_se_descartan(fingir, tmp_path):
    fingir({"openverse": {"results": [

        {"url": "https://x/mini.jpg", "title": "mini", "license": "cc0",
         "creator": "n", "foreign_landing_url": "https://x/mini",
         "width": 400, "height": 200},
    ]}})
    concepto = {"id": "c", "base_visual": {"descripcion": "algo"}, "copy": {}}
    cs, _ = fuentes.buscar(concepto, Cache(tmp_path / "c"))
    assert cs == []


def test_consultas_se_prueban_de_mas_especifica_a_mas_general(fingir, tmp_path):
    """Cada consulta se traduce a UNA busqueda de Openverse. Solo cuando
    Openverse no da suficiente se cae a Commons; para aislar el orden de
    consultas, aca Openverse siempre alcanza para responder.
    """
    llamadas = []

    def openverse(url, params):
        q = params.get("q")
        llamadas.append(q)
        # Las dos primeras consultas devuelven vacio, la tercera un resultado.
        if q != "muy general":
            return _RespuestaFalsa({"results": []})
        return _RespuestaFalsa({"results": [
            {"url": "https://x/a.jpg", "title": "A", "license": "cc0",
             "creator": "n", "foreign_landing_url": "https://x/a",
             "width": 2000, "height": 1200}]})

    fingir({"openverse": openverse})
    concepto = {"id": "c", "base_visual": {
        "consulta_archivo": "muy especifico", "descripcion": "menos especifico",
        "categoria": "muy_general"}, "copy": {}}
    cs, consulta = fuentes.buscar(concepto, Cache(tmp_path / "c"))
    assert cs, "la ultima consulta si tenia resultados"
    assert llamadas == ["muy especifico", "menos especifico", "muy general"]
    assert consulta == "muy general"


# --- descarga: cache real ----------------------------------------------------
def test_la_segunda_descarga_no_sale_a_la_red(fingir, tmp_path):
    llamadas = {"n": 0}

    def contar(url, params):
        llamadas["n"] += 1
        return _RespuestaFalsa(_imagen_bytes())
    fingir({"picsum": contar})

    cache = Cache(tmp_path / "c")
    c = fuentes.Candidato(url="https://picsum.photos/1600/900", licencia="cc0")
    fuentes.descargar(c, cache)
    fuentes.descargar(c, cache)
    fuentes.descargar(c, cache)
    assert llamadas["n"] == 1


# --- puntuacion --------------------------------------------------------------
def test_el_aire_es_uno_de_los_criterios_de_puntaje():
    """La MISMA imagen, con y sin detalle repartido por todos lados: la
    version con aire tiene que sacar mayor puntaje EN el componente 'aire'.

    Comparar puntajes totales entre dos imagenes distintas mezcla criterios:
    la saturada puede ganar en luminancia o color por casualidad y compensar
    lo que pierde en aire. Aca se aisla el criterio que interesa.
    """
    import random
    perfil = mod_perfiles.cargar_perfil("gdc")

    limpia = Image.new("RGB", (1600, 900), "#122f4a")
    ImageDraw.Draw(limpia).ellipse([1000, 200, 1400, 600], fill="#e8b923")

    # Patron denso y regular: cada celda pintada de un color distinto no
    # deja zonas limpias, y eso es lo que el criterio tiene que castigar.
    saturada = Image.new("RGB", (1600, 900), "#122f4a")
    d = ImageDraw.Draw(saturada)
    r = random.Random(3)
    for y in range(0, 900, 40):
        for x in range(0, 1600, 40):
            d.rectangle([x, y, x + 40, y + 40],
                        fill=(r.randint(60, 240), r.randint(60, 240),
                              r.randint(60, 240)))

    _, comp_l = fuentes.puntuar(limpia, perfil)
    _, comp_s = fuentes.puntuar(saturada, perfil)
    assert comp_l["aire"] > comp_s["aire"], (
        f"limpia aire={comp_l['aire']} vs saturada aire={comp_s['aire']}")


# --- politica de personas reales ---------------------------------------------
def test_true_crime_exige_licencia_verificada(fingir, tmp_path):
    fingir({"openverse": {"results": [

        {"url": "https://x/a.jpg", "title": "A", "license": "cc0",
         "creator": "n", "foreign_landing_url": "",   # sin URL de origen
         "width": 2000, "height": 1200},
    ]}, "descarga_imagen": _imagen_bytes()})
    perfil = mod_perfiles.cargar_perfil("true_crime")
    concepto = {"id": "c",
                "base_visual": {"origen": "foto_archivo",
                                "categoria": "documento_judicial",
                                "consulta_archivo": "expediente"},
                "copy": {}}
    with pytest.raises(fuentes.ErrorFuente) as exc:
        fuentes.resolver(concepto, perfil, Cache(tmp_path / "c"))
    assert "licencia verificada" in str(exc.value)


# --- eleccion completa -------------------------------------------------------
def test_elige_la_de_mejor_puntaje(fingir, tmp_path):
    resultados = [
        {"url": "https://x/mala.jpg", "title": "mala", "license": "cc0",
         "creator": "n", "foreign_landing_url": "https://x/mala",
         "width": 1600, "height": 900},
        {"url": "https://x/buena.jpg", "title": "buena", "license": "cc0",
         "creator": "n", "foreign_landing_url": "https://x/buena",
         "width": 1600, "height": 900},
    ]
    saturada = _imagen_bytes("#a02010", "#00a020")
    aire = _imagen_bytes("#122f4a", "#e8b923")

    def descarga(url, params):
        return _RespuestaFalsa(saturada if "mala" in url else aire)

    fingir({"openverse": {"results": resultados}, "https://x/": descarga})
    perfil = mod_perfiles.cargar_perfil("gdc")
    concepto = {"id": "c", "base_visual": {"origen": "foto_archivo",
                                            "descripcion": "algo"}, "copy": {}}
    imagen, elegido, _ = fuentes.resolver(concepto, perfil, Cache(tmp_path / "c"))
    assert "buena" in elegido.url
    assert imagen.size == (1600, 900)
