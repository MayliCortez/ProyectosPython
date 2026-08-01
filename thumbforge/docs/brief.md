# M4 - brief

Guion + politica del perfil + reglas del corpus -> **tres conceptos de miniatura
en JSON**, ninguno de los cuales viola una politica dura del perfil.

Codigo: `app/modulos/brief.py`. Pruebas: `pruebas/test_brief.py`.
Guion de ejemplo para probar la cadena: `guiones/ejemplo.md`.

M4 no sabe de que trata el canal. Todo lo que le da personalidad al brief entra
al prompt desde `perfil.yaml` a traves de `politicas.politica_para_prompt`. Si
alguna vez hace falta escribir una categoria concreta dentro de este modulo, el
diseno esta mal y eso va al YAML.

---

## Interfaz

```python
from app.modulos import brief

resultado = brief.generar_conceptos(
    perfil,                 # perfiles.Perfil ya cargado
    guion_texto,            # str: el Markdown crudo del guion
    cache=None,             # cache.Cache; sin ella se pierde el "cero red" de la 2da corrida
    titulo=None,            # titulo del video; si es None se toma del guion
    reglas=None,            # None = leerlas del corpus; una lista explicita la pisa
    *,
    max_intentos=brief.MAX_INTENTOS,   # 3
    generador=None,         # Callable[[llm.Peticion], llm.RespuestaLLM]; None = el LLM real
    nombre_guion=None,      # etiqueta para el archivo de salida
    escribir=True,          # escribe el JSON en rutas.dir_salida()
) -> brief.ResultadoBrief
```

Auxiliares publicas:

| Funcion | Para que |
|---|---|
| `cargar_guion(ruta)` / `preparar_guion(texto, titulo=None, limite=...)` | Markdown -> `Guion` (titulo, cuerpo, aviso de recorte) |
| `reglas_del_perfil(perfil)` | lee `corpus/reglas.md` y devuelve `list[Regla]` |
| `prompt_sistema(perfil)` / `prompt_usuario(guion, reglas, titulo, feedback)` | los prompts, inspeccionables sin gastar una llamada |
| `esquema_respuesta(perfil)` | el JSON Schema que se le exige al modelo |
| `escribir_brief(resultado, destino)` / `ruta_salida(perfil, clave, nombre)` | el entregable |

### `ResultadoBrief`

```python
@dataclass
class ResultadoBrief:
    perfil: str
    titulo: str | None
    conceptos: list[dict]                  # los 3 aprobados, con la forma de ESQUEMA_CONCEPTO
    veredictos: list[politicas.Veredicto]  # uno por concepto, en el mismo orden
    pendientes: list[politicas.Violacion]  # las DIFERIDAS: las resuelve M5
    intentos: int                          # cuantas vueltas hicieron falta
    rechazos: list[Rechazo]                # que se descarto y por que (se muestra al usuario)
    reglas: list[Regla]                    # las reglas que se le ofrecieron al modelo
    avisos: list[str]                      # recorte de guion, ausencia de reglas.md...
    desde_cache: bool
    archivo: Path | None                   # donde quedo el JSON
    # .ok -> bool ; .informe() -> str para la terminal ; .a_json() -> dict del entregable
```

```python
@dataclass
class Rechazo:
    intento: int
    concepto_id: str
    tipo: str      # politica | estrategia | trazabilidad | forma
    codigo: str    # el codigo de Violacion, o el del control propio de M4
    detalle: str   # el texto que ve el usuario, con el motivo declarado en el YAML
```

Si se agotan los intentos, `generar_conceptos` lanza `brief.ErrorBrief`
(subclase de `errores.ErrorPolitica`, asi que la CLI ya la imprime sin
traceback). Lleva `.violaciones` y `.rechazos`.

---

## El contrato del concepto

Un concepto tiene la forma de `esquemas.ESQUEMA_CONCEPTO`. Lo que M4 le exige
al modelo, campo por campo:

