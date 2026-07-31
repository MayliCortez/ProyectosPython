# Empaquetado

Notas de lo que se decidio en `Dockerfile` y `compose.yaml`, y por que. Es el
paso 2 del orden de construccion.

La regla de la que sale todo lo demas: **la imagen contiene solo codigo**.
`perfiles/`, `data/`, `salida/` y `.cache/` son volumenes bind. Borrar la
imagen, reconstruirla o actualizar la app no toca ni un perfil ni una
miniatura.

---

## La base, pinneada por digest

```
python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de
```

Un tag muta. `python:3.12-slim` de hoy no es el de dentro de tres meses, y el
dia que cambie la version de Debian debajo, un build que funcionaba deja de
funcionar sin que nadie haya tocado el repositorio. Un digest no muta: es el
hash del contenido.

El digest pinneado es el del **indice** (la lista multi-arquitectura), no el de
una plataforma. Eso es lo que preserva el multi-arch: Docker resuelve del
indice el manifiesto de la plataforma en la que esta construyendo.

Resuelto el 2026-07-31 contra Docker Hub. El indice cubre 8 plataformas; las
dos que nos importan:

| Plataforma | Digest del manifiesto |
|---|---|
| `linux/amd64` | `sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464` |
| `linux/arm64` | `sha256:55842c72c6b3584d06ec84c731fc516b30b8a53ad262ebd085e47ab568b3bfc1` |

Ambos son Python 3.12.13, imagen creada el 2026-07-14.

Para saber si el pin quedo viejo:

```bash
scripts/verificar_imagen.sh --solo-digest
```

Resuelve el digest actual del tag y lo compara. Si difiere no es un error: es
exactamente lo que el pin evita. Actualizarlo es una decision deliberada, se
cambia el `ARG BASE_IMAGEN` del Dockerfile y se vuelve a verificar.

---

## Dockerfile

### Dos etapas

`builder` arma un virtualenv en `/opt/venv`; la etapa final copia ese venv y
nada mas. En la imagen final no queda ni pip cache, ni fuentes de build, ni
compiladores.

### No se instala build-essential, ni siquiera en el builder

Las cuatro dependencias publican wheels `manylinux` para cp312 en x86_64 y en
aarch64 (verificado contra PyPI, ver la cuenta de tamano mas abajo). No hay
nada que compilar. Si algun dia el build falla intentando compilar, es que a
una dependencia le falta el wheel para esa plataforma — eso hay que mirarlo, no
taparlo agregando gcc, porque agregar gcc mete ~200 MB y una cadena de
herramientas en una imagen que se supone que solo corre Python.

Corolario: Pillow no necesita `libjpeg-dev`, `zlib1g-dev` ni `libfreetype-dev`
en el sistema. El wheel de manylinux ya trae esas bibliotecas adentro.
`thumbforge doctor` lo confirma en tiempo de ejecucion: chequea que
`PIL.features` reporte `jpg`, `zlib` y `freetype2`.

### El codigo vive dentro del venv

La etapa final copia **solo** `/opt/venv`, que ya contiene el paquete
`thumbforge` instalado y su comando en `/opt/venv/bin/thumbforge`. No se copia
una segunda vez el arbol `app/` a `/app`.

Es una desviacion consciente del enunciado ("copia el virtualenv y el codigo"):
tener el codigo en dos lugares —`/app/app` y el site-packages del venv— crea la
duda de cual se ejecuta, y la respuesta cambia segun se invoque `thumbforge`
(usa el del venv) o `python -m app.cli` desde `/app` (usaria el de `/app`).
Editar el equivocado dentro del contenedor y no ver ningun efecto es una tarde
perdida. Con una sola copia no hay ambiguedad, y `python -m app.cli` sigue
funcionando porque el paquete esta instalado.

`/app` queda entonces conteniendo unicamente los cuatro puntos de montaje.

### Consecuencia sobre `app/rutas.py`

`rutas.RAIZ_APP` se calcula desde `__file__`, asi que dentro del contenedor
apunta al site-packages del venv, no a `/app`. Por eso el Dockerfile **define
las cuatro variables de entorno de forma explicita** y no confia en los valores
por defecto de `rutas._DEFECTO`:

```
TF_PERFILES_DIR=/app/perfiles
TF_DATA_DIR=/app/data
TF_SALIDA_DIR=/app/salida
TF_CACHE_DIR=/app/.cache
TF_EN_CONTENEDOR=1
```

