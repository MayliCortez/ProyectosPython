"""M4 - brief. Sin red y sin claves: el modelo se inyecta.

Lo que se prueba aca no es que el modulo llame a un LLM, sino que se niegue a
entregar lo que el perfil prohibe, que las tres variantes sean tres apuestas y
no una repintada tres veces, y que una regla inventada no pase en silencio.
"""

from __future__ import annotations

import copy as copiar
import json
import shutil
from pathlib import Path

import pytest

from app import llm, red
from app import perfiles as mod_perfiles
from app import politicas
from app.cache import Cache
from app.modulos import brief

RAIZ = Path(__file__).resolve().parent.parent


# --- utilidades ---------------------------------------------------------------
@pytest.fixture(autouse=True)
def volumenes_aislados(tmp_path, monkeypatch):
    """Ni la salida ni la cache del repo se ensucian al correr las pruebas."""
    monkeypatch.setenv("TF_SALIDA_DIR", str(tmp_path / "salida"))
    monkeypatch.setenv("TF_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("TF_SIN_RED", raising=False)
    monkeypatch.delenv("TF_SIN_CACHE", raising=False)
    red.LLAMADAS.reiniciar()


def generador_fijo(*tandas):
    """Modelo simulado: una tanda de conceptos por intento.

    Guarda las peticiones para poder mirar que feedback recibio en la vuelta
    siguiente, que es la mitad del contrato del reintento.
    """
    peticiones: list[llm.Peticion] = []

    def generar(peticion: llm.Peticion) -> llm.RespuestaLLM:
        peticiones.append(peticion)
        tanda = tandas[min(len(peticiones) - 1, len(tandas) - 1)]
        return llm.RespuestaLLM(datos={"conceptos": copiar.deepcopy(tanda)})

    generar.peticiones = peticiones  # type: ignore[attr-defined]
    return generar


def perfil_tc():
    return mod_perfiles.cargar_perfil("true_crime")


GUION = (
    "# La lista que nadie miro\n\n"
    "Habia una lista de verificacion firmada y completa. El aviso llego dos "
    "semanas antes y quedo archivado esperando una revision programada.\n\n"
    "El hecho duro cuarenta segundos. El informe final dice que el sistema "
    "funciono exactamente como estaba disenado.\n"
)
TITULO = "El expediente que estuvo catorce anos en un cajon"


def concepto(cid, eje, estrategia, hipotesis, texto, categoria, descripcion,
             origen="foto_archivo", reglas=None, licencia="CC BY 4.0", capas=None,
             entidades=None):
    return {
        "id": cid,
        "estrategia": estrategia,
        "eje": eje,
        "hipotesis": hipotesis,
        "copy": {"texto": texto, "entidades": entidades or [{"tipo": "hecho", "valor": "revision"}]},
        "base_visual": {"origen": origen, "categoria": categoria,
                        "descripcion": descripcion, "fuente_sugerida": "archivo publico",
                        "licencia": licencia},
        "capas": capas if capas is not None else [],
        "reglas_aplicadas": reglas if reglas is not None else [],
    }


def tanda_valida(reglas=None):
    """Tres conceptos que cumplen la politica de `true_crime`: solo archivo,
    copy de tres palabras y un eje distinto cada uno."""
    return [
        concepto("tc-objeto", "rostro_humano_vs_objeto",
                 "el papel como sujeto",
                 "La carpeta sellada ocupa el cuadro y afirma que el caso existe.",
                 "Catorce anos despues", "documento_judicial",
                 "Carpeta de expediente sellada, luz lateral dura.", reglas=reglas),
        concepto("tc-tension", "momento_de_tension_vs_consecuencia",
                 "el instante previo",
                 "Un pasillo vacio antes del hallazgo mantiene la respiracion en suspenso.",
                 "La ultima ronda", "lugar_real",
                 "Pasillo institucional nocturno, iluminacion tenue.", reglas=reglas),
        concepto("tc-pregunta", "texto_que_nombra_vs_texto_que_pregunta",
                 "el texto interroga",
                 "Preguntar quien autorizo convierte al espectador en investigador.",
                 "Quien firmo eso", "objeto_cotidiano",
                 "Formulario firmado en primer plano, sello ilegible.", reglas=reglas),
    ]


def tanda_con_rostro_generado():
    """La segunda variante intenta exactamente lo que el perfil bloquea:
    generar con IA a una persona real."""
    tanda = tanda_valida()
    tanda[1] = concepto(
        "tc-rostro-generado", "momento_de_tension_vs_consecuencia",
        "rostro sintetico del acusado",
        "Un retrato del acusado da cara al relato y sostiene la mirada.",
        "El vecino silencioso", "perpetrador",
        "Retrato fotorrealista del acusado, mirada a camara.",
        origen="generada", licencia="")
    return tanda


# --- 1. la politica es una restriccion dura ------------------------------------
def test_rechaza_generar_con_ia_a_una_persona_real_con_el_motivo_del_yaml():
    """Criterio de aceptacion: el perfil rechaza con mensaje explicito
    cualquier concepto que intente generar con IA a una persona real, y el
    motivo que ve el usuario es el declarado en perfil.yaml."""
    generar = generador_fijo(tanda_con_rostro_generado())

    with pytest.raises(brief.ErrorBrief) as exc:
        brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                max_intentos=1, generador=generar)

    mensaje = str(exc.value)
    assert "tc-rostro-generado" in mensaje
    assert "ia_sobre_persona_real" in mensaje
    # El motivo NO es un texto del modulo: sale de politica_base_visual.razon.
    assert "derecho de imagen" in mensaje
    assert "difamacion" in mensaje
    assert "politica de plataforma" in mensaje
    # Y se dice que perfil las impone y donde estan escritas.
    assert "true_crime" in mensaje and "perfil.yaml" in mensaje

    codigos = {r.codigo for r in exc.value.rechazos}
    assert {"ia_sobre_persona_real", "ia_prohibida_para_categoria",
            "origen_no_permitido"} <= codigos


