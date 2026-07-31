# El corpus: `videos.jsonl` y `anotaciones.jsonl`

Dos archivos por perfil, en `perfiles/<slug>/corpus/`. Un objeto JSON por
linea, UTF-8, sin coma final ni corchetes envolventes. Se leen en streaming y
se pueden abrir con `head` sin cargar el archivo entero.

| Archivo | Lo escribe | Se une por |
|---|---|---|
| `videos.jsonl` | M1 `app/modulos/recolector.py` | `video_id` |
| `anotaciones.jsonl` | M2 `app/modulos/anotador.py` | `video_id` |

Ninguno de los dos sabe de que trata el canal. Las queries y los canales de
referencia salen de `corpus.queries` y `corpus.canales_referencia` del perfil;
las columnas extra de anotacion, de `campos_extra_anotacion`.

---

## El CTR ajeno no existe en ninguna API

**El CTR ajeno no existe en ninguna API.** Ni la YouTube Data API v3 ni
ninguna otra fuente publica expone el click-through rate de un video de otro
canal. Cualquier herramienta que diga estimarlo, lo esta inventando.

Lo que hay en `videos.jsonl` es otra cosa:

```
outlier_score = views / mediana_del_canal_en_la_ventana
```

Cuanto rindio un video **contra su propio canal**. Es rendimiento relativo, y
**no es CTR**. Comparar views entre canales de tamanos distintos no dice nada;
compararlas contra la mediana del mismo canal, si: 200.000 views son un exito
en un canal de 5.000 suscriptores y un fracaso en uno de 2.000.000.

El unico CTR real disponible es el propio, exportado a mano desde el Modo
Avanzado de YouTube Studio a `corpus/mi_ctr.csv`. Ese archivo es de otro
formato y de otro modulo (M3).

---

## `videos.jsonl`

### Campos

| Campo | Tipo | Que es |
|---|---|---|
| `video_id` | str | Id de YouTube. Clave de union con `anotaciones.jsonl`. |
| `canal_id` | str | Id del canal (`UC...`). Agrupador de la mediana. |
| `canal_titulo` | str | Nombre del canal al momento de recolectar. |
| `titulo` | str | Titulo del video. |
| `descripcion_corta` | str | Primeros 280 caracteres de la descripcion. |
| `publicado_en` | str | ISO-8601 UTC, `2026-04-22T19:57:23Z`. |
| `antiguedad_dias` | int | Dias entre `publicado_en` y `recolectado_en`. |
| `duracion_iso` | str | Tal cual la devuelve la API (`PT10M`). |
| `duracion_s` | int | La misma, en segundos. |
| `views` | int \| null | `statistics.viewCount`. |
| `likes` | int \| null | `statistics.likeCount`. **`null` no es `0`**: el canal puede tenerlos ocultos. |
| `comentarios` | int \| null | `statistics.commentCount`. Idem. |
| `miniatura_url` | str | URL de la resolucion mas alta disponible. |
| `miniatura_calidad` | str | `maxres` \| `standard` \| `high` \| `medium` \| `default`. |
| `miniatura_ruta` | str | Ruta absoluta del archivo ya descargado en `.cache/`. Vacia si fallo la descarga. |
| `miniatura_clave` | str | Clave de cache de esa imagen. Sobrevive a que el volumen de cache se mude de lugar; M2 la usa como respaldo de `miniatura_ruta`. |
| `mediana_canal` | float \| null | Mediana de `views` de los videos **de ese canal** dentro de la ventana. |
| `videos_del_canal_en_ventana` | int | Cuantos videos de ese canal entraron en la ventana. Es el `n` de la mediana. |
| `outlier_score` | float \| null | `views / mediana_canal`, 4 decimales. `null` cuando no se puede calcular honestamente. |
| `outlier_confiable` | bool | `true` solo si `videos_del_canal_en_ventana >= 3` y la mediana es mayor que cero. |
| `motivo_sin_outlier` | str | Vacio si hay score. Si no: `canal_con_menos_de_3_videos_en_la_ventana`, `mediana_del_canal_es_cero` o `el_video_no_reporta_views`. |
| `origen_tipo` | str | `query` \| `canal`. De donde salio el video. |
| `origen_valor` | str | La query literal o el id del canal de referencia. Sale del perfil. |
| `ventana_dias` | int | Ancho de la ventana usada (`corpus.ventana_dias`, por defecto 365). |
| `recolectado_en` | str | ISO-8601 UTC de la corrida. |

