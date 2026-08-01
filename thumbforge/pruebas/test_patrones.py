"""M3 - patrones: cruce de metadata con anotaciones y destilado de reglas.

Los corpus son sinteticos y se arman aca mismo: cada prueba dice que senal
sembro, asi cuando falla se sabe si se rompio el analisis o la siembra.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app import perfiles as mod_perfiles
from app.modulos import patrones


# --- andamiaje ---------------------------------------------------------------
# Dos valores por campo categorico: la clase 0 y la clase 1. Sembrar el corpus
# con estas tablas hace que el efecto esperado sea evidente al leer la prueba.
VALORES = {
    "sujeto_principal": ["objeto", "persona"],
    "rostro_humano": [False, True],
    "mirada": ["fuera_de_cuadro", "a_camara"],
    "emocion": ["neutra", "miedo"],
    "texto_presente": [False, True],
    "texto_literal": ["uno", "dos"],
    "texto_posicion": ["der_inf", "izq_sup"],
    "profundidad": ["escena_amplia", "primer_plano_unico"],
    "densidad": ["saturada", "limpia"],
}


def hacer_perfil(tmp_path: Path, slug: str = "perfil_de_prueba",
                 campos_extra: list[str] | None = None):
    raiz = tmp_path / slug
    (raiz / "corpus").mkdir(parents=True, exist_ok=True)
    (raiz / "perfil.yaml").write_text(
        yaml.safe_dump({
            "nombre": "Perfil de prueba",
            "idioma": "es",
            "campos_extra_anotacion": campos_extra or [],
        }, allow_unicode=True),
        "utf-8",
    )
    return mod_perfiles.cargar_perfil_en(raiz)


def anotacion(video_id: str, clase: int, i: int = 0) -> dict:
    """Anotacion completa donde todos los campos siguen a `clase`."""
    datos = {campo: valores[clase] for campo, valores in VALORES.items()}
    datos.update({
        "video_id": video_id,
        "anotado_en": "2026-07-31T00:00:00Z",
        "modelo": "prueba",
        "rostro_area_pct": 10 + clase * 30 + (i % 3),
        "texto_palabras": 2 + clase * 4,
        "texto_area_pct": 5 + clase * 10 + (i % 2),
        "contraste_texto_fondo": 3.0 + clase * 4.0 + (i % 3) * 0.1,
        "paleta_dominante": ["#111111", "#222222"] if clase else ["#333333"],
        "elementos_graficos": ["flecha"] if clase else [],
    })
    return datos


def volcar_jsonl(ruta: Path, registros: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in registros) + "\n", "utf-8")


def corpus_por_clase(perfil, clases: list[int], puntajes: list[float],
                     prefijo: str = "v") -> None:
    """Escribe videos.jsonl y anotaciones.jsonl a partir de clase + puntaje."""
    videos, anotaciones = [], []
    for i, (clase, score) in enumerate(zip(clases, puntajes)):
        vid = f"{prefijo}{i:03d}"
        videos.append({
            "video_id": vid, "canal_id": "canal1", "canal_titulo": "Canal 1",
            "titulo": f"titulo {i}", "publicado_en": "2026-01-01T00:00:00Z",
            "duracion_s": 600, "views": int(1000 * score), "likes": 10,
            "comentarios": 2, "miniatura_url": f"http://x/{vid}.jpg",
            "mediana_canal": 1000, "outlier_score": score,
            "recolectado_en": "2026-07-31T00:00:00Z",
        })
        anotaciones.append(anotacion(vid, clase, i))
    volcar_jsonl(perfil.archivo_videos, videos)
    volcar_jsonl(perfil.archivo_anotaciones, anotaciones)


def corpus_alternado(perfil, total: int = 60, bajo: float = 1.0, alto: float = 2.0):
    clases = [i % 2 for i in range(total)]
    puntajes = [alto if c else bajo for c in clases]
    corpus_por_clase(perfil, clases, puntajes)
    return clases, puntajes


def ids(reglas) -> list[str]:
    return [r.id for r in reglas]


def campos(reglas) -> set[str]:
    return {r.campo for r in reglas}


# --- n minima ----------------------------------------------------------------
def test_corpus_chico_no_emite_reglas_y_se_marca_insuficiente(tmp_path):
    """Con 6 videos cruzados no hay dos grupos de 8: no se publica nada."""
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=6)

    informe = patrones.analizar(perfil)
    assert informe.corpus.n_total == 6
    assert informe.corpus.reglas == []
    assert informe.reglas_activas() == []

    md = patrones.render_markdown(informe)
    assert patrones.MARCA_INSUFICIENTE in md
    assert "no se emite ninguna regla" in md.lower()


def test_grupo_chico_se_marca_insuficiente_y_no_genera_regla(tmp_path):
    """El corpus alcanza, pero un valor del campo aparece 3 veces: ese corte
    se informa con su n y no llega a regla."""
    perfil = hacer_perfil(tmp_path)
    # 3 videos de clase 1 con puntaje altisimo contra 27 de clase 0.
    clases = [1, 1, 1] + [0] * 27
    puntajes = [9.0, 9.5, 9.9] + [1.0 + (i % 4) * 0.1 for i in range(27)]
    corpus_por_clase(perfil, clases, puntajes)

    informe = patrones.analizar(perfil)
    assert informe.corpus.n_total == 30
    # Ningun campo categorico puede dar regla: el lado chico tiene n=3.
    assert "mirada" not in campos(informe.corpus.reglas)

    insuficientes = [d for d in informe.corpus.insuficientes if d.campo == "mirada"]
    assert insuficientes, "el corte de mirada tenia que quedar registrado"
    assert min(d.n_grupo for d in insuficientes) == 3

    md = patrones.render_markdown(informe)
    assert patrones.MARCA_INSUFICIENTE in md
    assert "`mirada`" in md
    # La n del corte descartado aparece en la misma linea que la marca.
    linea = next(ln for ln in md.splitlines()
                 if "`mirada`" in ln and patrones.MARCA_INSUFICIENTE in ln)
    assert "n grupo=" in linea and "resto=" in linea


def test_la_n_minima_es_configurable_pero_por_defecto_es_ocho():
    assert patrones.N_MINIMA == 8


# --- medianas, no promedios ---------------------------------------------------
def test_un_viral_extremo_no_cambia_ninguna_regla(tmp_path):
    """Se reemplaza el puntaje mas alto por uno 500 veces mayor.

    La mediana de cualquier grupo que contenga ese video no se mueve (cambiar
    el maximo de un conjunto no mueve su mediana); un promedio se iria a la
    estratosfera. Las reglas tienen que salir identicas.
    """
    clases = [i % 2 for i in range(60)]
    puntajes = [2.0 if c else 1.0 for c in clases]

    normal = hacer_perfil(tmp_path / "a")
    corpus_por_clase(normal, clases, puntajes)
    reglas_normales = patrones.analizar(normal).corpus.reglas

    con_viral = hacer_perfil(tmp_path / "b")
    extremos = list(puntajes)
    extremos[extremos.index(max(extremos))] = 1000.0
    corpus_por_clase(con_viral, clases, extremos)
    reglas_virales = patrones.analizar(con_viral).corpus.reglas

    assert reglas_normales, "la siembra tenia que producir reglas"
    assert [(r.id, r.campo, r.grupo, r.n_grupo, r.n_resto, r.mediana_grupo,
             r.mediana_resto, round(r.efecto, 9)) for r in reglas_normales] == \
           [(r.id, r.campo, r.grupo, r.n_grupo, r.n_resto, r.mediana_grupo,
             r.mediana_resto, round(r.efecto, 9)) for r in reglas_virales]

    # Y el promedio si se habria movido: la prueba no es trivial.
    assert sum(extremos) / len(extremos) > 5 * (sum(puntajes) / len(puntajes))


# --- tope de reglas -----------------------------------------------------------
def test_tope_de_siete_reglas_activas(tmp_path):
    """Con todos los campos correlacionados con el puntaje hay mas de siete
    candidatas; se publican siete y las demas quedan listadas."""
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)

    informe = patrones.analizar(perfil)
    assert len(informe.corpus.reglas) == patrones.MAX_REGLAS == 7
    assert informe.corpus.sobrantes, "las candidatas sobrantes tienen que informarse"
    # Un campo, una regla: nada de publicar el mismo corte dado vuelta.
    assert len(campos(informe.corpus.reglas)) == len(informe.corpus.reglas)
    assert ids(informe.corpus.reglas) == [f"R{i}" for i in range(1, 8)]

    md = patrones.render_markdown(informe)
    assert "tope de 7 reglas" in md


def test_las_reglas_estan_en_imperativo(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    reglas = patrones.analizar(perfil).corpus.reglas
    verbos = ("Pone ", "Evita ", "Inclui ", "Mantene ", "Saca ")
    for regla in reglas:
        assert regla.texto.startswith(verbos), regla.texto


def test_orden_por_tamano_del_efecto(tmp_path):
    perfil = hacer_perfil(tmp_path)
    # Efectos deliberadamente distintos por campo: el puntaje depende de
    # `emocion` con fuerza y de los demas campos apenas.
    videos, anotaciones = [], []
    for i in range(60):
        vid = f"v{i:03d}"
        clase = i % 2
        anot = anotacion(vid, clase, i)
        # `mirada` se desacopla: sigue un patron con muy poco efecto.
        anot["mirada"] = VALORES["mirada"][i % 2 if i % 7 else 1 - i % 2]
        anotaciones.append(anot)
        videos.append({"video_id": vid, "outlier_score": 3.0 if clase else 1.0})
    volcar_jsonl(perfil.archivo_videos, videos)
    volcar_jsonl(perfil.archivo_anotaciones, anotaciones)

    reglas = patrones.analizar(perfil).corpus.reglas
    efectos = [abs(r.efecto) for r in reglas]
    assert efectos == sorted(efectos, reverse=True)


# --- trazabilidad y lectura de vuelta ----------------------------------------
def test_cada_regla_es_rastreable_hasta_una_linea_con_su_n(tmp_path):
    """Criterio de aceptacion del proyecto: M4 cita R3 y desde ahi se llega
    al corte, a la n de cada grupo y a las medianas comparadas."""
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)

    informe = patrones.analizar(perfil)
    ruta = patrones.escribir_reglas(informe)
    assert ruta == perfil.archivo_reglas and ruta.is_file()
    md = ruta.read_text("utf-8")

    for regla in informe.reglas_activas():
        titulo = f"### {regla.id} - {regla.texto}"
        assert titulo in md
        bloque = md.split(titulo, 1)[1].split("### ", 1)[0]
        assert f"n: grupo={regla.n_grupo} / resto={regla.n_resto}" in bloque
        assert f"mediana {regla.metrica}:" in bloque
        assert regla.campo in bloque


def test_leer_reglas_devuelve_lo_que_se_escribio(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    informe = patrones.analizar(perfil)
    patrones.escribir_reglas(informe)

    leidas = patrones.leer_reglas(perfil)
    assert ids(leidas) == ids(informe.reglas_activas())
    assert [r.n_grupo for r in leidas] == [r.n_grupo for r in informe.reglas_activas()]
    assert all(r.texto and r.campo for r in leidas)


def test_leer_reglas_sobrevive_a_que_borren_el_apendice(tmp_path):
    """Si alguien edita el .md y se lleva puesto el JSON, las reglas siguen
    saliendo del markdown: la trazabilidad esta en el texto, no en el anexo."""
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    informe = patrones.analizar(perfil)
    ruta = patrones.escribir_reglas(informe)
    ruta.write_text(ruta.read_text("utf-8").split(patrones.MARCA_DATOS)[0], "utf-8")

    leidas = patrones.leer_reglas(perfil)
    assert ids(leidas) == ids(informe.reglas_activas())
    for original, leida in zip(informe.reglas_activas(), leidas):
        assert leida.n_grupo == original.n_grupo
        assert leida.n_resto == original.n_resto
        assert leida.campo == original.campo


def test_leer_reglas_sin_archivo_explica_como_generarlo(tmp_path):
    perfil = hacer_perfil(tmp_path)
    with pytest.raises(patrones.ErrorCorpus) as exc:
        patrones.leer_reglas(perfil)
    assert "thumbforge reglas" in str(exc.value)


# --- lectura tolerante --------------------------------------------------------
def test_lineas_rotas_y_registros_con_error_se_cuentan_y_no_voltean_la_corrida(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)

    with perfil.archivo_videos.open("a", encoding="utf-8") as fh:
        fh.write("{esto no es json\n")
        fh.write(json.dumps({"video_id": "sin_score", "views": 10}) + "\n")
        fh.write(json.dumps({"canal_id": "x"}) + "\n")
    with perfil.archivo_anotaciones.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"video_id": "z1", "error": "timeout del modelo"}) + "\n")
        fh.write("\n")

    informe = patrones.analizar(perfil)
    assert informe.lecturas["videos_json_invalido"] == 1
    assert informe.lecturas["videos_sin_video_id"] == 1
    assert informe.lecturas["videos_sin_outlier_score"] == 1
    assert informe.lecturas["anotaciones_con_error"] == 1
    assert informe.corpus.n_total == 60


def test_outlier_score_se_reconstruye_si_no_viene_hecho(tmp_path):
    perfil = hacer_perfil(tmp_path)
    videos, anotaciones = [], []
    for i in range(40):
        vid = f"v{i:03d}"
        clase = i % 2
        videos.append({"video_id": vid, "views": 2000 if clase else 1000,
                       "mediana_canal": 1000})
        anotaciones.append(anotacion(vid, clase, i))
    volcar_jsonl(perfil.archivo_videos, videos)
    volcar_jsonl(perfil.archivo_anotaciones, anotaciones)

    informe = patrones.analizar(perfil)
    assert informe.corpus.n_total == 40
    assert informe.corpus.reglas


def test_campos_extra_del_perfil_entran_al_analisis(tmp_path):
    """El motor no conoce el campo: lo toma de `campos_extra_anotacion`."""
    perfil = hacer_perfil(tmp_path, campos_extra=["campo_propio_del_perfil"])
    videos, anotaciones = [], []
    for i in range(40):
        vid = f"v{i:03d}"
        clase = i % 2
        anot = anotacion(vid, clase, i)
        anot["campo_propio_del_perfil"] = "alfa" if clase else "beta"
        anotaciones.append(anot)
        videos.append({"video_id": vid, "outlier_score": 2.0 if clase else 1.0})
    volcar_jsonl(perfil.archivo_videos, videos)
    volcar_jsonl(perfil.archivo_anotaciones, anotaciones)

    informe = patrones.analizar(perfil, max_reglas=20)
    assert "campo_propio_del_perfil" in campos(informe.corpus.reglas)


# --- mi_ctr.csv ---------------------------------------------------------------
CABECERA_ES = ("Contenido;Titulo del video;Impresiones;"
               "Porcentaje de clics de las impresiones (%);Vistas")


def test_ctr_con_bom_punto_y_coma_y_coma_decimal(tmp_path):
    ruta = tmp_path / "mi_ctr.csv"
    # \ufeff es el BOM que deja el export bajado desde Windows.
    ruta.write_bytes(
        ("\ufeff" + CABECERA_ES + "\n"
         "Total;;12.000;4,8;900\n"
         "aaaaaaaaaaa;Uno;5.000;6,4;300\n"
         "bbbbbbbbbbb;Dos;7.000;3,25;600\n").encode("utf-8")
    )
    lectura = patrones.leer_ctr(ruta)
    assert lectura.separador == ";"
    assert lectura.columna_id == "Contenido"
    assert lectura.columna_ctr == "Porcentaje de clics de las impresiones (%)"
    assert lectura.valores["aaaaaaaaaaa"] == 6.4
    assert lectura.valores["bbbbbbbbbbb"] == 3.25


def test_ctr_en_ingles_con_coma_y_simbolo_de_porcentaje(tmp_path):
    ruta = tmp_path / "mi_ctr.csv"
    ruta.write_text(
        "Content,Video title,Impressions,Impressions click-through rate (%),Views\n"
        "aaaaaaaaaaa,One,5000,6.4%,300\n"
        "bbbbbbbbbbb,Two,7000,3.25%,600\n", "utf-8")
    lectura = patrones.leer_ctr(ruta)
    assert lectura.separador == ","
    assert lectura.columna_ctr == "Impressions click-through rate (%)"
    assert lectura.valores == {"aaaaaaaaaaa": 6.4, "bbbbbbbbbbb": 3.25}


def test_ctr_sin_encabezado_reconocible_usa_la_forma_del_id(tmp_path):
    ruta = tmp_path / "mi_ctr.csv"
    ruta.write_text(
        "columna rara;CTR\n"
        "aaaaaaaaaaa;6,4\n"
        "bbbbbbbbbbb;3,25\n", "utf-8")
    lectura = patrones.leer_ctr(ruta)
    assert lectura.columna_id == "columna rara"
    assert lectura.valores["aaaaaaaaaaa"] == 6.4


def test_ctr_sin_columna_de_ctr_dice_exactamente_que_falta(tmp_path):
    ruta = tmp_path / "mi_ctr.csv"
    ruta.write_text("Contenido,Impresiones,Vistas\naaaaaaaaaaa,100,10\n", "utf-8")
    with pytest.raises(patrones.ErrorCorpus) as exc:
        patrones.leer_ctr(ruta)
    mensaje = str(exc.value)
    assert "falta la columna de CTR" in mensaje
    assert "Impresiones" in mensaje            # dice que encabezados si estan
    assert "Modo avanzado" in mensaje          # y de donde sacar el que falta


def test_ctr_sin_columna_de_id_dice_exactamente_que_falta(tmp_path):
    ruta = tmp_path / "mi_ctr.csv"
    ruta.write_text("Titulo,Porcentaje de clics (%)\nUn titulo,6.4\n", "utf-8")
    with pytest.raises(patrones.ErrorCorpus) as exc:
        patrones.leer_ctr(ruta)
    assert "falta la columna de id de video" in str(exc.value)


def test_csv_ilegible_no_voltea_el_informe_del_corpus(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    perfil.archivo_ctr.write_text("Titulo,Impresiones\nUn titulo,100\n", "utf-8")

    informe = patrones.analizar(perfil)
    assert informe.corpus.reglas, "el corpus ajeno se analiza igual"
    assert any("falta la columna" in a for a in informe.avisos)
    md = patrones.render_markdown(informe)
    assert "No se pudo usar" in md


# --- informe de CTR propio ----------------------------------------------------
def sembrar_ctr(perfil, *, invertido: bool, total: int = 40) -> None:
    """Agrega videos propios anotados y su CTR. Con `invertido` el CTR premia
    la clase contraria a la que premia el corpus ajeno."""
    anotaciones = [json.loads(ln) for ln in
                   perfil.archivo_anotaciones.read_text("utf-8").splitlines() if ln.strip()]
    filas = ["Contenido;Porcentaje de clics de las impresiones (%)"]
    for i in range(total):
        vid = f"p{i:03d}"
        clase = i % 2
        anotaciones.append(anotacion(vid, clase, i))
        bueno = (clase == 0) if invertido else (clase == 1)
        filas.append(f"{vid};{'8,0' if bueno else '3,0'}")
    volcar_jsonl(perfil.archivo_anotaciones, anotaciones)
    perfil.archivo_ctr.write_text("\n".join(filas) + "\n", "utf-8")


def test_el_informe_de_ctr_propio_va_primero_y_se_declara_que_pesa_mas(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    sembrar_ctr(perfil, invertido=False)

    informe = patrones.analizar(perfil)
    assert informe.ctr is not None and informe.ctr.reglas
    assert ids(informe.ctr.reglas)[0] == "C1"
    # Las reglas activas arrancan por las del CTR propio.
    assert informe.reglas_activas()[0].fuente == patrones.FUENTE_CTR
    assert all(r.pesa_mas for r in informe.ctr.reglas)

    md = patrones.render_markdown(informe)
    assert md.index("Informe A - CTR propio") < md.index("Informe B - corpus ajeno")
    assert "pesan mas" in md


def test_conflicto_entre_ctr_propio_y_corpus_ajeno_queda_marcado(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    sembrar_ctr(perfil, invertido=True)

    informe = patrones.analizar(perfil)
    assert informe.conflictos, "el CTR premia la clase contraria: tiene que chocar"
    conflicto = informe.conflictos[0]
    assert conflicto.regla_ctr.startswith("C") and conflicto.regla_corpus.startswith("R")

    md = patrones.render_markdown(informe)
    assert "CONFLICTO" in md
    assert "Gana el CTR propio" in md
    assert f"Aplica {conflicto.regla_ctr}" in md


def test_sin_mi_ctr_el_informe_explica_de_donde_sale_el_ctr(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)

    informe = patrones.analizar(perfil)
    assert informe.ctr is None
    md = patrones.render_markdown(informe)
    assert "No hay `corpus/mi_ctr.csv`" in md
    assert "no es CTR" in md
    assert "Modo avanzado" in md


def test_ctr_sin_anotaciones_cruzadas_avisa_en_vez_de_callarse(tmp_path):
    perfil = hacer_perfil(tmp_path)
    corpus_alternado(perfil, total=60)
    perfil.archivo_ctr.write_text(
        "Contenido;Porcentaje de clics (%)\nzzzzzzzzzzz;5,5\n", "utf-8")

    informe = patrones.analizar(perfil)
    assert informe.ctr is not None and informe.ctr.n_total == 0
    assert any("anotaciones.jsonl" in a for a in informe.avisos)


# --- documentacion ------------------------------------------------------------
def test_docs_reglas_dice_lo_que_tiene_que_decir():
    doc = (Path(__file__).resolve().parent.parent / "docs" / "reglas.md").read_text("utf-8")
    assert "El CTR ajeno no existe en ninguna API" in doc
    assert "no es CTR" in doc
    assert "rendimiento relativo" in doc