def test_nunca_entrega_un_concepto_con_violaciones_duras():
    """Aunque dos de los tres conceptos esten bien, el juego no se entrega."""
    generar = generador_fijo(tanda_con_rostro_generado())
    with pytest.raises(brief.ErrorBrief):
        brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                max_intentos=1, generador=generar)


# --- 2. el reintento con feedback ----------------------------------------------
def test_el_reintento_pasa_el_error_como_feedback_y_acepta_la_correccion():
    generar = generador_fijo(tanda_con_rostro_generado(), tanda_valida())

    resultado = brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                        generador=generar)

    assert resultado.ok
    assert resultado.intentos == 2
    assert [c["id"] for c in resultado.conceptos] == ["tc-objeto", "tc-tension", "tc-pregunta"]

    # El segundo prompt lleva el rechazo del primero, con el motivo del YAML.
    segundo = generar.peticiones[1].usuario
    assert "Intento 1 RECHAZADO" in segundo
    assert "ia_sobre_persona_real" in segundo
    assert "derecho de imagen" in segundo
    assert "true_crime" in segundo
    # El primero no lo llevaba: el feedback aparece porque hubo un rechazo.
    assert "RECHAZADO" not in generar.peticiones[0].usuario

    # El rechazo intermedio se le muestra al usuario: es una feature.
    assert any(r.concepto_id == "tc-rostro-generado" for r in resultado.rechazos)
    assert "derecho de imagen" in resultado.informe() or any(
        "derecho de imagen" in r.detalle for r in resultado.rechazos)


# --- 3. el tope de reintentos ---------------------------------------------------
def test_se_agota_el_tope_y_falla_con_un_mensaje_util():
    generar = generador_fijo(tanda_con_rostro_generado())

    with pytest.raises(brief.ErrorBrief) as exc:
        brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                max_intentos=3, generador=generar)

    assert len(generar.peticiones) == 3
    mensaje = str(exc.value)
    assert "agoto los 3 intentos" in mensaje
    assert "true_crime" in mensaje
    assert "ia_sobre_persona_real" in mensaje
    # Las violaciones quedan accesibles para quien atrape el error.
    assert any(v.codigo == "ia_sobre_persona_real" for v in exc.value.violaciones)


# --- 4. las diferidas no rechazan ------------------------------------------------
def test_las_diferidas_no_rechazan_y_viajan_como_pendientes_para_m5():
    tanda = tanda_valida()
    # Persona real de archivo, sin licencia resuelta: el perfil lo difiere.
    tanda[0]["base_visual"].update({"categoria": "persona_real", "licencia": ""})
    generar = generador_fijo(tanda)

    resultado = brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                        generador=generar)

    assert resultado.ok
    assert resultado.intentos == 1
    assert [v.codigo for v in resultado.pendientes] == ["licencia_pendiente"]
    assert all(x.severidad == politicas.SEV_DIFERIDA for x in resultado.pendientes)
    assert "PENDIENTE para M5" in resultado.informe()