| Campo | Que es |
|---|---|
| `id` | identificador corto en minusculas con guiones |
| `estrategia` | la apuesta en pocas palabras |
| `eje` | uno de `esquemas.EJES_ESTRATEGIA`, distinto en cada concepto |
| `hipotesis` | por que **esa** miniatura ganaria el click, en una frase. Es lo que M6 mide, no un resumen del guion |
| `copy.texto` | el texto sobreimpreso |
| `copy.entidades` | `[{tipo, valor}]`: lo que el copy nombra, clasificado. El perfil puede prohibir tipos enteros |
| `copy.<debe_incluir>` | si el perfil declara `copy.debe_incluir`, ese campo se agrega al esquema **por nombre**, leido del YAML |
| `base_visual` y cada entrada de `capas` | `{origen, categoria, descripcion, fuente_sugerida, licencia}` |
| `reglas_aplicadas` | identificadores de `corpus/reglas.md` (`R1`, `R2`...) |

`origen` y `categoria` son el vocabulario con el que el perfil concede y niega
permisos, y por eso son obligatorios en todo elemento visual. `origen` sale de
`esquemas.ORIGENES_VISUALES`; `categoria` es texto libre, porque cada canal
nombra sus cosas como quiere y el motor no tiene por que conocerlas.

El JSON Schema que se le manda al modelo **se deriva del perfil**:

- el `enum` de `origen` es `politica_base_visual.orden_preferencia`, asi que un
  perfil que solo acepta archivo ni siquiera le ofrece al modelo la opcion de
  generar;
- el campo obligatorio del copy es el que nombre `copy.debe_incluir`;
- `conceptos` tiene `minItems == maxItems == 3`.

Aun asi se valida todo despues de recibir la respuesta. Un esquema restringe el
formato, no la conducta: el modelo puede poner `foto_archivo` y describir un
render.

---

## Los tres ejes de estrategia

Declarados en `esquemas.EJES_ESTRATEGIA`:

1. `rostro_humano_vs_objeto` — quien protagoniza el cuadro.
2. `momento_de_tension_vs_consecuencia` — antes o despues del hecho.
3. `texto_que_nombra_vs_texto_que_pregunta` — que funcion cumple el copy.

**Los tres conceptos tienen que tomar tres ejes distintos.** Cambiar la paleta,
el encuadre o la tipografia no es una variante: es la misma apuesta repintada, y
un test A/B entre tres repintados no puede ensenar nada, porque las tres pierden
o ganan por el mismo motivo.

M4 lo exige en el prompt y lo verifica en el codigo, con dos controles:

- **`eje_repetido` / `eje_invalido`** — el `eje` declarado tiene que estar en la
  lista y no puede repetirse.
- **`encuadre_repetido`** — similitud de Jaccard sobre los tokens de
  `estrategia + hipotesis + copy.texto + base_visual.categoria +
  base_visual.descripcion`, sin palabras vacias. Dos conceptos que comparten
  `UMBRAL_SIMILITUD` (0.60) o mas de su formulacion son el mismo concepto con
  otra etiqueta de eje pegada encima.

M6 tambien mide distancia entre variantes, pero esa comprobacion llega despues
de generar y componer las imagenes: cara y tarde. Se ataja aca, donde todavia
son texto.

---

## Como se rechaza y como se reintenta

```
        prompt (politica del perfil + reglas + guion)
                        |
                        v
                +----------------+
                |    modelo      |
                +----------------+
                        |
             +----------+-----------+-----------------+
             v          v           v                 v
          forma     politicas   estrategia      trazabilidad
          (3 dicts) (duras)     (ejes+similitud) (R-n existen)
             |          |           |                 |
             +----------+-----+-----+-----------------+
                              |
                    ¿algun rechazo?
                     |               |
                    si               no
                     |               |
        feedback con el error        entrega + cache + salida/
        -> intento siguiente
        (tope: MAX_INTENTOS = 3)
                     |
              tope agotado -> ErrorBrief
```

### 1. Las politicas duras no se negocian

