# Instalar y correr thumbforge

Este documento asume que sos otra persona -no yo- y que agarraste este
proyecto por primera vez. No hace falta que sepas Python. Si no sabes Docker,
la seccion **A** es la mas corta.

Tres formas de tenerlo andando, en orden de simple a inusual. Elegi UNA:

- **A. Repo + Docker Compose.** Necesita `git`, `docker` y `docker compose`. Es
  lo que quiero que uses.
- **B. Imagen desde GitHub Container Registry.** No hay que clonar nada, se baja
  la imagen ya armada. Aparece cuando publiquemos las primeras releases.
- **C. Tarball offline.** No necesita internet ni cuenta en ningun lado. Es
  para el caso raro de una maquina sin conexion o con un firewall duro.

Elegi UNA. No mezcles.

---

## A. Repo + Docker Compose (recomendada)

### 1. Clonar

```sh
git clone https://github.com/MayliCortez/ProyectosPython.git
cd ProyectosPython/thumbforge
```

### 2. Preparar el .env

Se copia el ejemplo y se completan las claves que se van a usar. **Ninguna
es obligatoria para probar**: sin claves solo faltan los modulos que las
necesitan.

```sh
cp .env.example .env
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
```

`UID` y `GID` son para que los archivos que caen en `./salida` te queden a
vos, no a root. En Windows este paso no aplica y las lineas se pueden
saltar.

Editas `.env` con lo que tengas. Sin `YOUTUBE_API_KEY` no corre `corpus`, sin
`ANTHROPIC_API_KEY` u `OPENAI_API_KEY` no corre M4 con guion, pero
`run --conceptos` (brief hecho a mano) anda con las dos vacias.

### 3. Chequeo previo

```sh
docker compose run --rm app thumbforge doctor
```

Si sale con codigo 0 y la seccion **Perfiles** dice OK para los cuatro, esta
lista. Cualquier ERROR trae el motivo concreto y como arreglarlo.

### 4. Primera miniatura

Los ejemplos viven en `ejemplos/` en el repo pero **no entran a la imagen**:
la imagen contiene solo codigo. Se copian a un volumen para que el contenedor
los vea:

```sh
cp ejemplos/conceptos_true_crime.json data/
docker compose run --rm app thumbforge run \
  --perfil true_crime \
  --conceptos data/conceptos_true_crime.json
```

Deja en `./salida`: los JPG, `<slug>_brief.json`, `qa.md` y `creditos.txt`.
Miralos con tu explorador de archivos: son tuyos, no de root.

### 5. Con imagen propia

Si tenes una foto tuya, va al volumen tambien:

```sh
cp /donde/este/tu-foto.jpg data/
docker compose run --rm app thumbforge run \
  --perfil gdc \
  --conceptos data/mi-brief.json \
  --imagen data/tu-foto.jpg
```

### 6. Bajar y anotar corpus de referencia

Necesita `YOUTUBE_API_KEY` en `.env`.

```sh
docker compose run --rm app thumbforge corpus --perfil gdc --limite 60
docker compose run --rm app thumbforge reglas --perfil gdc
```

El corpus queda en `perfiles/gdc/corpus/`. Segunda corrida del mismo perfil:
cero llamadas de red.

### 7. Interfaz web (opcional, todavia en camino)

Cuando este disponible se levanta con:

```sh
docker compose --profile web up
```

Y se abre `http://localhost:8000`. Se publica solo en `127.0.0.1` a proposito:
la interfaz no tiene autenticacion y el contenedor tiene tus claves. Exponerla
a la LAN tiene que ser una decision tuya, no algo que el compose haga por
defecto.

---

## B. Imagen desde GHCR (cuando este publicada)

Cuando saquemos la primera release, la imagen va a estar en `ghcr.io/maylicortez/thumbforge`.
Mientras tanto usa la seccion A: la ganancia de esta via es no clonar el repo,
que en este proyecto ademas pesa poco.

