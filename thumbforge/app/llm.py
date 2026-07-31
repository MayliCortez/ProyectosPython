"""Cliente de modelo, con salida JSON garantizada.

Lo usan M2 (vision sobre miniaturas) y M4 (conceptos a partir del guion). El
perfil no elige el proveedor: eso es infraestructura y vive en .env.

Dos decisiones que no son obvias:

- La salida JSON se pide con `output_config.format` (structured outputs), no
  con "devolveme JSON y nada mas" y despues a limpiar cercos de markdown. El
  modelo queda restringido por el esquema y el parseo deja de fallar.
- No se manda `temperature` ni `top_p`. Los modelos actuales de Anthropic los
  rechazan con 400; lo que gradua profundidad y gasto es `effort`.
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

from . import proveedores, red
from .cache import Cache, huella
from .errores import ErrorProveedor

# Se pueden pisar por entorno sin tocar codigo.
MODELO_ANTHROPIC = os.environ.get("TF_MODELO_ANTHROPIC", "claude-opus-5")
MODELO_OPENAI = os.environ.get("TF_MODELO_OPENAI", "gpt-4o")

REINTENTOS = 3
ESPERA_BASE = 2.0


@dataclass
class RespuestaLLM:
    datos: dict
    proveedor: str = ""
    modelo: str = ""
    desde_cache: bool = False
    tokens_entrada: int = 0
    tokens_salida: int = 0
    intentos: int = 1
    aviso: str = ""


@dataclass
class Imagen:
    """Imagen para el prompt de vision."""

    datos: bytes
    tipo: str = "image/jpeg"

    def base64(self) -> str:
        return base64.standard_b64encode(self.datos).decode("ascii")


@dataclass
class Peticion:
    sistema: str
    usuario: str
    esquema: dict                      # JSON Schema de la respuesta
    imagenes: list[Imagen] = field(default_factory=list)
    max_tokens: int = 4096
    esfuerzo: str = "medium"           # low | medium | high | xhigh | max

    def clave(self) -> str:
        """Huella de todo lo que puede cambiar la respuesta."""
        return huella(self.sistema, self.usuario, self.esquema, self.esfuerzo,
                      [i.datos for i in self.imagenes])


# --- Anthropic ---------------------------------------------------------------
def _pedir_anthropic(p: Peticion, clave_api: str) -> RespuestaLLM:
    import anthropic

    contenido: list[dict] = [
        {"type": "image",
         "source": {"type": "base64", "media_type": img.tipo, "data": img.base64()}}
        for img in p.imagenes
    ]
    contenido.append({"type": "text", "text": p.usuario})

    red.exigir_red("anthropic")
    cliente = anthropic.Anthropic(api_key=clave_api, timeout=red.TIEMPO_LIMITE)
    respuesta = cliente.messages.create(
        model=MODELO_ANTHROPIC,
        max_tokens=p.max_tokens,
        system=p.sistema,
        messages=[{"role": "user", "content": contenido}],
        output_config={
            "effort": p.esfuerzo,
            "format": {"type": "json_schema", "schema": p.esquema},
        },
    )

    # El modelo puede declinar la peticion: llega HTTP 200 con stop_reason
    # 'refusal' y content vacio. Leer content[0] a ciegas revienta aca.
    if respuesta.stop_reason == "refusal":
        detalle = getattr(respuesta, "stop_details", None)
        motivo = getattr(detalle, "category", None) or "sin categoria"
        raise ErrorProveedor(
            f"El modelo rechazo la peticion (categoria: {motivo}). "
            f"Si el guion toca un tema sensible, reformulalo o revisa el perfil."
        )

    texto = "".join(b.text for b in respuesta.content if b.type == "text")
    uso = respuesta.usage
    return RespuestaLLM(
        datos=json.loads(texto),
        proveedor="anthropic",
        modelo=respuesta.model,
        tokens_entrada=getattr(uso, "input_tokens", 0),
        tokens_salida=getattr(uso, "output_tokens", 0),
    )


# --- OpenAI ------------------------------------------------------------------
def _pedir_openai(p: Peticion, clave_api: str) -> RespuestaLLM:
    contenido: list[dict] = [
        {"type": "image_url",
         "image_url": {"url": f"data:{img.tipo};base64,{img.base64()}"}}
        for img in p.imagenes
    ]
    contenido.append({"type": "text", "text": p.usuario})

    cuerpo = {
        "model": MODELO_OPENAI,
        "max_tokens": p.max_tokens,
        "messages": [
            {"role": "system", "content": p.sistema},
            {"role": "user", "content": contenido},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "respuesta", "strict": True, "schema": p.esquema},
        },
    }

    with red.cliente("openai") as c:
        r = c.post("https://api.openai.com/v1/chat/completions",
                   headers={"Authorization": f"Bearer {clave_api}"}, json=cuerpo)
    if r.status_code != 200:
        raise ErrorProveedor(f"OpenAI respondio HTTP {r.status_code}: {r.text[:300]}")

    cuerpo_resp = r.json()
    mensaje = cuerpo_resp["choices"][0]["message"]
    if mensaje.get("refusal"):
        raise ErrorProveedor(f"El modelo rechazo la peticion: {mensaje['refusal']}")

    uso = cuerpo_resp.get("usage", {})
    return RespuestaLLM(
        datos=json.loads(mensaje["content"]),
        proveedor="openai",
        modelo=cuerpo_resp.get("model", MODELO_OPENAI),
        tokens_entrada=uso.get("prompt_tokens", 0),
        tokens_salida=uso.get("completion_tokens", 0),
    )


# --- entrada publica ---------------------------------------------------------
def pedir_json(peticion: Peticion, cache: Cache | None = None,
               espacio_cache: str = "llm", reintentos: int = REINTENTOS) -> RespuestaLLM:
    """Pide una respuesta JSON al proveedor configurado.

    Reintenta con backoff exponencial. Si el JSON no parsea, el error vuelve
    al modelo como feedback en el intento siguiente.
    """
    clave = peticion.clave()

    if cache is not None:
        guardado = cache.leer_json(espacio_cache, clave)
        if guardado is not None:
            cache.stats.aciertos += 1
            return RespuestaLLM(datos=guardado["datos"], proveedor=guardado.get("proveedor", ""),
                                modelo=guardado.get("modelo", ""), desde_cache=True)
        cache.stats.fallos += 1

    prov = proveedores.proveedor_llm()
    clave_api = prov.clave()
    if not clave_api:
        raise ErrorProveedor(
            f"Falta {prov.var_entorno} en .env para hablar con {prov.nombre}. "
            f"Corre 'thumbforge doctor' para ver que mas falta."
        )

    implementaciones = {"anthropic": _pedir_anthropic, "openai": _pedir_openai}
    if prov.id not in implementaciones:
        raise ErrorProveedor(f"El proveedor '{prov.id}' no sabe generar texto.")
    llamar = implementaciones[prov.id]

    peticion_actual = peticion
    ultimo_error: Exception | None = None

    for intento in range(1, reintentos + 1):
        try:
            respuesta = llamar(peticion_actual, clave_api)
            respuesta.intentos = intento
            if cache is not None:
                cache.guardar_json(espacio_cache, clave, {
                    "datos": respuesta.datos, "proveedor": respuesta.proveedor,
                    "modelo": respuesta.modelo})
            return respuesta

        except red.ErrorSinRed:
            raise  # el modo offline no se reintenta: es intencional

        except json.JSONDecodeError as exc:
            # Devolver el error como contexto suele arreglarlo en el intento
            # siguiente, y cuesta menos que abandonar la miniatura.
            ultimo_error = exc
            peticion_actual = Peticion(
                sistema=peticion.sistema,
                usuario=(f"{peticion.usuario}\n\n[Intento {intento} fallido: la respuesta "
                         f"anterior no era JSON valido ({exc}). Devolve solo JSON que "
                         f"cumpla el esquema.]"),
                esquema=peticion.esquema, imagenes=peticion.imagenes,
                max_tokens=peticion.max_tokens, esfuerzo=peticion.esfuerzo)

        except Exception as exc:  # noqa: BLE001 - se reintenta y despues se informa
            ultimo_error = exc

        if intento < reintentos:
            espera = ESPERA_BASE * (2 ** (intento - 1)) + random.uniform(0, 1)
            time.sleep(espera)

    raise ErrorProveedor(
        f"{reintentos} intentos fallidos contra {prov.nombre}. Ultimo error: {ultimo_error}")


def esquema_json(propiedades: dict[str, Any], requeridas: list[str] | None = None) -> dict:
    """Arma un JSON Schema con las restricciones que exigen los proveedores:
    objeto cerrado y lista explicita de requeridas."""
    return {
        "type": "object",
        "properties": propiedades,
        "required": requeridas if requeridas is not None else list(propiedades),
        "additionalProperties": False,
    }