### Registro de ejemplo

```json
{"video_id":"dQw4w9WgXcQ","canal_id":"UCabc123def456","canal_titulo":"Canal de referencia","titulo":"Titulo del video de referencia","descripcion_corta":"Primeros 280 caracteres de la descripcion...","publicado_en":"2026-04-22T19:57:23Z","antiguedad_dias":100,"duracion_iso":"PT10M","duracion_s":600,"views":412000,"likes":18400,"comentarios":903,"miniatura_url":"https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg","miniatura_calidad":"maxres","miniatura_ruta":"/app/.cache/miniaturas/3f/3fe3b11f49b8ab607a33fe5d1ef688a211bb0f5eca6a38b2bb93a6988a870001.jpg","miniatura_clave":"3fe3b11f49b8ab607a33fe5d1ef688a211bb0f5eca6a38b2bb93a6988a870001","mediana_canal":101000.0,"videos_del_canal_en_ventana":7,"outlier_score":4.0792,"outlier_confiable":true,"motivo_sin_outlier":"","origen_tipo":"query","origen_valor":"<la query textual del perfil>","ventana_dias":365,"recolectado_en":"2026-07-31T19:57:23Z"}
```

### Que queda afuera

Dos filtros duros, antes de cualquier calculo:

- **Shorts**: `duracion_s < 62`. Un Short entra por otra superficie, con otra
  miniatura y otro comportamiento de audiencia; mezclarlo ensucia las
  conclusiones. El corte va en 62 s y no en 60 porque YouTube redondea y deja
  pasar videos de 61.
- **Videos recientes**: menos de 14 dias. Todavia estan acumulando views: su
  `outlier_score` seria ruido.
- Ademas, un video cuya `duracion_iso` no parsea se descarta: sin duracion no
  se puede saber si es un Short.

### Canales con menos de 3 videos en la ventana

**Decision: el registro se conserva, pero sin `outlier_score`.** Queda
`outlier_score: null`, `outlier_confiable: false` y
`motivo_sin_outlier: "canal_con_menos_de_3_videos_en_la_ventana"`, y el
resumen de la corrida lo avisa contando los canales afectados.

Por que no se inventa: con `n = 1` la mediana del canal **es** ese mismo video,
asi que el score daria exactamente `1.0` — un numero que parece medido y no
midio nada, indistinguible de un video que de verdad rindio como su mediana.
Con `n = 2` la mediana es el promedio de los dos y el score es un espejo:
siempre uno arriba y otro abajo, sin informacion. Escribir `null` con motivo
declarado deja que M3 filtre por `outlier_confiable` en vez de promediar basura.

Se conserva la fila, en vez de descartarla, porque M2 anota **la imagen**: un
video sin score sigue aportando una miniatura valida al analisis visual.

Mismo criterio para los otros dos casos degenerados: mediana cero (canal sin
views en la ventana) y video sin `viewCount` reportado.

### Orden y recorte

Los registros se escriben ordenados por `outlier_score` descendente; los que
no tienen score van al final. Cuando la CLI pasa `--limite`, el recorte se
aplica **despues** de calcular la mediana, asi achicar el corpus no deforma el
denominador.

---

## `anotaciones.jsonl`

Un registro por video de `videos.jsonl`. Los cuatro primeros campos son de
sistema (`app/esquemas.py::CAMPOS_ANOTACION_SISTEMA`) y van primero para que el
archivo se pueda leer a ojo; despues vienen, en orden, los campos de
`ESQUEMA_ANOTACION_BASE` y al final los `campos_extra_anotacion` del perfil.

### Campos de sistema

| Campo | Tipo | Que es |
|---|---|---|
| `video_id` | str | Union con `videos.jsonl`. |
| `anotado_en` | str | ISO-8601 UTC. |
| `modelo` | str | Modelo que respondio. Vacio si la anotacion fallo. |
| `error` | str | Vacio si salio bien. Si no, el motivo. |

### Campos del modelo

