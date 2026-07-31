"""M1 recolector, sin clave de API y sin tocar internet.

El transporte es un seam de inyeccion: el doble devuelve respuestas grabadas
pero pasa igual por `red.exigir_red`, asi la prueba de "segunda corrida, cero
llamadas" mide lo mismo que mediria en produccion.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pytest

from app import red
from app.cache import Cache
from app.errores import ErrorProveedor, ErrorThumbforge
from app.modulos import recolector
from app.perfiles import Perfil

AHORA = datetime.now(timezone.utc)


# --- andamiaje ---------------------------------------------------------------
def perfil_de_prueba(tmp_path, **corpus) -> Perfil:
    """Perfil sintetico: la prueba del motor no debe depender de ningun nicho."""
    datos = {
        "nombre": "perfil de prueba",
        "idioma": "es-419",
        "corpus": {"queries": ["termino uno"], "canales_referencia": [], **corpus},
    }
    raiz = tmp_path / "perfil_x"
    (raiz / "corpus").mkdir(parents=True, exist_ok=True)
    return Perfil(slug="perfil_x", raiz=raiz, datos=datos, skin={})


def png(color=(10, 20, 30)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (32, 18), color).save(buffer, format="PNG")
    return buffer.getvalue()


def item(video_id, canal="C1", views=1000, duracion="PT10M", dias=100,
         titulo="titulo", canal_titulo="Canal Uno", likes=10, comentarios=2):
    publicado = (AHORA - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    estadisticas = {"viewCount": str(views)}
    if likes is not None:
        estadisticas["likeCount"] = str(likes)
    if comentarios is not None:
        estadisticas["commentCount"] = str(comentarios)
    return {
        "id": video_id,
        "snippet": {
            "channelId": canal,
            "channelTitle": canal_titulo,
            "title": titulo,
            "description": "d" * 400,
            "publishedAt": publicado,
            "thumbnails": {
                "default": {"url": f"https://i.example/{video_id}/default.jpg"},
                "high": {"url": f"https://i.example/{video_id}/hq.jpg"},
                "maxres": {"url": f"https://i.example/{video_id}/maxres.jpg"},
            },
        },
        "contentDetails": {"duration": duracion},
        "statistics": estadisticas,
    }


class TransporteFalso:
    """Doble del transporte HTTP. Cuenta llamadas por `red`, como el real."""

    def __init__(self, items, destino="youtube-falso"):
        self.items = {i["id"]: i for i in items}
        self.destino = destino
        self.busquedas = 0
        self.detalles = 0
        self.descargas = 0

    def obtener_json(self, url, params):
        red.exigir_red(self.destino)
        if url.endswith("/search"):
            self.busquedas += 1
            return {"items": [{"id": {"videoId": vid}} for vid in self.items]}
        if url.endswith("/videos"):
            self.detalles += 1
            pedidos = str(params.get("id", "")).split(",")
            return {"items": [self.items[v] for v in pedidos if v in self.items]}
        raise AssertionError(f"recurso inesperado: {url}")

    def obtener_bytes(self, url):
        red.exigir_red(self.destino)
        self.descargas += 1
        return png()


@pytest.fixture(autouse=True)
def sin_variables(monkeypatch):
    monkeypatch.delenv("TF_SIN_RED", raising=False)
    monkeypatch.delenv("TF_SIN_CACHE", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "AIza" + "x" * 35)
    red.LLAMADAS.reiniciar()


# --- duraciones ISO-8601 -----------------------------------------------------
@pytest.mark.parametrize("texto,segundos", [
    ("PT4M13S", 253),
    ("PT1H", 3600),                 # sin minutos ni segundos
    ("PT62S", 62),                  # justo en el corte de Short
    ("PT1M2S", 62),
    ("P1DT2H3M4S", 93784),          # emision de un dia entero
    ("PT1H30M", 5400),
    ("P0D", 0),                     # vivo en curso
    ("PT0S", 0),
    ("P1W", 604800),
    ("pt4m13s", 253),               # minusculas
    ("PT1.5S", 2),                  # decimales, se redondea
])
def test_duraciones_iso(texto, segundos):
    assert recolector.duracion_iso_a_segundos(texto) == segundos


@pytest.mark.parametrize("texto", ["", "P", "PT", "4M13S", "banana", None, "P1Y"])
def test_duraciones_invalidas_levantan(texto):
    with pytest.raises(ValueError):
        recolector.duracion_iso_a_segundos(texto)


# --- filtros duros -----------------------------------------------------------
def test_descarta_shorts_y_recientes(tmp_path):
    transporte = TransporteFalso([
        item("largo", duracion="PT10M", dias=100),
        item("short", duracion="PT58S", dias=100),
        item("justo", duracion="PT62S", dias=100),      # el corte es inclusivo
        item("nuevo", duracion="PT10M", dias=3),
        item("borde", duracion="PT10M", dias=13),       # 13 dias: todavia no
        item("roto", duracion="", dias=100),
    ])
    perfil = perfil_de_prueba(tmp_path)
    resumen = recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                                    transporte=transporte)

    ids = {r["video_id"] for r in recolector.leer_jsonl(perfil.archivo_videos)}
    assert ids == {"largo", "justo"}
    assert resumen.descartados_shorts == 1
    assert resumen.descartados_recientes == 2
    assert resumen.descartados_sin_duracion == 1


def test_elige_la_miniatura_de_mayor_resolucion(tmp_path):
    transporte = TransporteFalso([item("a")])
    perfil = perfil_de_prueba(tmp_path)
    recolector.recolectar(perfil, Cache(tmp_path / "cache"), transporte=transporte)
    registro = recolector.leer_jsonl(perfil.archivo_videos)[0]
    assert registro["miniatura_calidad"] == "maxres"
    assert registro["miniatura_url"].endswith("maxres.jpg")
    assert registro["miniatura_ruta"] and registro["miniatura_clave"]


def test_la_miniatura_queda_en_cache_para_m2(tmp_path):
    from pathlib import Path

    transporte = TransporteFalso([item("a")])
    perfil = perfil_de_prueba(tmp_path)
    recolector.recolectar(perfil, Cache(tmp_path / "cache"), transporte=transporte)
    registro = recolector.leer_jsonl(perfil.archivo_videos)[0]
    assert Path(registro["miniatura_ruta"]).is_file()
    assert transporte.descargas == 1


# --- mediana y outlier_score -------------------------------------------------
def test_mediana_y_outlier_por_canal(tmp_path):
    """La mediana es del canal, no del corpus: 200k es exito en un canal y
    fracaso en otro."""
    transporte = TransporteFalso([
        item("a1", canal="A", views=100),
        item("a2", canal="A", views=200),
        item("a3", canal="A", views=900),
        item("b1", canal="B", views=10_000),
        item("b2", canal="B", views=20_000),
        item("b3", canal="B", views=30_000),
    ])
    perfil = perfil_de_prueba(tmp_path)
    resumen = recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                                    transporte=transporte)
    por_id = {r["video_id"]: r for r in recolector.leer_jsonl(perfil.archivo_videos)}

    assert por_id["a3"]["mediana_canal"] == 200.0
    assert por_id["a3"]["outlier_score"] == 4.5
    assert por_id["a1"]["outlier_score"] == 0.5
    # Mismo numero de views distinto veredicto segun el canal.
    assert por_id["b2"]["mediana_canal"] == 20_000.0
    assert por_id["b2"]["outlier_score"] == 1.0
    assert resumen.canales == 2
    assert resumen.canales_sin_mediana == 0


def test_canal_con_menos_de_tres_videos_no_recibe_mediana_inventada(tmp_path):
    """Con n=1 la mediana seria el propio video y el score daria 1.0: un
    numero que parece medido y no midio nada."""
    transporte = TransporteFalso([
        item("solo", canal="SOLO", views=5000),
        item("a1", canal="A", views=100),
        item("a2", canal="A", views=200),
        item("a3", canal="A", views=300),
    ])
    perfil = perfil_de_prueba(tmp_path)
    resumen = recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                                    transporte=transporte)
    por_id = {r["video_id"]: r for r in recolector.leer_jsonl(perfil.archivo_videos)}

    solo = por_id["solo"]
    assert solo["outlier_score"] is None
    assert solo["outlier_confiable"] is False
    assert solo["motivo_sin_outlier"] == recolector.MOTIVO_POCOS_VIDEOS
    assert solo["videos_del_canal_en_ventana"] == 1
    # Pero el registro se conserva: la imagen le sirve igual a M2.
    assert solo["views"] == 5000
    assert resumen.canales_sin_mediana == 1
    assert any("outlier_score" in a for a in resumen.avisos)
    # El canal con tres si tiene score.
    assert por_id["a3"]["outlier_score"] == 1.5


def test_mediana_cero_no_divide_por_cero(tmp_path):
    transporte = TransporteFalso([
        item("z1", canal="Z", views=0),
        item("z2", canal="Z", views=0),
        item("z3", canal="Z", views=0),
    ])
    perfil = perfil_de_prueba(tmp_path)
    recolector.recolectar(perfil, Cache(tmp_path / "cache"), transporte=transporte)
    for registro in recolector.leer_jsonl(perfil.archivo_videos):
        assert registro["outlier_score"] is None
        assert registro["motivo_sin_outlier"] == recolector.MOTIVO_MEDIANA_CERO


def test_likes_ocultos_no_se_confunden_con_cero(tmp_path):
    transporte = TransporteFalso([item("a", likes=None, comentarios=None)])
    perfil = perfil_de_prueba(tmp_path)
    recolector.recolectar(perfil, Cache(tmp_path / "cache"), transporte=transporte)
    registro = recolector.leer_jsonl(perfil.archivo_videos)[0]
    assert registro["likes"] is None and registro["comentarios"] is None


# --- lotes y cuota -----------------------------------------------------------
def test_videos_list_va_en_lotes_de_cincuenta(tmp_path):
    """Un `videos.list` por video multiplicaria la cuota por 50."""
    transporte = TransporteFalso([item(f"v{i}", views=100 + i) for i in range(120)])
    perfil = perfil_de_prueba(tmp_path, max_por_fuente=120)
    recolector.recolectar(perfil, Cache(tmp_path / "cache"), transporte=transporte)
    assert transporte.detalles == 3          # 120 ids -> 50 + 50 + 20


# --- cacheo ------------------------------------------------------------------
def test_segunda_corrida_sin_red_no_sale_a_la_red(tmp_path, monkeypatch):
    """Criterio de aceptacion: sin --refrescar, cero llamadas."""
    transporte = TransporteFalso([item(f"v{i}", views=100 + i) for i in range(6)])
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)

    primera = recolector.recolectar(perfil, cache, transporte=transporte)
    assert primera.llamadas_red > 0
    assert primera.escritos == 6

    llamadas_primera = red.LLAMADAS.total
    monkeypatch.setenv("TF_SIN_RED", "1")
    segunda = recolector.recolectar(perfil, cache, transporte=transporte)

    assert segunda.llamadas_red == 0
    assert red.LLAMADAS.total == llamadas_primera
    assert segunda.escritos == 6
    assert {r["video_id"] for r in recolector.leer_jsonl(perfil.archivo_videos)} == \
        {f"v{i}" for i in range(6)}


def test_refrescar_vuelve_a_pedir(tmp_path):
    transporte = TransporteFalso([item("a")])
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)

    recolector.recolectar(perfil, cache, transporte=transporte)
    busquedas = transporte.busquedas
    recolector.recolectar(perfil, cache, transporte=transporte, refrescar=True)
    assert transporte.busquedas > busquedas


def test_sin_red_desde_la_primera_corrida_falla_claro(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_SIN_RED", "1")
    perfil = perfil_de_prueba(tmp_path)
    with pytest.raises(red.ErrorSinRed):
        recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                              transporte=TransporteFalso([item("a")]))


# --- perfil ------------------------------------------------------------------
def test_las_queries_salen_del_perfil(tmp_path):
    """El motor no inventa terminos de busqueda: los lee del YAML."""
    vistos = []

    class Espia(TransporteFalso):
        def obtener_json(self, url, params):
            if url.endswith("/search"):
                vistos.append(dict(params))
            return super().obtener_json(url, params)

    perfil = perfil_de_prueba(tmp_path, queries=["alfa", "beta"],
                              canales_referencia=["UC123"])
    recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                          transporte=Espia([item("a")]))

    assert [p.get("q") for p in vistos if "q" in p] == ["alfa", "beta"]
    assert [p.get("channelId") for p in vistos if "channelId" in p] == ["UC123"]
    # El canal se busca por fecha y la query por relevancia.
    assert [p["order"] for p in vistos] == ["date", "relevance", "relevance"]


def test_perfil_sin_corpus_declarado_falla_con_mensaje_accionable(tmp_path):
    perfil = perfil_de_prueba(tmp_path, queries=[], canales_referencia=[])
    with pytest.raises(ErrorThumbforge) as exc:
        recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                              transporte=TransporteFalso([]))
    assert "corpus.queries" in str(exc.value)


def test_limite_recorta_por_outlier(tmp_path):
    transporte = TransporteFalso([
        item("bajo", canal="A", views=100),
        item("medio", canal="A", views=200),
        item("alto", canal="A", views=900),
    ])
    perfil = perfil_de_prueba(tmp_path)
    resumen = recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                                    transporte=transporte, limite=2)
    ids = [r["video_id"] for r in recolector.leer_jsonl(perfil.archivo_videos)]
    assert ids == ["alto", "medio"]
    assert resumen.escritos == 2


# --- errores de la API -------------------------------------------------------
def test_cuota_agotada_se_explica_como_cuota(tmp_path, monkeypatch):
    class Rota:
        def obtener_json(self, url, params):
            red.exigir_red("youtube-falso")
            raise ErrorProveedor(
                recolector._explicar_http(403, '{"error":{"errors":[{"reason":"quotaExceeded"}]}}'))

        def obtener_bytes(self, url):
            raise AssertionError("no deberia llegar aca")

    perfil = perfil_de_prueba(tmp_path)
    with pytest.raises(ErrorProveedor) as exc:
        recolector.recolectar(perfil, Cache(tmp_path / "cache"), transporte=Rota())
    assert "cuota diaria" in str(exc.value)


def test_una_miniatura_caida_no_tira_la_corrida(tmp_path):
    class SinImagenes(TransporteFalso):
        def obtener_bytes(self, url):
            red.exigir_red(self.destino)
            raise ErrorProveedor("HTTP 404")

    perfil = perfil_de_prueba(tmp_path)
    resumen = recolector.recolectar(perfil, Cache(tmp_path / "cache"),
                                    transporte=SinImagenes([item("a"), item("b")]))
    assert resumen.escritos == 2
    assert resumen.miniaturas_fallidas == 2
    assert all(r["miniatura_ruta"] == "" for r in recolector.leer_jsonl(perfil.archivo_videos))
