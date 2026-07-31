# thumbforge

Motor de miniaturas multi-nicho.

## Principio rector

**El motor no sabe nada del nicho.** No hay una sola regla de aviacion, de
true crime ni de tecnologia dentro del codigo. Todo lo especifico de un canal
vive en una carpeta de perfil. Agregar un canal nuevo es crear una carpeta, no
tocar Python.

Si aparece un `if nicho == "..."` en `app/`, el diseno esta mal: eso va al YAML.
La prueba `pruebas/test_politicas.py::test_ningun_nicho_esta_cableado_en_el_motor`
recorre `app/` buscando nombres de nicho y falla si encuentra alguno.

## Estado

Construido: **paso 1** del orden de construccion — esqueleto, sistema de
perfiles y `thumbforge doctor`. Los modulos M1..M6 llegan en los pasos
siguientes; `run`, `corpus` y `reglas` responden indicando en que paso llegan.

## Estructura

```
thumbforge/
├── pyproject.toml          # dependencias pinneadas a version exacta
├── .env.example            # se versiona esto; .env jamas
├── app/
│   ├── cli.py              # run | corpus | reglas | doctor | perfiles | politica
│   ├── perfiles.py         # carga y validacion de perfiles
│   ├── politicas.py        # motor de politicas (no conoce ningun nicho)
│   ├── proveedores.py      # registro de APIs externas
│   ├── esquemas.py         # esquema base de anotacion y de concepto
│   ├── doctor.py           # diagnostico de instalacion
│   ├── rutas.py            # resolucion de los cuatro volumenes
│   └── modulos/            # M1..M6
├── perfiles/               # → volumen
├── data/                   # → volumen
├── salida/                 # → volumen
├── .cache/                 # → volumen
├── ejemplos/               # conceptos JSON para probar politicas sin red
└── pruebas/
```

## Perfiles incluidos

Tres perfiles de prueba con politicas deliberadamente opuestas. Si el motor los
soporta sin ramas condicionales, la abstraccion funciona.

| Perfil | Alias | Base visual | Personas reales | Copy |
|---|---|---|---|---|
| `aviacion_historica` | `gdc` | archivo real primero, IA solo fondos | si, solo licencia verificada | 4 palabras, sobrio, nombre reconocible obligatorio |
| `true_crime` | `tc` | solo archivo licenciado, IA prohibida | si, restriccion maxima | 3 palabras, sin sensacionalismo, sin nombres de victimas |
| `tech_reviews` | `tech` | generacion libre, producto de foto de prensa | no aplica | 5 palabras, comparativo, numero permitido |

Cada perfil es una carpeta:

```
perfiles/<slug>/
  perfil.yaml     # politica de contenido
  skin.yaml       # identidad visual
  fonts/          # tipografias embebidas (archivos, no nombres de familia)
  assets/         # logo, marcos, texturas
  corpus/         # videos.jsonl, anotaciones.jsonl, reglas.md, mi_ctr.csv
```

### Las fuentes van por ruta de archivo

`skin.yaml` dice `archivo: "fonts/DejaVuSans-Bold.ttf"`, nunca
`familia: "Arial Bold"`. Una fuente instalada en Windows no existe en
`python:3.12-slim`, y Pillow **no avisa**: cae en silencio a la fuente por
defecto y arruina el render. `doctor` verifica que cada tipografia exista y que
Pillow pueda abrirla.

## Uso

```bash
thumbforge doctor                       # diagnostico completo, con llamadas de prueba
thumbforge doctor --sin-red             # sin tocar la red
thumbforge doctor --quiet               # solo codigo de salida (lo usa el healthcheck)
thumbforge perfiles --detalle           # perfiles disponibles y su politica completa
thumbforge politica --perfil tc --concepto ejemplos/conceptos_true_crime.json
```

Sin instalar el paquete: `python -m app.cli ...` desde este directorio.

### El bloqueo de `true_crime`

Generar con IA el rostro de una persona real —victima o perpetrador— es un
problema legal (derecho de imagen, difamacion), de politica de plataforma y
etico. El perfil lo bloquea **en el motor**, no en la memoria del operador:

```
$ thumbforge politica --perfil tc --concepto ejemplos/conceptos_true_crime.json

tc-2-rostro-generado: RECHAZADO
  - [ia_sobre_persona_real] base_visual propone generar con IA a una persona
    real ('perpetrador'). El perfil lo bloquea sin excepcion.
    (regla: personas_reales.generar_con_ia)
```

El mismo JSON, evaluado con `--perfil gdc`, recibe otro veredicto: la diferencia
esta enteramente en el YAML.

## Sobre el CTR

**El CTR ajeno no existe en ninguna API.** Ni la YouTube Data API v3 ni ninguna
otra fuente publica expone el click-through rate de un video de otro canal.
Cualquier herramienta que diga estimarlo, lo esta inventando.

Lo que M1 calcula es `outlier_score = views / mediana_del_canal_en_la_ventana`:
cuanto rindio un video **contra el propio canal**. Es una senal de rendimiento
relativo, y **no es CTR**.

El unico CTR real disponible es el propio, exportado a mano desde el Modo
Avanzado de YouTube Studio a `perfiles/<slug>/corpus/mi_ctr.csv`. Cuando ese
archivo existe, M3 corre el analisis con CTR como variable dependiente e informa
aparte, y **esas conclusiones pesan mas** que las del corpus ajeno.

## Configuracion

```bash
cp .env.example .env    # y completar las claves
```

`.env` no se versiona ni entra a la imagen. `thumbforge doctor` verifica que
cada clave este presente, que tenga formato plausible y que el proveedor
responda a una llamada de prueba que no consume tokens.

## Desarrollo

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```