# --- 5. distancia estrategica ----------------------------------------------------
def test_tres_conceptos_en_el_mismo_eje_se_rechazan():
    tanda = tanda_valida()
    for c in tanda:
        c["eje"] = "rostro_humano_vs_objeto"
    generar = generador_fijo(tanda)

    with pytest.raises(brief.ErrorBrief) as exc:
        brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                max_intentos=1, generador=generar)

    repetidos = [r for r in exc.value.rechazos if r.codigo == "eje_repetido"]
    assert len(repetidos) == 2
    assert "ejes distintos" in repetidos[0].detalle


def test_dos_conceptos_con_el_mismo_encuadre_se_rechazan_aunque_cambien_de_eje():
    """Repintar la misma idea y cambiarle la etiqueta del eje no alcanza."""
    tanda = tanda_valida()
    gemelo = copiar.deepcopy(tanda[0])
    gemelo["id"] = "tc-gemelo"
    gemelo["eje"] = "momento_de_tension_vs_consecuencia"
    tanda[1] = gemelo
    generar = generador_fijo(tanda)

    with pytest.raises(brief.ErrorBrief) as exc:
        brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                max_intentos=1, generador=generar)

    encuadre = [r for r in exc.value.rechazos if r.codigo == "encuadre_repetido"]
    assert encuadre and encuadre[0].concepto_id == "tc-gemelo"


def test_un_eje_inventado_se_rechaza():
    tanda = tanda_valida()
    tanda[2]["eje"] = "colores_calidos_vs_frios"
    generar = generador_fijo(tanda)

    with pytest.raises(brief.ErrorBrief) as exc:
        brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                max_intentos=1, generador=generar)
    assert any(r.codigo == "eje_invalido" for r in exc.value.rechazos)


# --- 6. trazabilidad de reglas ----------------------------------------------------
REGLAS_MD = """\
# Reglas identificadas del corpus

Generado por M3 sobre 120 miniaturas anotadas.

## R1 - Un solo sujeto en el cuadro
Los encuadres con un unico sujeto rinden por encima de la mediana del canal.

- **R2**: El texto no supera las tres palabras.
- R3. Evitar el rojo saturado como color dominante.

| Regla | Enunciado | Soporte |
|---|---|---|
| R4 | Reservar el cuadrante inferior derecho para el logo | 0.71 |

> R5 (descartada): usar flechas amarillas.
"""


@pytest.fixture
def perfil_con_reglas(tmp_path):
    """Copia del perfil en tmp, con corpus/reglas.md. No se toca perfiles/."""
    destino = tmp_path / "perfiles" / "true_crime"
    shutil.copytree(RAIZ / "perfiles" / "true_crime", destino)
    (destino / "corpus").mkdir(exist_ok=True)
    (destino / "corpus" / "reglas.md").write_text(REGLAS_MD, "utf-8")
    return mod_perfiles.cargar_perfil_en(destino)


def test_el_lector_de_reglas_tolera_los_formatos_de_markdown(perfil_con_reglas):
    reglas = brief.reglas_del_perfil(perfil_con_reglas)
    assert [r.id for r in reglas] == ["R1", "R2", "R3", "R4", "R5"]
    assert reglas[0].texto.startswith("Un solo sujeto")
    assert reglas[1].texto == "El texto no supera las tres palabras."
    assert reglas[3].texto.startswith("Reservar el cuadrante")
    # La descartada se lee, pero no se ofrece al modelo ni se puede citar.
    assert reglas[4].activa is False
    assert "R5" not in brief.prompt_usuario(
        brief.preparar_guion(GUION), reglas, TITULO)


def test_un_identificador_de_regla_inventado_se_detecta(perfil_con_reglas):
    generar = generador_fijo(tanda_valida(reglas=["R1", "R9"]))

    with pytest.raises(brief.ErrorBrief) as exc:
        brief.generar_conceptos(perfil_con_reglas, GUION, titulo=TITULO,
                                max_intentos=1, generador=generar)

    inventadas = [r for r in exc.value.rechazos if r.codigo == "regla_inexistente"]
    assert len(inventadas) == 3
    assert "R9" in inventadas[0].detalle
    assert "R1, R2, R3, R4" in inventadas[0].detalle


def test_las_reglas_citadas_que_existen_pasan_y_quedan_en_el_brief(perfil_con_reglas):
    generar = generador_fijo(tanda_valida(reglas=["R1", "R2"]))
    resultado = brief.generar_conceptos(perfil_con_reglas, GUION, titulo=TITULO,
                                        generador=generar)
    assert resultado.ok
    assert all(c["reglas_aplicadas"] == ["R1", "R2"] for c in resultado.conceptos)
    assert "R1." in generar.peticiones[0].usuario