Salen de `perfil.esquema_anotacion()` = `ESQUEMA_ANOTACION_BASE` +
`campos_extra_anotacion`. Este archivo no los duplica a proposito: la fuente de
verdad es `app/esquemas.py` y el `perfil.yaml`. Los enum viajan como
restriccion del JSON Schema que se le manda al proveedor, no solo como texto
del prompt, asi no vuelve un valor de fantasia que despues haya que normalizar.

**Los campos numericos son estimaciones del modelo, no mediciones.**
`rostro_area_pct`, `texto_area_pct` y `contraste_texto_fondo` los estima a ojo
un modelo de vision: sirven para ordenar y agrupar, no para auditar. El prompt
se lo dice con esas palabras.

### Registro de ejemplo

```json
{"video_id":"dQw4w9WgXcQ","anotado_en":"2026-07-31T19:58:02Z","modelo":"claude-opus-5","error":"","sujeto_principal":"persona","rostro_humano":true,"rostro_area_pct":31,"mirada":"a_camara","emocion":"determinacion","texto_presente":true,"texto_literal":"EL ULTIMO VUELO","texto_palabras":3,"texto_posicion":"izq_inf","texto_area_pct":14,"paleta_dominante":["#0B1B2B","#D9A441","#F2F2F0"],"contraste_texto_fondo":8.2,"profundidad":"dos_planos","elementos_graficos":["flecha","circulo rojo"],"densidad":"media","campo_propio_uno":"valor que pidio el perfil"}
```

### Registro fallido

Un fallo no aborta el lote: el video queda con `error` cargado, con **todas**
las columnas presentes en su valor neutro (cadena vacia, lista vacia, `0`,
`false`), y la corrida sigue con el resto. M3 lee una tabla rectangular.

```json
{"video_id":"aBcDeFgHiJk","anotado_en":"2026-07-31T19:58:11Z","modelo":"","error":"3 intentos fallidos contra Anthropic. Ultimo error: ...","sujeto_principal":"","rostro_humano":false,"rostro_area_pct":0,"mirada":"","emocion":"","texto_presente":false,"texto_literal":"","texto_palabras":0,"texto_posicion":"","texto_area_pct":0,"paleta_dominante":[],"contraste_texto_fondo":0,"profundidad":"","elementos_graficos":[],"densidad":"","campo_propio_uno":""}
```

Volver a correr `thumbforge corpus` reintenta **solo** las filas con `error`:
las que salieron bien se reutilizan tal cual. Con `--refrescar` se reanota
todo.

---

## Cacheo y cuota

Todo lo que sale a la red pasa por `app/red.py` y se cachea en `app/cache.py`.
Una segunda corrida sin `--refrescar` se resuelve entera desde `.cache/` y hace
**cero** llamadas: con `TF_SIN_RED=1` completa igual.

Detalle que lo sostiene: el borde de la ventana (`publishedAfter`) se redondea
a medianoche UTC. Si se moviera con el reloj, la clave de cache cambiaria a
cada segundo y la segunda corrida volveria a pagar cuota entera.

### Cuota de la YouTube Data API v3

La cuota por defecto de un proyecto son **10.000 unidades por dia**, y se
renueva a medianoche hora del Pacifico.

| Llamada | Costo | Cuantas |
|---|---|---|
| `search.list` | **100 unidades** | una por pagina de hasta 50 ids, por fuente |
| `videos.list` | **1 unidad** | una por lote de hasta 50 ids, sin importar cuantos |
| descarga de miniatura | 0 | no pasa por la API |

Una corrida tipica de **60 videos** con tres queries en el perfil:

```
3 search.list  (una pagina de 50 por query)   3 x 100 = 300
1 videos.list  (150 ids -> 3 lotes de 50)     3 x   1 =   3
                                              -------------
                                                      303 unidades
```

Es decir **~300 unidades**, unas 33 corridas frescas por dia. El costo lo
domina `search.list`: es 100 veces mas caro que `videos.list`, y por eso los
ids se agrupan en lotes de 50 en vez de pedir video por video (de a uno serian
60 unidades en lugar de 3, y con 500 videos la diferencia se vuelve el limite).

Con una sola fuente que devuelva 60 ids son 2 paginas de `search.list` (50 +
10) y 2 lotes de `videos.list`: **202 unidades**. Y con todo cacheado,
**0 unidades**.