```sh
mkdir thumbforge-uso && cd thumbforge-uso
curl -O https://raw.githubusercontent.com/MayliCortez/ProyectosPython/main/thumbforge/compose.yaml
curl -O https://raw.githubusercontent.com/MayliCortez/ProyectosPython/main/thumbforge/.env.example
cp .env.example .env
echo "UID=$(id -u)" >> .env && echo "GID=$(id -g)" >> .env

# Ajusta compose.yaml: reemplaza 'build: .' por 'image: ghcr.io/maylicortez/thumbforge:0.1.0'.
docker compose pull
docker compose run --rm app thumbforge doctor
```

Los perfiles de ejemplo NO vienen en la imagen. Se descargan aparte:

```sh
mkdir -p perfiles
# Aca curl a cada carpeta de perfil, o clonar el repo solo para eso.
```

Si vas a bajar los perfiles del repo igual, la seccion **A** te sale mas corta.

---

## C. Tarball offline

Sirve cuando la maquina destino no tiene internet, o cuando queres mover la
imagen sin depender de un registry. Necesita `docker` en las dos maquinas.

### En la maquina con internet

```sh
cd thumbforge
docker compose build app
docker save thumbforge:0.1.0 | gzip > thumbforge-0.1.0.tar.gz
```

Se copia `thumbforge-0.1.0.tar.gz`, `compose.yaml`, `.env.example` y las
carpetas `perfiles/` y `ejemplos/` a la maquina destino.

### En la maquina destino

```sh
gunzip -c thumbforge-0.1.0.tar.gz | docker load
cp .env.example .env
echo "UID=$(id -u)" >> .env && echo "GID=$(id -g)" >> .env
docker compose run --rm app thumbforge doctor
```

**Editar `compose.yaml`** antes de correr para que use la imagen cargada en
vez de intentar construirla:

```yaml
# reemplazar:  build: .
# por:         image: thumbforge:0.1.0
```

---

## Los cuatro volumenes

El compose monta cuatro carpetas del host adentro del contenedor. Todo lo que
importa vive ahi: la imagen contiene solo codigo, y actualizar la app **no
borra tu trabajo**.

| Host | Dentro | Que va |
|---|---|---|
| `./perfiles/` | `/app/perfiles` | Un directorio por canal (perfil.yaml, skin.yaml, fonts, corpus) |
| `./data/` | `/app/data` | Los archivos de entrada que le pases al contenedor (imagenes, briefs) |
| `./salida/` | `/app/salida` | Lo que produce cada corrida: JPG, qa.md, creditos.txt, brief.json |
| `./.cache/` | `/app/.cache` | Cache interna. Borrala cuando quieras: solo se paga otra vez lo que costo traerlo. |

---

## Agregar un canal propio

Copia la carpeta de un perfil parecido y editala. No hay que tocar Python:

```sh
cp -r perfiles/tech_reviews perfiles/mi_canal
# Editar perfiles/mi_canal/perfil.yaml y skin.yaml
docker compose run --rm app thumbforge doctor --perfil mi_canal
```

`doctor` dice **exactamente** que falta si algo no cierra: una tipografia que
no carga, un lienzo por debajo del minimo, una lista de licencias vacia.

---

## Cuando algo falla

| Sintoma | Que mirar |
|---|---|
| `docker compose run` dice `permission denied` sobre `./salida` | Falta `UID=...` y `GID=...` en `.env`, o los pusiste despues de crear la carpeta con root. `sudo chown -R $USER ./salida ./data ./.cache`. |
| `doctor` marca ERROR en Perfiles | Lee el detalle. Suele ser una tipografia mal referenciada o el `lienzo` por debajo de 1280x720. |
| Miniaturas no se ven bien pero corre sin errores | Abri `salida/qa.md`. Cada rechazo dice contra que umbral fallo y de que perfil sale ese umbral. |
| `corpus` pide `YOUTUBE_API_KEY` | Es correcto: sin clave no hay corpus. Sacala en Google Cloud Console, YouTube Data API v3, sin costo hasta el limite gratuito. |
| Todo sale con permisos de root | El `.env` no tenia `UID`/`GID` en el momento del primer `docker compose up`. Fija los permisos con el `chown` de arriba. |

---

## Actualizar

```sh
git pull
docker compose build app
```

Ni `perfiles/`, ni `data/`, ni `salida/`, ni `.cache/` se tocan: son
volumenes, sobreviven al build. Si un perfil rompe con la version nueva,
`doctor` te lo dice antes de la primera corrida.