def test_sin_reglas_no_falla_pero_lo_dice():
    generar = generador_fijo(tanda_valida())
    # El perfil del repo no tiene corpus/reglas.md todavia.
    resultado = brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO,
                                        generador=generar)
    assert resultado.ok
    assert any("reglas.md" in a for a in resultado.avisos)


# --- 7. cache -------------------------------------------------------------------
def test_el_mismo_guion_dos_veces_no_sale_a_la_red_la_segunda(tmp_path, monkeypatch):
    cache = Cache(tmp_path / "cache")
    generar = generador_fijo(tanda_valida())

    primero = brief.generar_conceptos(perfil_tc(), GUION, cache, titulo=TITULO,
                                      reglas=[], generador=generar)
    assert primero.desde_cache is False
    assert len(generar.peticiones) == 1

    # Segunda corrida: red cortada de raiz y sin generador inyectado. Si
    # faltara una sola lectura de cache, esto explota con ErrorSinRed o
    # ErrorProveedor en vez de devolver el brief.
    monkeypatch.setenv("TF_SIN_RED", "1")
    red.LLAMADAS.reiniciar()
    segundo = brief.generar_conceptos(perfil_tc(), GUION, Cache(tmp_path / "cache"),
                                      titulo=TITULO, reglas=[])

    assert segundo.desde_cache is True
    assert red.LLAMADAS.total == 0
    assert [c["id"] for c in segundo.conceptos] == [c["id"] for c in primero.conceptos]
    assert len(generar.peticiones) == 1        # el modelo no se volvio a llamar


def test_cambiar_el_guion_invalida_la_cache(tmp_path):
    cache = Cache(tmp_path / "cache")
    generar = generador_fijo(tanda_valida())
    brief.generar_conceptos(perfil_tc(), GUION, cache, titulo=TITULO, reglas=[],
                            generador=generar)
    brief.generar_conceptos(perfil_tc(), GUION + "\nUn parrafo mas.\n", cache,
                            titulo=TITULO, reglas=[], generador=generar)
    assert len(generar.peticiones) == 2


def test_cambiar_las_reglas_activas_invalida_la_cache(tmp_path):
    cache = Cache(tmp_path / "cache")
    generar = generador_fijo(tanda_valida(reglas=["R1"]))
    brief.generar_conceptos(perfil_tc(), GUION, cache, titulo=TITULO, reglas=[],
                            generador=generar)
    brief.generar_conceptos(perfil_tc(), GUION, cache, titulo=TITULO,
                            reglas=[brief.Regla("R1", "Un solo sujeto")],
                            generador=generar)
    assert len(generar.peticiones) == 2


# --- 8. el guion ------------------------------------------------------------------
def test_extrae_titulo_del_frontmatter_y_del_encabezado():
    g = brief.preparar_guion("---\ntitulo: \"Desde el front matter\"\n---\n\n# Otro\n\nCuerpo.\n")
    assert g.titulo == "Desde el front matter"
    assert "Cuerpo." in g.cuerpo and "# Otro" not in g.cuerpo

    g2 = brief.preparar_guion("# Desde el encabezado\n\nCuerpo.\n")
    assert g2.titulo == "Desde el encabezado"


def test_el_guion_de_ejemplo_se_lee_entero():
    g = brief.cargar_guion(RAIZ / "guiones" / "ejemplo.md")
    assert g.titulo == "Lo que nadie reviso antes de salir"
    assert g.recortado is False
    assert "Cierre" in g.cuerpo


def test_un_guion_largo_no_se_trunca_en_silencio():
    largo = ("ARRANQUE del episodio.\n\n"
             + "\n\n".join(f"Parrafo intermedio numero {i} con relleno suficiente."
                           for i in range(400))
             + "\n\nCIERRE del episodio.\n")
    g = brief.preparar_guion(largo, limite=2000)

    assert g.recortado is True
    assert "ARRANQUE" in g.cuerpo and "CIERRE" in g.cuerpo   # gancho y consecuencia
    assert "tramo intermedio del guion omitido" in g.cuerpo
    assert g.aviso and "TF_BRIEF_LIMITE_GUION" in g.aviso


def test_el_recorte_llega_al_usuario_y_al_prompt(monkeypatch):
    largo = ("ARRANQUE.\n\n" + "\n\n".join(f"Relleno {i}." for i in range(3000))
             + "\n\nCIERRE.\n")
    monkeypatch.setattr(brief, "LIMITE_GUION", 1500)
    generar = generador_fijo(tanda_valida())
    resultado = brief.generar_conceptos(perfil_tc(), largo, titulo=TITULO, reglas=[],
                                        generador=generar)
    assert any("se omitieron" in a.lower() or "omitieron" in a for a in resultado.avisos)
    assert "AVISO SOBRE EL GUION" in generar.peticiones[0].usuario


