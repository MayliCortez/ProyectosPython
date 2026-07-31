"""M2 anotador, sin clave de API y sin llamar a ningun modelo.

`anotar` recibe la funcion que habla con el proveedor como parametro, asi la
prueba inyecta un doble que devuelve JSON grabado -o que falla a proposito-
sin monkeypatch sobre modulos ajenos.
"""

from __future__ import annotations

import io

import pytest

from app import esquemas, red
from app.cache import Cache
from app.errores import ErrorProveedor, ErrorThumbforge
from app.llm import RespuestaLLM
from app.modulos import anotador, recolector
from app.perfiles import Perfil


# --- andamiaje ---------------------------------------------------------------
def perfil_de_prueba(tmp_path, extras=None) -> Perfil:
    datos = {
        "nombre": "perfil de prueba",
        "idioma": "es-419",
        "campos_extra_anotacion": list(extras or []),
    }
    raiz = tmp_path / "perfil_x"
    (raiz / "corpus").mkdir(parents=True, exist_ok=True)
    return Perfil(slug="perfil_x", raiz=raiz, datos=datos, skin={})


def jpg(ancho=1280, alto=720) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), (200, 30, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


def corpus(tmp_path, perfil, cache, cantidad=2, con_miniatura=True) -> list[dict]:
    """Deja videos.jsonl y las miniaturas en cache, como las dejaria M1."""
    registros = []
    for i in range(cantidad):
        video_id = f"v{i}"
        registro = {"video_id": video_id, "titulo": f"t{i}", "canal_id": "C1",
                    "miniatura_ruta": "", "miniatura_clave": ""}
        if con_miniatura:
            clave = f"clave{i}" + "0" * 10
            ruta = cache.guardar_bytes(recolector.ESPACIO_MINIATURAS, clave, jpg(), ".jpg")
            registro["miniatura_clave"] = clave
            registro["miniatura_ruta"] = str(ruta)
        registros.append(registro)
    recolector.escribir_jsonl(perfil.archivo_videos, registros)
    return registros


def respuesta_valida(esquema: dict) -> dict:
    """Una respuesta que cumple el esquema, campo por campo."""
    datos = {}
    for campo, definicion in esquema.items():
        tipo, opciones, _ = anotador._desarmar(definicion)
        if tipo == "enum":
            datos[campo] = opciones[0]
        elif tipo == "bool":
            datos[campo] = True
        elif tipo == "int":
            datos[campo] = 12
        elif tipo == "float":
            datos[campo] = 4.5
        elif tipo == "list[str]":
            datos[campo] = ["#112233"]
        else:
            datos[campo] = "texto"
    return datos


class ModeloFalso:
    """Doble de `llm.pedir_json`. Cuenta llamadas y puede fallar a pedido."""

    def __init__(self, esquema, fallan=(), modelo="modelo-de-prueba"):
        self.esquema = esquema
        self.fallan = set(fallan)
        self.modelo = modelo
        self.llamadas = 0
        self.imagenes = []

    def __call__(self, peticion, cache=None, espacio_cache="llm"):
        self.llamadas += 1
        self.imagenes.append(peticion.imagenes[0].datos)
        if self.llamadas in self.fallan:
            # `pedir_json` ya agoto sus tres intentos antes de llegar aca.
            raise ErrorProveedor("3 intentos fallidos contra el proveedor")
        red.exigir_red("modelo-falso")
        return RespuestaLLM(datos=respuesta_valida(self.esquema),
                            proveedor="falso", modelo=self.modelo)


@pytest.fixture(autouse=True)
def sin_variables(monkeypatch):
    monkeypatch.delenv("TF_SIN_RED", raising=False)
    monkeypatch.delenv("TF_SIN_CACHE", raising=False)
    red.LLAMADAS.reiniciar()


# --- esquema y prompt --------------------------------------------------------
def test_el_esquema_del_perfil_llega_al_json_schema(tmp_path):
    perfil = perfil_de_prueba(tmp_path, extras=["campo_propio_uno"])
    esquema = anotador.esquema_llm(perfil.esquema_anotacion())

    assert esquema["type"] == "object"
    assert esquema["additionalProperties"] is False
    assert set(esquema["required"]) == set(esquema["properties"])
    assert set(esquemas.ESQUEMA_ANOTACION_BASE) <= set(esquema["properties"])
    assert "campo_propio_uno" in esquema["properties"]

    props = esquema["properties"]
    assert props["mirada"]["enum"] == ["a_camara", "fuera_de_cuadro", "sin_rostro"]
    assert props["rostro_humano"]["type"] == "boolean"
    assert props["rostro_area_pct"]["type"] == "integer"
    assert props["contraste_texto_fondo"]["type"] == "number"
    assert props["paleta_dominante"] == {
        "type": "array", "items": {"type": "string"},
        "description": esquemas.ESQUEMA_ANOTACION_BASE["paleta_dominante"][2]}


def test_el_prompt_lista_opciones_y_declara_las_estimaciones(tmp_path):
    perfil = perfil_de_prueba(tmp_path, extras=["campo_propio_uno"])
    texto = anotador.prompt(perfil.esquema_anotacion())

    assert "a_camara | fuera_de_cuadro | sin_rostro" in texto
    assert "campo_propio_uno" in texto
    assert "ESTIMACIONES" in texto
    for campo in esquemas.ESQUEMA_ANOTACION_BASE:
        assert campo in texto


def test_los_campos_extra_no_contaminan_a_otro_perfil(tmp_path):
    con_extras = perfil_de_prueba(tmp_path / "a", extras=["campo_propio_uno"])
    sin_extras = perfil_de_prueba(tmp_path / "b")
    assert "campo_propio_uno" in anotador.esquema_llm(con_extras.esquema_anotacion())["properties"]
    assert "campo_propio_uno" not in anotador.esquema_llm(sin_extras.esquema_anotacion())["properties"]


# --- imagen ------------------------------------------------------------------
def test_la_miniatura_se_reduce_antes_de_mandarla():
    from PIL import Image

    original = jpg(1280, 720)
    reducida = anotador.reducir_imagen(original)
    with Image.open(io.BytesIO(reducida)) as im:
        assert max(im.size) == anotador.LADO_MAX
        assert im.format == "JPEG"
    assert len(reducida) < len(original)


def test_anotar_manda_la_imagen_reducida(tmp_path):
    from PIL import Image

    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=1)
    modelo = ModeloFalso(perfil.esquema_anotacion())

    anotador.anotar(perfil, cache, pedir=modelo)
    with Image.open(io.BytesIO(modelo.imagenes[0])) as im:
        assert max(im.size) == anotador.LADO_MAX