Los nombres salen de `rutas._ENV`, y los cuatro destinos coinciden uno a uno
con los `target` de los binds de `compose.yaml`. `TF_EN_CONTENEDOR=1` es lo que
lee `doctor._chequear_entorno` para reportar el contexto y el uid efectivo.

`XDG_CACHE_HOME` tambien apunta a `/app/.cache`: si alguna biblioteca decide
cachear algo, cae en el volumen y no engorda la capa de escritura del
contenedor.

### pip se borra del venv

Despues de instalar, el builder hace `pip uninstall -y pip` dentro de
`/opt/venv`. Dos motivos:

1. Son ~20 MB duplicados: la imagen base ya trae su propio pip en
   `/usr/local/lib/python3.12/site-packages`.
2. Un `pip install` hecho a mano dentro de un contenedor en marcha se pierde al
   recrearlo, y mientras tanto hace que esa maquina no se parezca a ninguna
   otra. Si falta una dependencia, va a `pyproject.toml`.

### Usuario

La imagen crea `forge` (uid 1000, gid 1000) y termina con `USER 1000:1000`, asi
que un `docker run` pelado ya es no-root. `compose.yaml` lo pisa con el UID/GID
del host (ver mas abajo).

Como el uid efectivo puede ser cualquiera, `HOME=/tmp`: es el unico directorio
garantizado escribible por cualquier uid. Nada de la app guarda estado en
`HOME`, pero si Python o alguna biblioteca intenta escribir ahi, no explota.

Los cuatro directorios de `/app` quedan en 0777. Es aceptable porque son
**puntos de montaje**: en uso real el bind del host los tapa y mandan los
permisos del host. El 0777 solo evita que un `docker run` sin binds y con un
uid arbitrario se trabe escribiendo.

### Sin ENTRYPOINT

El uso normal es `docker compose run --rm app thumbforge <comando>`. Con
`ENTRYPOINT ["thumbforge"]` esa linea quedaria como `thumbforge thumbforge
doctor`. Se deja `CMD ["thumbforge", "doctor"]`, que es lo que corre un
`docker compose up app` pelado, y cualquier otro comando se pasa entero.

### HEALTHCHECK

Esta declarado en el Dockerfile *y* en `compose.yaml`. En el Dockerfile para
que sirva tambien a quien use `docker run` sin compose; en compose porque es
donde se lo espera al leer la orquestacion.

`thumbforge doctor --quiet` no toca la red (`cmd_doctor` calcula
`con_red = not (sin_red or quiet)`) y sale 1 solo ante errores que impiden
trabajar. Ojo con esto: **un contenedor sin `perfiles/` montado sale
unhealthy**, porque `doctor` marca ERROR cuando no encuentra ningun
`perfil.yaml`. Es correcto: sin perfiles el motor no puede hacer nada. Faltar
claves de API es AVISO, no ERROR, asi que un `.env` a medio llenar no tumba el
healthcheck.

---

## compose.yaml

### Binds, no volumenes nombrados

```yaml
- ./perfiles:/app/perfiles
- ./data:/app/data
- ./salida:/app/salida
- ./.cache:/app/.cache
```

Un volumen nombrado vive dentro del area de Docker y para mirarlo hay que
entrar con un contenedor. Estas cuatro carpetas se editan a mano (perfiles,
YAML, fuentes), se revisan a ojo (miniaturas) y se respaldan copiandolas. Tienen
que ser carpetas normales del disco, visibles desde el explorador de archivos.

Los cuatro van en lectura-escritura, incluido `perfiles/`: M1 escribe el corpus
en `perfiles/<slug>/corpus/`.

### `user: "${UID:-1000}:${GID:-1000}"`

Sin esto, en Linux, cada miniatura que aparece en `./salida` es propiedad de
root y hace falta `sudo` hasta para borrarla. Compose interpola `UID` y `GID`
desde el `.env` del proyecto (en bash, `UID` no se exporta al entorno, asi que
la unica via confiable es el archivo). Por eso `.env.example` los incluye y por
eso la receta:

```bash
echo "UID=$(id -u)" >> .env && echo "GID=$(id -g)" >> .env
```

En macOS con Docker Desktop y en Windows con WSL2 el mapeo de propietario lo
maneja la capa de virtualizacion y esto es inocuo; en Linux es la diferencia
entre usable e insoportable.

### Secretos

`env_file: .env`, y nada mas. Las claves nunca entran al Dockerfile (quedarian
en la imagen y en el historial de capas, donde `docker history` las muestra) ni
escritas en `compose.yaml`, que si se versiona. Se versiona `.env.example`,
jamas `.env` — `.gitignore` y `.dockerignore` lo excluyen.