# --- 9. el prompt -------------------------------------------------------------------
def test_la_politica_del_perfil_se_inyecta_desde_el_yaml():
    perfil = perfil_tc()
    sistema = brief.prompt_sistema(perfil)
    # El volcado es el de politicas, no una serializacion propia.
    assert politicas.politica_para_prompt(perfil) in sistema
    assert "generacion_ia_prohibida_para" in sistema
    assert "derecho de imagen" in sistema
    for eje in ("rostro_humano_vs_objeto", "momento_de_tension_vs_consecuencia",
                "texto_que_nombra_vs_texto_que_pregunta"):
        assert eje in sistema


def test_dos_perfiles_distintos_producen_dos_prompts_distintos():
    a = brief.prompt_sistema(mod_perfiles.cargar_perfil("gdc"))
    b = brief.prompt_sistema(mod_perfiles.cargar_perfil("tech"))
    assert a != b
    assert "nombre_reconocible" in a and "nombre_reconocible" not in b


def test_el_esquema_de_respuesta_sale_del_perfil():
    esquema_tc = brief.esquema_respuesta(perfil_tc())
    concepto = esquema_tc["properties"]["conceptos"]["items"]["properties"]
    # El perfil solo admite archivo: el esquema ni siquiera ofrece 'generada'.
    assert concepto["base_visual"]["properties"]["origen"]["enum"] == ["foto_archivo"]
    assert esquema_tc["properties"]["conceptos"]["minItems"] == 3

    esquema_tech = brief.esquema_respuesta(mod_perfiles.cargar_perfil("tech"))
    copy_tech = esquema_tech["properties"]["conceptos"]["items"]["properties"]["copy"]
    # `copy.debe_incluir` del YAML se convierte en un campo del esquema.
    assert "producto" in copy_tech["properties"]
    assert "producto" not in concepto["copy"]["properties"]


# --- 10. el entregable ----------------------------------------------------------------
def test_escribe_el_brief_en_la_salida():
    generar = generador_fijo(tanda_valida())
    resultado = brief.generar_conceptos(perfil_tc(), GUION, titulo=TITULO, reglas=[],
                                        nombre_guion="ejemplo", generador=generar)

    assert resultado.archivo is not None and resultado.archivo.is_file()
    assert resultado.archivo.name == "brief_true_crime_ejemplo.json"
    datos = json.loads(resultado.archivo.read_text("utf-8"))
    assert datos["perfil"] == "true_crime"
    assert len(datos["conceptos"]) == 3
    assert {"pendientes", "rechazos", "avisos", "reglas_disponibles"} <= set(datos)


def test_otro_perfil_acepta_lo_que_true_crime_prohibe():
    """La misma cadena, otro YAML: lo que alla se rechaza, aca pasa. La
    diferencia esta entera en el perfil."""
    perfil = mod_perfiles.cargar_perfil("gdc")
    tanda = [
        concepto("gdc-objeto", "rostro_humano_vs_objeto", "objeto como sujeto",
                 "El fuselaje danado cuenta el riesgo sin texto explicativo.",
                 "El regreso del P-51", "aeronave_identificable",
                 "Maquina con danos de combate, tres cuartos delantero.",
                 capas=[{"origen": "generada", "categoria": "cielo",
                         "descripcion": "Cielo cargado al atardecer.",
                         "fuente_sugerida": "generacion", "licencia": ""}]),
        concepto("gdc-tension", "momento_de_tension_vs_consecuencia", "el instante",
                 "La pista vacia antes del aterrizaje sostiene la espera.",
                 "Ultimo vuelo del P-51", "pista_de_aterrizaje",
                 "Pista desierta al amanecer, niebla baja."),
        concepto("gdc-pregunta", "texto_que_nombra_vs_texto_que_pregunta", "interrogar",
                 "Preguntar por el destino del P-51 abre una incognita concreta.",
                 "Donde quedo el P-51", "hangar",
                 "Interior de hangar con una silueta cubierta."),
    ]
    for c in tanda:
        c["copy"]["nombre_reconocible"] = "P-51"
    generar = generador_fijo(tanda)

    resultado = brief.generar_conceptos(perfil, GUION, titulo=TITULO, reglas=[],
                                        generador=generar)
    assert resultado.ok and resultado.intentos == 1
