"""Esquemas comunes a todos los nichos.

Nada de lo que hay aca es especifico de un canal. Lo especifico se suma
desde `campos_extra_anotacion` del perfil.
"""

from __future__ import annotations

# --- M2 anotador: esquema base ---------------------------------------------
# clave -> (tipo, opciones|None, descripcion)
ESQUEMA_ANOTACION_BASE: dict[str, tuple] = {
    "sujeto_principal": ("enum", ["persona", "objeto", "escena", "texto", "grafico", "otro"],
                         "Que ocupa el rol protagonico del encuadre."),
    "rostro_humano": ("bool", None, "Hay al menos un rostro humano visible."),
    "rostro_area_pct": ("int", None, "Porcentaje del area total que ocupa el rostro mas grande. 0 si no hay."),
    "mirada": ("enum", ["a_camara", "fuera_de_cuadro", "sin_rostro"], "Direccion de la mirada."),
    "emocion": ("enum", ["miedo", "asombro", "determinacion", "dolor", "neutra", "ninguna"],
                "Emocion legible en el sujeto."),
    "texto_presente": ("bool", None, "Hay texto sobreimpreso."),
    "texto_literal": ("str", None, "El texto tal cual aparece. Cadena vacia si no hay."),
    "texto_palabras": ("int", None, "Cantidad de palabras del texto sobreimpreso."),
    "texto_posicion": ("enum", ["izq_sup", "izq_inf", "der_sup", "der_inf", "centro"],
                       "Cuadrante donde cae el bloque de texto."),
    "texto_area_pct": ("int", None, "Porcentaje del area que ocupa el bloque de texto."),
    "paleta_dominante": ("list[str]", None, "Dos a cuatro colores dominantes en hex."),
    "contraste_texto_fondo": ("float", None, "Razon de contraste WCAG entre texto y su fondo inmediato."),
    "profundidad": ("enum", ["primer_plano_unico", "dos_planos", "escena_amplia"], "Estructura de planos."),
    "elementos_graficos": ("list[str]", None, "Flechas, circulos, marcos, iconos, numeros."),
    "densidad": ("enum", ["limpia", "media", "saturada"], "Cuanto ocupa el encuadre."),
}

# Campos que agrega el motor, no el modelo de vision.
CAMPOS_ANOTACION_SISTEMA = ("video_id", "anotado_en", "modelo", "error")


# --- M4 brief: esquema de concepto -----------------------------------------
# Un concepto es lo que el motor de politicas evalua. Las claves son
# genericas: `origen` y `categoria` son el vocabulario con el que cualquier
# perfil expresa sus permisos y sus prohibiciones.
ORIGENES_VISUALES = ("foto_archivo", "foto_editada", "generada")

ESQUEMA_CONCEPTO = {
    "id": "str",
    "estrategia": "str",
    "eje": "str",
    "hipotesis": "str",
    "copy": {
        "texto": "str",
        "nombre_reconocible": "str",
        "entidades": "list[{tipo,valor}]",
    },
    "base_visual": {
        "origen": "|".join(ORIGENES_VISUALES),
        "categoria": "str",
        "descripcion": "str",
        "fuente_sugerida": "str",
    },
    "capas": "list[{origen,categoria,descripcion}]",
    "reglas_aplicadas": "list[str]",
}

EJES_ESTRATEGIA = (
    "rostro_humano_vs_objeto",
    "momento_de_tension_vs_consecuencia",
    "texto_que_nombra_vs_texto_que_pregunta",
)


def esquema_anotacion(campos_extra: list[str] | None = None) -> dict[str, tuple]:
    """Esquema base + los campos que pide el perfil."""
    esquema = dict(ESQUEMA_ANOTACION_BASE)
    for campo in campos_extra or []:
        if campo not in esquema:
            esquema[campo] = ("str", None, f"Campo propio del perfil: {campo}.")
    return esquema