# --- corrida -----------------------------------------------------------------
def test_anota_todo_el_corpus_con_los_campos_de_sistema(tmp_path):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path, extras=["campo_propio_uno"])
    corpus(tmp_path, perfil, cache, cantidad=3)
    modelo = ModeloFalso(perfil.esquema_anotacion())

    resumen = anotador.anotar(perfil, cache, pedir=modelo)
    filas = recolector.leer_jsonl(perfil.archivo_anotaciones)

    assert resumen.anotados == 3 and resumen.fallidos == 0
    assert len(filas) == 3
    for fila in filas:
        for campo in esquemas.CAMPOS_ANOTACION_SISTEMA:
            assert campo in fila
        assert fila["error"] == ""
        assert fila["modelo"] == "modelo-de-prueba"
        assert set(perfil.esquema_anotacion()) <= set(fila)
        assert "campo_propio_uno" in fila
    # Los campos de sistema van primero: el .jsonl se lee a ojo.
    assert list(filas[0])[:4] == list(esquemas.CAMPOS_ANOTACION_SISTEMA)


def test_un_fallo_marca_error_y_el_lote_sigue(tmp_path):
    """Criterio duro: a los 3 intentos el video queda con `error` y la
    corrida continua con el resto."""
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=4)
    modelo = ModeloFalso(perfil.esquema_anotacion(), fallan={2})

    resumen = anotador.anotar(perfil, cache, pedir=modelo)
    por_id = {f["video_id"]: f for f in recolector.leer_jsonl(perfil.archivo_anotaciones)}

    assert modelo.llamadas == 4                  # no aborto en el segundo
    assert resumen.anotados == 3 and resumen.fallidos == 1
    assert len(por_id) == 4
    fallido = por_id["v1"]
    assert "3 intentos fallidos" in fallido["error"]
    # Igual trae todas las columnas, con valores neutros: M3 lee una tabla.
    assert set(perfil.esquema_anotacion()) <= set(fallido)
    assert fallido["rostro_humano"] is False
    assert all(por_id[v]["error"] == "" for v in ("v0", "v2", "v3"))