`politicas.evaluar_conceptos(conceptos, perfil, titulo)` devuelve un `Veredicto`
por concepto. **Cualquier violacion de severidad `dura` rechaza el juego
entero**, aunque los otros dos conceptos esten impecables: no se entrega un
brief con un concepto que el perfil prohibe, ni con una advertencia al lado.

El motivo que ve el usuario **no lo escribe M4**: es el `razon` declarado en el
YAML, propagado por `Violacion.texto()`. Cambiar la explicacion del bloqueo es
editar el perfil, no el codigo.

### 2. Las diferidas no rechazan

Severidad `diferida` (por ejemplo `licencia_pendiente`, cuando el perfil exige
licencia verificada y todavia no hay ninguna): el concepto **se aprueba** y la
violacion viaja en `ResultadoBrief.pendientes` y en el JSON de salida, para que
M5 la resuelva antes de componer. Rechazar aca seria pedirle al modelo que
invente una licencia, que es exactamente lo contrario de lo que se busca.

### 3. Trazabilidad de reglas

Cada identificador que aparezca en `reglas_aplicadas` tiene que existir en
`corpus/reglas.md`. Un modelo que cita `R9` cuando hay siete reglas rompe la
trazabilidad **en silencio**, y el silencio es lo peor que le puede pasar a una
cadena de decisiones: seis meses despues nadie puede saber por que la miniatura
se decidio asi.

- `regla_inexistente` — cita un identificador que no esta en el archivo.
- `sin_trazabilidad` — hay reglas activas y el concepto no cita ninguna.
- Si **no hay** `reglas.md`, no hay nada que rastrear: el control se apaga
  entero, el brief se genera igual con la sola politica del perfil, y el
  resultado lo dice en `avisos`. No se falla por un archivo que M3 todavia no
  escribio.

### 4. El feedback

El rechazo vuelve al modelo tal cual, agrupado por tipo, con el codigo, el
mensaje y el motivo declarado en el YAML, mas la instruccion de conservar lo que
no fue observado. No se le manda "proba de nuevo": se le manda que estuvo mal y
por que.

### 5. El tope

`MAX_INTENTOS = 3`. Agotado el tope, `ErrorBrief` con la lista de lo que quedo
sin resolver en el ultimo intento y la ruta del `perfil.yaml` que impone esas
restricciones. **Nunca** se devuelve un concepto con violaciones duras: si la
restriccion ya no aplica, se cambia el YAML, no el resultado.

---

## El lector de reglas (provisional)

M3 escribe `perfiles/<slug>/corpus/reglas.md` y va a exponer su propio lector.
Mientras tanto M4 trae uno tolerante, aislado detras de un unico punto de
reemplazo:

```python
# app/modulos/brief.py
LECTOR_REGLAS: Callable[[Perfil], list[Regla]] = _lector_por_defecto
```

Cuando el de M3 exista, se asigna ahi y se borra `leer_reglas_markdown`. Nada
mas del modulo cambia.

Formatos que reconoce, todos con el identificador `R<n>` al principio de la
linea:

```markdown
## R1 - Un solo sujeto en el cuadro      <- encabezado; si no hay texto en la
El enunciado va en la linea siguiente.      misma linea, toma la siguiente

- **R2**: El texto no supera las tres palabras.
- R3. Evitar el rojo saturado como color dominante.

| R4 | Reservar el cuadrante inferior derecho para el logo | 0.71 |

> R5 (descartada): usar flechas amarillas.   <- se lee, pero queda inactiva
```

Una regla marcada como `descartada`, `inactiva`, `obsoleta` o `retirada` no se
le ofrece al modelo ni se puede citar. Los identificadores duplicados se quedan
con la primera aparicion. `reglas_del_perfil` tambien acepta `dict` o texto
suelto, por si M3 devuelve otra cosa.

---

## El guion

Entrada: Markdown. `preparar_guion` extrae:

- **Titulo**: el argumento explicito gana; si no, el front matter YAML
  (`titulo:` / `title:`); si no, el primer encabezado `#`. Cuando el titulo sale
  del encabezado, esa linea **se saca del cuerpo**: ya viaja en su propio campo,
  y el control `copy.no_duplicar_titulo` necesita comparar contra un titulo
  limpio.