`scripts/verificar_imagen.sh` comprueba que no haya un `.env` dentro de la
imagen ni claves en su `Config.Env`.

### Anclaje YAML compartido

`x-thumbforge-comun` concentra build, env_file, user, volumenes y healthcheck;
`app` y `web` lo mezclan con `<<:`. Un solo lugar donde cambiar el mapeo de
volumenes cuando aparezca un quinto.

### El servicio `web` todavia no existe

Llega en el **paso 8**. Queda declarado bajo `profiles: [web]` para que no
arranque con un `docker compose up` normal, y para fijar ahora el contrato:

- El paso 8 debe entregar **`app/web.py` con un objeto ASGI llamado `app`**.
  El comando declarado es `uvicorn app.web:app --host 0.0.0.0 --port 8000`.
- `uvicorn`, `fastapi` y `python-multipart` son el extra `[web]` de
  `pyproject.toml`. No entran a la imagen de la CLI: el servicio `web` se
  construye con `build.args: TF_EXTRAS: "[web]"` y produce una imagen aparte,
  `thumbforge:0.1.0-web`. La CLI se queda chica.
- El puerto se publica en **`127.0.0.1:8000:8000`**, no en `8000:8000`. La
  interfaz no tiene autenticacion y el contenedor tiene las claves de API en el
  entorno; exponerla a la LAN tiene que ser una decision explicita, no el valor
  por defecto.
- El healthcheck del servicio `web` es el mismo `doctor --quiet`: verifica que
  la instalacion este sana, **no** que el puerto HTTP responda. Cuando el paso 8
  tenga un endpoint de salud, conviene cambiarlo por una consulta a ese
  endpoint.

Hasta el paso 8, `docker compose --profile web up web` construye bien y falla al
arrancar con `ModuleNotFoundError: app.web`. Es lo esperado.

---

## Cuenta de tamano

Objetivo: por debajo de 600 MB. Numeros reales, no estimados a ojo.

**Base**, midiendo el `ISIZE` de cada capa gzip del manifiesto de Docker Hub
(tamano descomprimido, que es lo que reporta `docker image inspect`):

| Capa | amd64 comprimida | amd64 en disco | arm64 comprimida | arm64 en disco |
|---|---|---|---|---|
| debian slim | 29.8 MB | 81.0 MB | 30.1 MB | 103.0 MB |
| deps de runtime | 1.3 MB | 4.1 MB | 1.3 MB | 4.2 MB |
| CPython 3.12.13 | 12.1 MB | 38.1 MB | 12.0 MB | 41.4 MB |
| entrypoint | ~0 | ~0 | ~0 | ~0 |
| **total base** | **43.2 MB** | **123.3 MB** | **43.5 MB** | **148.5 MB** |

**Dependencias**, tamano del wheel y tamano instalado (suma de los tamanos
descomprimidos de las entradas del zip), consultado en pypi.org:

| Paquete | Version | whl amd64 | instalado amd64 | whl arm64 | instalado arm64 |
|---|---|---|---|---|---|
| Pillow | 12.3.0 | 6.94 MB | 19.67 MB | 6.27 MB | 22.95 MB |
| PyYAML | 6.0.3 | 0.81 MB | 2.90 MB | 0.78 MB | 2.92 MB |
| httpx | 0.28.1 | 0.07 MB | 0.30 MB | igual | 0.30 MB |
| python-dotenv | 1.2.2 | 0.02 MB | 0.06 MB | igual | 0.06 MB |
| anyio (via httpx) | 4.14.2 | 0.13 MB | 0.51 MB | igual | 0.51 MB |
| certifi (via httpx) | 2026.7.22 | 0.14 MB | 0.25 MB | igual | 0.25 MB |
| idna (via httpx) | 3.18 | 0.07 MB | 0.33 MB | igual | 0.33 MB |
| httpcore (via httpx) | 1.0.9 | 0.08 MB | 0.29 MB | igual | 0.29 MB |
| h11 (via httpcore) | 0.16.0 | 0.04 MB | 0.10 MB | igual | 0.10 MB |
| sniffio (via anyio) | 1.3.1 | 0.01 MB | 0.02 MB | igual | 0.02 MB |
| typing_extensions | 4.16.0 | 0.05 MB | 0.18 MB | igual | 0.18 MB |
| **total** | | **8.3 MB** | **24.6 MB** | **7.6 MB** | **27.9 MB** |

**Suma final estimada:**

