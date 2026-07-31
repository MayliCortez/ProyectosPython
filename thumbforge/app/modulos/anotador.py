"""M2 - anotador del corpus con modelo de vision.

Toma las miniaturas que M1 dejo en la cache y las convierte en filas
estructuradas: `perfiles/<slug>/corpus/anotaciones.jsonl`, un registro por
video.

El esquema no esta escrito aca. Sale de `esquemas.ESQUEMA_ANOTACION_BASE` mas
los `campos_extra_anotacion` del perfil, via `perfil.esquema_anotacion()`. Este
modulo solo lo traduce a dos cosas: un JSON Schema para el proveedor y un
prompt legible para el modelo. Agregar un campo de anotacion es editar el YAML
del perfil, no este archivo.

Dos decisiones que se pagan caro si se ignoran:

- La miniatura se reduce antes de mandarla. Una maxres de YouTube son
  1280x720; para decir si hay un rostro y donde cae el texto alcanza con un
  lado de 512, y la imagen se paga por token.
- Una anotacion que falla los tres intentos no aborta el lote. El video queda
  con `error` cargado y la corrida sigue: perder 40 anotaciones buenas porque
  la 41 disparo un rate limit no es una opcion.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import llm, red
from ..cache import Cache
from ..errores import ErrorThumbforge
from ..perfiles import Perfil
from . import recolector

# Lado maximo del lado largo de la imagen que se manda al modelo.
LADO_MAX = 512
CALIDAD_JPEG = 82
ESPACIO_LLM = "anotaciones"
ESPACIO_REDUCIDAS = "miniaturas_reducidas"

# Vision con esquema cerrado: no hace falta presupuesto de razonamiento largo,
# y `esfuerzo` es lo que gradua gasto en los modelos actuales.
ESFUERZO = "medium"
MAX_TOKENS = 2048

SISTEMA = (
    "Sos un analista visual. Describis miniaturas de video con criterios "
    "observables y repetibles. No opinas sobre la calidad ni sobre el tema: "
    "solo registras lo que se ve. Respondes unicamente con un objeto JSON que "
    "cumple el esquema pedido, sin texto alrededor."
)


# --- traduccion del esquema del perfil ---------------------------------------
_TIPOS_JSON = {
    "str": {"type": "string"},
    "bool": {"type": "boolean"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "list[str]": {"type": "array", "items": {"type": "string"}},
}


def propiedades_json(esquema: dict[str, tuple]) -> dict[str, dict]:
    """dict del perfil -> `properties` de un JSON Schema.

    Los enum viajan como restriccion del esquema y no solo como texto del
    prompt: asi el proveedor no puede devolver un valor de fantasia que
    despues haya que normalizar a mano en M3.
    """
    propiedades: dict[str, dict] = {}
    for campo, definicion in esquema.items():
        tipo, opciones, descripcion = _desarmar(definicion)
        if tipo == "enum":
            propiedad: dict[str, Any] = {"type": "string", "enum": list(opciones or [])}
        else:
            propiedad = dict(_TIPOS_JSON.get(tipo, _TIPOS_JSON["str"]))
        if descripcion:
            propiedad["description"] = descripcion
        propiedades[campo] = propiedad
    return propiedades


def _desarmar(definicion: Any) -> tuple[str, list | None, str]:
    """Tolera definiciones de 1, 2 o 3 elementos, o un tipo pelado."""
    if isinstance(definicion, str):
        return definicion, None, ""
    partes = list(definicion) + [None, None, None]
    tipo = str(partes[0] or "str")
    opciones = partes[1] if isinstance(partes[1], (list, tuple)) else None
    descripcion = str(partes[2] or "")
    return tipo, list(opciones) if opciones else None, descripcion


def esquema_llm(esquema: dict[str, tuple]) -> dict:
    return llm.esquema_json(propiedades_json(esquema))


def prompt(esquema: dict[str, tuple]) -> str:
    """Arma el pedido a partir del esquema, campo por campo."""
    lineas = [
        "Anota esta miniatura de video. Devolve un unico objeto JSON con exactamente "
        "estos campos:",
        "",
    ]
    for campo, definicion in esquema.items():
        tipo, opciones, descripcion = _desarmar(definicion)
        if tipo == "enum":
            forma = "uno de: " + " | ".join(opciones or [])
        elif tipo == "list[str]":
            forma = "lista de cadenas"
        elif tipo == "bool":
            forma = "true o false"
        elif tipo in ("int", "float"):
            forma = "numero"
        else:
            forma = "texto"
        lineas.append(f"- {campo} ({forma}): {descripcion}".rstrip())
    lineas += [
        "",
        "Reglas:",
        "- Describi solo lo que se ve en la imagen. No infieras el tema del video "
        "ni uses el titulo.",
        "- Los campos numericos de area, porcentaje y contraste son ESTIMACIONES tuyas "
        "a ojo, no mediciones: aproximalas con criterio y no las dejes vacias.",
        "- Los porcentajes van de 0 a 100. Si el elemento no esta, va 0.",
        "- Los colores van en hexadecimal con almohadilla, por ejemplo #1A2B3C.",
        "- Si un campo no aplica, usa el valor neutro de su tipo (cadena vacia, lista "
        "vacia, 0 o false), nunca null.",
    ]
    return "\n".join(lineas)


# --- imagen ------------------------------------------------------------------
def reducir_imagen(datos: bytes, lado_max: int = LADO_MAX) -> bytes:
    """Reduce y reencoda a JPEG.

    Una maxres de 1280x720 no aporta nada sobre 512 para decidir si hay un
    rostro o donde cae el texto, y se paga por token de imagen.
    """
    from PIL import Image

    with Image.open(io.BytesIO(datos)) as im:
        im = im.convert("RGB")
        im.thumbnail((lado_max, lado_max), Image.LANCZOS)
        buffer = io.BytesIO()
        im.save(buffer, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
    return buffer.getvalue()


def _miniatura(registro: dict, cache: Cache) -> bytes:
    """Bytes de la miniatura que dejo M1. Nunca sale a la red."""
    ruta = Path(str(registro.get("miniatura_ruta") or ""))
    if not ruta.is_file():
        # La cache puede haberse mudado de volumen: la clave sobrevive a la ruta.
        clave = str(registro.get("miniatura_clave") or "")
        if clave:
            for sufijo in (".jpg", ".png"):
                candidata = cache.ruta(recolector.ESPACIO_MINIATURAS, clave, sufijo)
                if candidata.is_file():
                    ruta = candidata
                    break
    if not ruta.is_file():
        raise ErrorThumbforge(
            f"No hay miniatura en cache para {registro.get('video_id')}. "
            f"Corre 'thumbforge corpus' para que M1 la descargue."
        )
    return ruta.read_bytes()


# --- resumen -----------------------------------------------------------------
@dataclass
class ResumenAnotacion:
    perfil: str
    archivo: Path | None = None
    campos: int = 0
    videos: int = 0
    anotados: int = 0
    reutilizados: int = 0
    desde_cache: int = 0
    fallidos: int = 0
    sin_miniatura: int = 0
    llamadas_red: int = 0
    errores: list[str] = field(default_factory=list)

    def texto(self) -> str:
        lineas = [
            f"perfil            {self.perfil}",
            f"campos            {self.campos} (base + campos_extra_anotacion del perfil)",
            f"videos            {self.videos}",
            f"anotados          {self.anotados} ({self.desde_cache} desde cache)",
            f"ya estaban        {self.reutilizados}",
            f"sin miniatura     {self.sin_miniatura}",
            f"con error         {self.fallidos}",
            f"escritos          {self.anotados + self.reutilizados + self.fallidos} "
            f"-> {self.archivo}",
            f"llamadas de red   {self.llamadas_red}",
        ]
        lineas += [f"error             {e}" for e in self.errores[:10]]
        return "\n".join(lineas)


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalizar(datos: dict, esquema: dict[str, tuple]) -> dict:
    """Se queda con los campos del esquema y completa los que falten.

    El proveedor los garantiza, pero un doble de prueba o un modelo futuro
    pueden no hacerlo, y M3 necesita que todas las filas tengan las mismas
    columnas.
    """
    salida: dict[str, Any] = {}
    for campo, definicion in esquema.items():
        tipo, _, _ = _desarmar(definicion)
        if campo in datos:
            salida[campo] = datos[campo]
        elif tipo == "list[str]":
            salida[campo] = []
        elif tipo == "bool":
            salida[campo] = False
        elif tipo in ("int", "float"):
            salida[campo] = 0
        else:
            salida[campo] = ""
    return salida


def _registro(video_id: str, modelo: str, datos: dict, esquema: dict[str, tuple],
              error: str = "") -> dict:
    # Los campos de sistema van primero: leer el .jsonl a ojo tiene que
    # empezar por saber de que video se habla y si fallo.
    registro = {
        "video_id": video_id,
        "anotado_en": _ahora(),
        "modelo": modelo,
        "error": error,
    }
    registro.update(_normalizar(datos, esquema))
    return registro


# --- entrada publica ---------------------------------------------------------
def anotar(perfil: Perfil, cache: Cache | None = None, refrescar: bool = False,
           limite: int | None = None,
           pedir: Callable[..., llm.RespuestaLLM] | None = None) -> ResumenAnotacion:
    """Anota las miniaturas del corpus y escribe `corpus/anotaciones.jsonl`.

    Es idempotente: un video con registro previo sin `error` no se vuelve a
    anotar salvo `refrescar=True`. Un video que falla queda con `error`
    cargado y la corrida continua con el resto.

    `pedir` existe para inyectar un doble en las pruebas; por defecto es
    `llm.pedir_json`, que ya reintenta con backoff y garantiza JSON por
    esquema.
    """
    cache = cache if cache is not None else Cache()
    pedir = pedir if pedir is not None else llm.pedir_json
    llamadas_antes = red.LLAMADAS.total

    esquema = perfil.esquema_anotacion()
    resumen = ResumenAnotacion(perfil=perfil.slug, archivo=perfil.archivo_anotaciones,
                               campos=len(esquema))

    videos = recolector.leer_jsonl(perfil.archivo_videos)
    if not videos:
        raise ErrorThumbforge(
            f"No hay corpus que anotar en {perfil.archivo_videos}. "
            f"Corre 'thumbforge corpus --perfil {perfil.slug}' primero: M2 anota lo que "
            f"M1 recolecto, no sale a buscar videos."
        )
    if limite is not None:
        videos = videos[:max(0, int(limite))]
    resumen.videos = len(videos)

    previas = {str(r.get("video_id")): r
               for r in recolector.leer_jsonl(perfil.archivo_anotaciones)
               if r.get("video_id")}

    esquema_json_ = esquema_llm(esquema)
    texto_prompt = prompt(esquema)
    salida: list[dict] = []

    for video in videos:
        video_id = str(video.get("video_id") or "")
        if not video_id:
            continue

        anterior = previas.get(video_id)
        if anterior is not None and not anterior.get("error") and not refrescar:
            resumen.reutilizados += 1
            salida.append(anterior)
            continue

        try:
            imagen = reducir_imagen(_miniatura(video, cache))
        except ErrorThumbforge as exc:
            resumen.sin_miniatura += 1
            resumen.errores.append(f"{video_id}: {exc}")
            salida.append(_registro(video_id, "", {}, esquema, error=str(exc)))
            continue
        except Exception as exc:  # noqa: BLE001 - una imagen rota no corta el lote
            resumen.sin_miniatura += 1
            resumen.errores.append(f"{video_id}: miniatura ilegible ({exc})")
            salida.append(_registro(video_id, "", {}, esquema,
                                    error=f"miniatura ilegible: {exc}"))
            continue

        peticion = llm.Peticion(
            sistema=SISTEMA,
            usuario=texto_prompt,
            esquema=esquema_json_,
            imagenes=[llm.Imagen(datos=imagen, tipo="image/jpeg")],
            max_tokens=MAX_TOKENS,
            esfuerzo=ESFUERZO,
        )
        if refrescar:
            # `pedir_json` no tiene modo refresco: se le saca la entrada de
            # abajo para que vuelva a preguntar y a cachear.
            cache.ruta(ESPACIO_LLM, peticion.clave()).unlink(missing_ok=True)

        try:
            respuesta = pedir(peticion, cache=cache, espacio_cache=ESPACIO_LLM)
        except Exception as exc:  # noqa: BLE001 - ver docstring: el lote sigue
            # `pedir_json` ya agoto sus tres intentos con backoff. Insistir
            # aca solo multiplicaria la espera; lo util es dejar constancia y
            # que un `--refrescar` posterior reintente solo estos.
            resumen.fallidos += 1
            resumen.errores.append(f"{video_id}: {type(exc).__name__}: {exc}")
            salida.append(_registro(video_id, "", {}, esquema, error=str(exc)))
            continue

        resumen.anotados += 1
        if respuesta.desde_cache:
            resumen.desde_cache += 1
        salida.append(_registro(video_id, respuesta.modelo, respuesta.datos, esquema))

    # Con `limite`, los videos que quedaron fuera de esta corrida conservan su
    # anotacion previa: el archivo se reescribe entero y perderlas seria tirar
    # tokens ya pagados.
    vistos = {r["video_id"] for r in salida}
    salida.extend(r for vid, r in previas.items() if vid not in vistos)

    recolector.escribir_jsonl(perfil.archivo_anotaciones, salida)
    resumen.llamadas_red = red.LLAMADAS.total - llamadas_antes
    return resumen
