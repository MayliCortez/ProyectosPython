# Reglas: como se generan y como se leen

M3 (`app/modulos/patrones.py`) cruza el corpus de videos con sus anotaciones y
escribe `perfiles/<slug>/corpus/reglas.md`. Ese archivo lo consume M4 para
armar conceptos, y es el que hay que leer cuando una miniatura sale como sale
y no se entiende por que.

```
thumbforge reglas --perfil gdc
```

`reglas.md` se **reescribe entero** en cada corrida. No se edita a mano: lo que
se toca ahi se pierde en la corrida siguiente. Si una regla no gusta, lo que se
cambia es el corpus o el umbral, no el archivo.

---

## Lo primero, porque casi todas las herramientas del rubro mienten con esto

**El CTR ajeno no existe en ninguna API.** Ni la YouTube Data API v3 ni ninguna
otra fuente publica expone el click-through rate de un video de otro canal.
Cualquier herramienta que diga estimarte el CTR de la competencia lo esta
inventando.

Lo que M1 calcula, y sobre lo que M3 saca conclusiones del corpus ajeno, es:

```
outlier_score = views / mediana_del_canal_en_la_ventana
```

Es decir: cuanto rindio ese video **contra su propio canal**. Es una senal de
**rendimiento relativo**, y **no es CTR**. Un video puede tener un
`outlier_score` altisimo por el titulo, por el tema, por el momento en que
salio o porque el algoritmo lo empujo, sin que la miniatura haya tenido nada
que ver.

Por eso el informe del corpus ajeno **cede** ante el del CTR propio, que si es
CTR de verdad.

---

## Los dos informes, y cual manda

`reglas.md` se abre con el orden de autoridad y despues trae los dos bloques:

| | Informe A | Informe B |
|---|---|---|
| Fuente | `corpus/mi_ctr.csv` (export propio de YouTube Studio) | `corpus/videos.jsonl` + `anotaciones.jsonl` |
| Variable dependiente | CTR real | `outlier_score` |
| Identificadores | `C1`, `C2`, … | `R1`, `R2`, … |
| Autoridad | **manda** | cede ante A |

Cuando los dos informes se contradicen sobre el mismo campo, el choque queda
anotado en una seccion de conflictos en vez de resolverse en silencio. Un
conflicto no es un error del motor: suele significar que tu audiencia no se
comporta como la del corpus de referencia, que es exactamente la clase de cosa
que uno quiere enterarse.

### Como conseguir el CTR propio

Es un export manual; no hay API que lo entregue.

> YouTube Studio → Analytics → **Modo avanzado** → exportar la tabla con la
> columna «Porcentaje de clics de las impresiones (%)» → guardar como
> `perfiles/<slug>/corpus/mi_ctr.csv`.

El lector es deliberadamente tolerante, porque ese CSV cambia de forma segun
idioma y version: acepta separador `,` o `;`, decimales con coma, porcentajes
con `%`, BOM, y detecta la columna de CTR y la de id de video por contenido
cuando el nombre no coincide. Si aun asi no puede identificar una columna, dice
**cual** falta y como obtenerla, en vez de reventar con un `KeyError`.

---

## Como se lee una regla

```markdown
### R1 - Pone `mirada` en «a_camara».

- corte: `mirada` = «a_camara»
- n: grupo=20 / resto=20 / total=40
- mediana outlier_score: grupo=2.00 / resto=0.84
- efecto: +137.5% (favorece)
```

| Campo | Que dice |
|---|---|
| `R1` | Identificador estable. M4 lo cita en `reglas_aplicadas` de cada concepto, y desde ahi se vuelve a esta linea. |
| `corte` | La condicion que parte el corpus en dos. |
| `n` | Cuantos videos hay de cada lado. `grupo` cumple la condicion; `resto` son los demas que tienen ese campo anotado. |
| `mediana` | Las dos medianas comparadas. |
| `efecto` | Diferencia relativa entre ellas. |

Esa linea es la que cumple el criterio de aceptacion del proyecto: **cada regla
aplicada en M4 es rastreable hasta una linea de `reglas.md` con su n**.

---

## Las decisiones del analisis, y por que

| Parametro | Valor | Motivo |
|---|---|---|
| `N_MINIMA` | 8 por lado | Debajo de eso la mediana la mueve un solo video. El corte se marca `[muestra insuficiente]` y **no** genera regla. |
| `MAX_REGLAS` | 7 | Una lista de treinta reglas no la aplica nadie, ni un humano ni un modelo. |
| `UMBRAL_EFECTO` | 15% | Publicar una regla por una diferencia de medianas del 2% es ruido con formato de conclusion. |
| `TRAMOS` | 3 | Los campos numericos se parten en tercios por cuantiles empiricos, no por cortes fijos: un corte en «40%» no significa lo mismo en dos corpus distintos. |
| `MAX_CATEGORIAS` | 12 | Un campo con 200 valores distintos (`texto_literal`, por ejemplo) no se agrupa: cada grupo tendria n=1. |

### Medianas, nunca promedios

Un solo video viral mueve un promedio cientos por ciento y una mediana casi
nada. Todo el analisis compara medianas, y hay una prueba que lo verifica:
inyectar un outlier extremo en el corpus no cambia las reglas emitidas.

### Correlacion, no causa

Una regla dice con que aparece **asociado** el rendimiento, no que lo produzca.
`reglas.md` lo repite en su encabezado a proposito. El corpus no es un
experimento controlado: nadie publico el mismo video dos veces con dos
miniaturas distintas.

---

## Cortes descartados

Al final de cada informe hay una seccion plegable con los cortes que tenian
muestra suficiente pero no llegaron a regla, con el motivo: efecto por debajo
del umbral, campo no agrupable, u otro corte del mismo campo con mas efecto.

Sirve para dos cosas: ver que el motor efectivamente miro un campo, y detectar
que un campo esta llegando vacio desde M2 (aparece como «campo no agrupable
(sin datos)») — que es un problema de anotacion, no de analisis.

---

## Cuando `reglas.md` no existe

M4 funciona igual: genera conceptos sin reglas y lo dice en su resultado. Las
reglas son una mejora, no un requisito. Un canal nuevo, sin corpus todavia,
puede producir miniaturas desde el primer dia.