```
amd64:  123.3 (base) + 24.6 (deps) + ~6 (.pyc que compila pip) + ~0.3 (paquete thumbforge)
     = ~154 MB
arm64:  148.5 (base) + 27.9 (deps) + ~6 (.pyc) + ~0.3
     = ~183 MB
```

Comprimido (lo que se transfiere en un push/pull): ~43 MB de base + ~10 MB de la
capa del venv, del orden de 55 MB.

Margen sobre el objetivo de 600 MB: mas de 3x. Si alguna vez `docker image
inspect` devuelve 400 MB o mas, algo se colo — casi seguro un compilador o una
dependencia con binarios (torch, numpy con MKL, opencv). El script de
verificacion avisa a los 600 MB y falla a 1 GB.

Aclaracion sobre los `.pyc`: los ~6 MB son estimados (bytecode del ~5 MB de
codigo Python puro que hay entre las dependencias). `PYTHONDONTWRITEBYTECODE=1`
se define en la **etapa final**, para que nadie escriba `.pyc` en tiempo de
ejecucion, y deliberadamente **no** en el builder, para que pip deje el bytecode
precompilado dentro del venv: sin el, cada invocacion de la CLI recompilaria. El
numero exacto lo da `docker image inspect` en la maquina con Docker.

---

## Verificacion

### Lo que se verifico sin demonio de Docker

La maquina donde se escribio esto no tiene demonio de Docker
(`/var/run/docker.sock` no existe), asi que **la imagen no se construyo**. Si se
verifico:

- El digest del indice de `python:3.12-slim` contra el registry, y que el indice
  incluye `linux/amd64` y `linux/arm64`.
- Los tamanos de capa de la base por plataforma, leyendo el `ISIZE` de cada blob
  gzip con peticiones `Range`.
- Los tamanos de wheel e instalado de las 4 dependencias y sus 7 transitivas,
  contra pypi.org, y que existe wheel manylinux cp312 para x86_64 y aarch64 de
  las dos que tienen binarios (Pillow, PyYAML).
- `docker compose config` parsea el archivo sin demonio: se corrio sobre una
  copia del proyecto y resuelve bien los dos servicios, el perfil `web`, los
  cuatro binds (`type: bind`) y la interpolacion de `UID`/`GID`.
- Que los cuatro `target` de los binds coinciden exactamente con los valores de
  `TF_*_DIR` del Dockerfile, y que esos nombres de variable son los que declara
  `app/rutas.py` (`rutas._ENV`). Se importo `rutas` con esas variables puestas y
  las cuatro rutas resuelven a los puntos de montaje.
- Que los cuatro directorios origen (`./perfiles`, `./data`, `./salida`,
  `./.cache`) existen en el repositorio.
- Que `.dockerignore` excluye del contexto los cuatro volumenes, `.env`, `.git`,
  `pruebas/` y `ejemplos/`, y deja entrar `pyproject.toml` y `app/`.
- Sintaxis de `scripts/verificar_imagen.sh` con `bash -n`.

### Lo que NO se pudo verificar aca

Todo lo que requiere construir y correr la imagen:

- Que el build termine y en cuanto tiempo.
- El tamano real de la imagen (`docker image inspect`).
- Que `thumbforge doctor` corra adentro y salga 0.
- Que el uid dentro del contenedor no sea root y coincida con el del host.
- Que un archivo creado en `/app/salida` aparezca en `./salida` con el uid del
  host.
- Que el build cruce a `linux/arm64` con buildx.

Para eso esta `scripts/verificar_imagen.sh`, que cubre exactamente esa lista.

### En una maquina con Docker

```bash
cd thumbforge
cp .env.example .env
echo "UID=$(id -u)" >> .env && echo "GID=$(id -g)" >> .env

scripts/verificar_imagen.sh          # todo, incluido el multi-arch
scripts/verificar_imagen.sh --sin-multiarch
scripts/verificar_imagen.sh --solo-digest
```

O a mano:

```bash
docker compose build app
docker image inspect -f '{{.Size}}' thumbforge:0.1.0
docker compose run --rm app thumbforge doctor --sin-red
docker compose run --rm app id -u                    # no debe ser 0

docker buildx create --name tf-multi --driver docker-container
docker buildx build --builder tf-multi \
  --platform linux/amd64,linux/arm64 --output type=cacheonly .
```

El build multi-arquitectura necesita un builder con driver `docker-container`:
el driver `docker` por defecto no cruza plataformas. El script crea uno temporal
y lo borra al salir, sin tocar el builder por defecto del usuario.