- **Cuerpo**: el resto, con los saltos de linea multiples colapsados.

### Guiones largos: cabeza y cola, nunca en silencio

Limite: `LIMITE_GUION`, 12000 caracteres, ajustable con `TF_BRIEF_LIMITE_GUION`.

Por encima del limite **no se trunca**: se conserva el **60% inicial** y el
**40% final**, cortando en frontera de parrafo, y el desarrollo del medio se
reemplaza por una marca visible:

```
[...tramo intermedio del guion omitido por longitud: 41208 caracteres...]
```

Por que el arranque y el cierre y no los primeros 12000 caracteres:

- el gancho esta al principio y es de donde sale el **momento de tension**;
- el desenlace esta al final y es de donde sale la **consecuencia**;
- los dos polos del eje `momento_de_tension_vs_consecuencia` viven, entonces, en
  los extremos. Cortar por la mitad deja al modelo con un solo polo y los tres
  conceptos se le parecen.

El recorte **se informa siempre**, por partida doble:

1. al modelo, como bloque `AVISO SOBRE EL GUION` dentro del prompt, para que
   sepa que esta trabajando con material parcial;
2. al usuario, en `ResultadoBrief.avisos` y en el JSON de salida, diciendo
   cuantos caracteres se enviaron, cuantos se omitieron y como subir el limite.

Truncar en silencio es la peor opcion posible: el brief sale peor y nadie se
entera de por que.

---

## Cache

Clave: `huella(VERSION_BRIEF, slug, perfil.datos, guion.cuerpo, titulo,
reglas_activas, EJES_ESTRATEGIA, CANTIDAD_CONCEPTOS)`, espacio `brief`.

Se cachea el **brief entero**, no cada llamada suelta: la segunda corrida del
mismo guion no hace ni una llamada de red, ni siquiera para repetir los
reintentos que hicieron falta la primera vez. Se verifica con `TF_SIN_RED=1` en
`pruebas/test_brief.py::test_el_mismo_guion_dos_veces_no_sale_a_la_red_la_segunda`.

Cambia el guion, cambia una linea del `perfil.yaml`, cambia una regla activa o
cambia la version del prompt -> la clave cambia y se vuelve a pedir.

Los **veredictos no se guardan**: se recalculan al leer de cache. Evaluar es
gratis y deterministico, y asi editar el perfil no queda tapado por una cache
vieja que decia "aprobado".

---

## El entregable

`rutas.dir_salida() / brief_<slug>_<nombre|huella8>.json`:

```json
{
  "perfil": "...",
  "titulo": "...",
  "intentos": 2,
  "desde_cache": false,
  "conceptos": [ ... los 3 ... ],
  "reglas_disponibles": [{"id": "R1", "texto": "...", "activa": true}],
  "pendientes": [{"concepto": "...", "violaciones": [{"codigo": "licencia_pendiente", "...": "..."}]}],
  "rechazos": [{"intento": 1, "concepto_id": "...", "tipo": "politica", "codigo": "...", "detalle": "..."}],
  "avisos": ["..."]
}
```

`rechazos` no es ruido de debug: es el registro de que se descarto y por que, y
es lo que permite defender el brief mas adelante.

---

## Probarlo sin claves de API

`generador` es un `Callable[[llm.Peticion], llm.RespuestaLLM]`. Inyectando uno
falso se prueba la cadena completa sin red:

```python
def generador_fijo(*tandas):
    peticiones = []
    def generar(peticion):
        peticiones.append(peticion)
        return llm.RespuestaLLM(datos={"conceptos": tandas[min(len(peticiones) - 1, len(tandas) - 1)]})
    generar.peticiones = peticiones
    return generar

brief.generar_conceptos(perfil, guion, reglas=[], generador=generador_fijo(tanda_mala, tanda_buena))
```

Guardar las peticiones permite verificar lo que importa del reintento: que el
segundo prompt lleve el error del primero.