def test_video_sin_miniatura_queda_con_error_y_no_llama_al_modelo(tmp_path):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=2, con_miniatura=False)
    modelo = ModeloFalso(perfil.esquema_anotacion())

    resumen = anotador.anotar(perfil, cache, pedir=modelo)
    assert modelo.llamadas == 0
    assert resumen.sin_miniatura == 2
    filas = recolector.leer_jsonl(perfil.archivo_anotaciones)
    assert all("miniatura" in f["error"] for f in filas)


# --- idempotencia ------------------------------------------------------------
def test_no_reanota_lo_ya_anotado_ni_sale_a_la_red(tmp_path, monkeypatch):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=3)
    modelo = ModeloFalso(perfil.esquema_anotacion())

    primera = anotador.anotar(perfil, cache, pedir=modelo)
    assert primera.anotados == 3 and primera.llamadas_red == 3

    monkeypatch.setenv("TF_SIN_RED", "1")
    llamadas_primera = red.LLAMADAS.total
    segunda = anotador.anotar(perfil, cache, pedir=modelo)

    assert modelo.llamadas == 3                  # no volvio a preguntar
    assert segunda.reutilizados == 3 and segunda.anotados == 0
    assert segunda.llamadas_red == 0
    assert red.LLAMADAS.total == llamadas_primera
    assert len(recolector.leer_jsonl(perfil.archivo_anotaciones)) == 3


def test_reintenta_solo_los_que_habian_fallado(tmp_path):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=3)

    anotador.anotar(perfil, cache, pedir=ModeloFalso(perfil.esquema_anotacion(), fallan={2}))
    segundo = ModeloFalso(perfil.esquema_anotacion())
    resumen = anotador.anotar(perfil, cache, pedir=segundo)

    assert segundo.llamadas == 1                 # solo el que tenia error
    assert resumen.anotados == 1 and resumen.reutilizados == 2
    assert all(f["error"] == "" for f in recolector.leer_jsonl(perfil.archivo_anotaciones))


def test_refrescar_reanota_todo(tmp_path):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=2)

    anotador.anotar(perfil, cache, pedir=ModeloFalso(perfil.esquema_anotacion()))
    segundo = ModeloFalso(perfil.esquema_anotacion())
    resumen = anotador.anotar(perfil, cache, pedir=segundo, refrescar=True)

    assert segundo.llamadas == 2
    assert resumen.anotados == 2 and resumen.reutilizados == 0


def test_limite_no_borra_las_anotaciones_de_los_que_quedaron_afuera(tmp_path):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=3)

    anotador.anotar(perfil, cache, pedir=ModeloFalso(perfil.esquema_anotacion()))
    anotador.anotar(perfil, cache, pedir=ModeloFalso(perfil.esquema_anotacion()), limite=1)
    assert len(recolector.leer_jsonl(perfil.archivo_anotaciones)) == 3


# --- errores -----------------------------------------------------------------
def test_sin_corpus_el_mensaje_manda_a_correr_m1(tmp_path):
    perfil = perfil_de_prueba(tmp_path)
    with pytest.raises(ErrorThumbforge) as exc:
        anotador.anotar(perfil, Cache(tmp_path / "cache"),
                        pedir=ModeloFalso(perfil.esquema_anotacion()))
    assert "thumbforge corpus" in str(exc.value)


def test_respuesta_incompleta_se_completa_con_valores_neutros(tmp_path):
    cache = Cache(tmp_path / "cache")
    perfil = perfil_de_prueba(tmp_path)
    corpus(tmp_path, perfil, cache, cantidad=1)

    def parcial(peticion, cache=None, espacio_cache="llm"):
        red.exigir_red("modelo-falso")
        return RespuestaLLM(datos={"sujeto_principal": "persona"}, modelo="m")

    anotador.anotar(perfil, cache, pedir=parcial)
    fila = recolector.leer_jsonl(perfil.archivo_anotaciones)[0]
    assert fila["sujeto_principal"] == "persona"
    assert fila["paleta_dominante"] == []
    assert fila["texto_literal"] == ""
    assert fila["texto_palabras"] == 0
    assert set(perfil.esquema_anotacion()) <= set(fila)
