#!/usr/bin/env bash
#
# Verificacion de punta a punta del empaquetado de thumbforge.
#
# Este script corre en una maquina CON demonio de Docker. Comprueba lo que no
# se puede comprobar leyendo archivos: que la imagen construya, cuanto pesa de
# verdad, que adentro no haya compiladores ni root, que doctor pase, que lo
# que sale a ./salida quede propiedad del usuario del host, y que el build
# multi-arquitectura funcione.
#
#   scripts/verificar_imagen.sh                 # todo
#   scripts/verificar_imagen.sh --sin-multiarch # sin la parte lenta de buildx
#   scripts/verificar_imagen.sh --solo-digest   # solo comparar el digest base
#
# Salida 0 = todo bien. Salida 1 = al menos una prueba fallo.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

IMAGEN="thumbforge:0.1.0"
TAG_BASE="python:3.12-slim"
LIMITE_AVISO_MB=600
LIMITE_ERROR_MB=1024
BUILDER="thumbforge-verificacion"

SIN_MULTIARCH=0
SOLO_DIGEST=0
for arg in "$@"; do
  case "$arg" in
    --sin-multiarch) SIN_MULTIARCH=1 ;;
    --solo-digest)   SOLO_DIGEST=1 ;;
    -h|--help)       sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "opcion desconocida: $arg" >&2; exit 2 ;;
  esac
done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_OK=$'\033[32m'; C_MAL=$'\033[31m'; C_AVISO=$'\033[33m'; C_TIT=$'\033[1m'; C_FIN=$'\033[0m'
else
  C_OK=""; C_MAL=""; C_AVISO=""; C_TIT=""; C_FIN=""
fi

N=0
FALLOS=0
AVISOS=0

prueba() { N=$((N + 1)); printf '\n%sPRUEBA %d: %s%s\n' "$C_TIT" "$N" "$1" "$C_FIN"; }
ok()     { printf '  %sOK%s    %s\n' "$C_OK" "$C_FIN" "$1"; }
aviso()  { AVISOS=$((AVISOS + 1)); printf '  %sAVISO%s %s\n' "$C_AVISO" "$C_FIN" "$1"; }
mal()    { FALLOS=$((FALLOS + 1)); printf '  %sFALLA%s %s\n' "$C_MAL" "$C_FIN" "$1"; }
info()   { printf '        %s\n' "$1"; }

limpiar() {
  rm -f "$RAIZ/salida/.prueba_uid" 2>/dev/null || true
  docker buildx rm "$BUILDER" >/dev/null 2>&1 || true
}
trap limpiar EXIT

# uid del archivo, portable entre GNU coreutils y BSD/macOS
uid_de() {
  stat -c %u "$1" 2>/dev/null || stat -f %u "$1"
}

# ---------------------------------------------------------------------------
prueba "el digest de la base sigue siendo el pinneado en el Dockerfile"
PINNEADO="$(grep -oE 'ARG BASE_IMAGEN=.*@sha256:[0-9a-f]{64}' Dockerfile | grep -oE 'sha256:[0-9a-f]{64}' || true)"
if [ -z "$PINNEADO" ]; then
  mal "el Dockerfile no pinnea la base por digest (busco 'ARG BASE_IMAGEN=...@sha256:...')"
else
  ok "Dockerfile pinnea $PINNEADO"
  TOKEN="$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull" \
           | sed -E 's/.*"token":"([^"]+)".*/\1/')" || TOKEN=""
  if [ -z "$TOKEN" ]; then
    aviso "sin red: no se pudo consultar el registry para comparar el digest"
  else
    ACTUAL="$(curl -fsS -o /dev/null -D - \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
        "https://registry-1.docker.io/v2/library/python/manifests/3.12-slim" \
        | tr -d '\r' | awk 'tolower($1)=="docker-content-digest:"{print $2}')" || ACTUAL=""
    info "digest actual del tag $TAG_BASE: ${ACTUAL:-desconocido}"
    if [ "$ACTUAL" = "$PINNEADO" ]; then
      ok "el pin esta al dia"
    else
      aviso "el tag $TAG_BASE se movio. No es un error: el pin es justamente para que no se mueva solo."
      info "Para actualizar a conciencia, reemplaza el digest del Dockerfile por: $ACTUAL"
    fi
  fi
fi
if [ "$SOLO_DIGEST" -eq 1 ]; then
  printf '\nfallas=%d avisos=%d\n' "$FALLOS" "$AVISOS"
  exit $((FALLOS > 0))
fi

# ---------------------------------------------------------------------------
prueba "hay demonio de Docker y un .env con UID/GID"
if ! docker info >/dev/null 2>&1; then
  mal "no hay demonio de Docker accesible. Sin el no se puede verificar nada mas."
  exit 1
fi
ok "demonio de Docker accesible"

if [ ! -f .env ]; then
  mal ".env no existe. Corre:  cp .env.example .env"
  exit 1
fi
ok ".env presente (no se versiona; sus valores no entran a la imagen)"

UID_HOST="$(id -u)"
GID_HOST="$(id -g)"
if ! grep -qE "^UID=$UID_HOST$" .env || ! grep -qE "^GID=$GID_HOST$" .env; then
  aviso "UID/GID en .env no coinciden con los tuyos ($UID_HOST:$GID_HOST). Corregilo con:"
  info "sed -i.bak '/^UID=/d;/^GID=/d' .env && echo \"UID=\$(id -u)\" >> .env && echo \"GID=\$(id -g)\" >> .env"
fi

# ---------------------------------------------------------------------------
prueba "la imagen construye"
if docker compose build app; then
  ok "build completo"
else
  mal "el build fallo"
  exit 1
fi

# ---------------------------------------------------------------------------
prueba "tamano de la imagen (objetivo < ${LIMITE_AVISO_MB} MB, techo ${LIMITE_ERROR_MB} MB)"
BYTES="$(docker image inspect -f '{{.Size}}' "$IMAGEN")"
MB=$((BYTES / 1000 / 1000))
info "docker image inspect: $MB MB ($BYTES bytes, sin comprimir)"
if [ "$MB" -ge "$LIMITE_ERROR_MB" ]; then
  mal "$MB MB: se colo algo grande. Revisa las capas con: docker history $IMAGEN"
elif [ "$MB" -ge "$LIMITE_AVISO_MB" ]; then
  aviso "$MB MB: pasa el objetivo de $LIMITE_AVISO_MB MB"
else
  ok "$MB MB"
fi

# ---------------------------------------------------------------------------
prueba "la imagen no trae compiladores ni cadena de build"
SOBRAS=""
for bin in gcc cc g++ make ld cmake; do
  if docker run --rm "$IMAGEN" sh -c "command -v $bin" >/dev/null 2>&1; then
    SOBRAS="$SOBRAS $bin"
  fi
done
if [ -n "$SOBRAS" ]; then
  mal "la imagen final tiene:$SOBRAS (deberian quedar solo en la etapa builder)"
else
  ok "sin gcc/cc/g++/make/ld/cmake"
fi

# ---------------------------------------------------------------------------
prueba "CPU-only: nada de torch, cuda ni difusion local"
PESADOS="$(docker run --rm "$IMAGEN" sh -c \
  'ls /opt/venv/lib/python3.12/site-packages 2>/dev/null | grep -iE "^(torch|nvidia|triton|diffusers|transformers|onnxruntime)" || true')"
if [ -n "$PESADOS" ]; then
  mal "la imagen incluye paquetes de GPU/difusion local: $PESADOS"
else
  ok "site-packages sin torch/nvidia/diffusers"
fi

# ---------------------------------------------------------------------------
prueba "el usuario dentro del contenedor no es root"
UID_DENTRO="$(docker compose run --rm -T --no-deps app id -u | tr -d '\r')"
if [ "$UID_DENTRO" = "0" ]; then
  mal "el contenedor corre como root. Revisa 'user:' en compose.yaml y USER en el Dockerfile."
else
  ok "uid dentro del contenedor: $UID_DENTRO (host: $UID_HOST)"
  [ "$UID_DENTRO" = "$UID_HOST" ] || aviso "no coincide con el uid del host; los archivos de ./salida van a salir con otro dueno"
fi

# La imagen sola (sin compose) tambien tiene que ser no-root.
UID_PELADO="$(docker run --rm "$IMAGEN" id -u | tr -d '\r')"
if [ "$UID_PELADO" = "0" ]; then
  mal "'docker run' sin compose arranca como root: falta USER en el Dockerfile"
else
  ok "'docker run' pelado arranca como uid $UID_PELADO"
fi

# ---------------------------------------------------------------------------
prueba "la imagen contiene SOLO codigo: los volumenes vienen vacios"
CONTENIDO="$(docker run --rm "$IMAGEN" sh -c \
  'ls -A /app/perfiles /app/data /app/salida /app/.cache 2>/dev/null | grep -v "^$" | grep -v ":$" || true')"
if [ -n "$CONTENIDO" ]; then
  mal "hay datos horneados en la imagen: $CONTENIDO"
  info "perfiles/, data/, salida/ y .cache/ tienen que entrar por bind, nunca por COPY"
else
  ok "los cuatro puntos de montaje estan vacios en la imagen"
fi

# ---------------------------------------------------------------------------
prueba "no hay secretos horneados en la imagen"
FUGA="$(docker run --rm "$IMAGEN" sh -c 'cat /app/.env /opt/venv/.env 2>/dev/null || true')"
if [ -n "$FUGA" ]; then
  mal "hay un .env dentro de la imagen"
else
  ok "sin .env dentro de la imagen"
fi
if docker image inspect -f '{{json .Config.Env}}' "$IMAGEN" | grep -qiE '(API_KEY|SECRET|TOKEN)":?"[^"]+'; then
  mal "hay claves en el ENV de la imagen"
else
  ok "el ENV de la imagen no lleva claves"
fi

# ---------------------------------------------------------------------------
prueba "thumbforge doctor corre dentro del contenedor y no toca la red"
if docker compose run --rm -T --no-deps app thumbforge doctor --sin-red; then
  ok "doctor --sin-red salio 0"
else
  mal "doctor --sin-red salio distinto de 0: hay algo que impide trabajar (ver la tabla de arriba)"
fi

prueba "doctor --quiet (el mismo chequeo que usa el healthcheck)"
if docker compose run --rm -T --no-deps app thumbforge doctor --quiet; then
  ok "doctor --quiet salio 0: el healthcheck daria 'healthy'"
else
  mal "doctor --quiet salio 1: el healthcheck daria 'unhealthy'"
fi

# ---------------------------------------------------------------------------
prueba "un archivo creado en /app/salida sale con el UID del host"
rm -f salida/.prueba_uid
docker compose run --rm -T --no-deps app sh -c 'printf ok > /app/salida/.prueba_uid'
if [ ! -f salida/.prueba_uid ]; then
  mal "el archivo no aparecio en ./salida: el bind no esta funcionando"
else
  DUENO="$(uid_de salida/.prueba_uid)"
  if [ "$DUENO" = "$UID_HOST" ]; then
    ok "./salida/.prueba_uid es del uid $DUENO (= el tuyo): no hace falta sudo para borrarlo"
  else
    mal "./salida/.prueba_uid quedo del uid $DUENO y vos sos $UID_HOST"
    info "Revisa UID/GID en .env y 'user:' en compose.yaml"
  fi
  rm -f salida/.prueba_uid
fi

# ---------------------------------------------------------------------------
prueba "los cuatro volumenes apuntan adentro del contenedor a donde espera app/rutas.py"
MAPEO="$(docker compose run --rm -T --no-deps app sh -c \
  'printf "%s %s %s %s\n" "$TF_PERFILES_DIR" "$TF_DATA_DIR" "$TF_SALIDA_DIR" "$TF_CACHE_DIR"' | tr -d '\r')"
ESPERADO="/app/perfiles /app/data /app/salida /app/.cache"
if [ "$MAPEO" = "$ESPERADO" ]; then
  ok "TF_PERFILES_DIR/TF_DATA_DIR/TF_SALIDA_DIR/TF_CACHE_DIR = $ESPERADO"
else
  mal "las variables de volumen valen '$MAPEO' y deberian valer '$ESPERADO'"
fi

# ---------------------------------------------------------------------------
if [ "$SIN_MULTIARCH" -eq 1 ]; then
  prueba "build multi-arquitectura (omitido por --sin-multiarch)"
  aviso "no verificado"
else
  prueba "el build funciona para linux/amd64 y linux/arm64"
  info "usa un builder temporal ($BUILDER, driver docker-container) y no toca el tuyo por defecto"
  docker buildx rm "$BUILDER" >/dev/null 2>&1 || true
  if ! docker buildx create --name "$BUILDER" --driver docker-container >/dev/null 2>&1; then
    aviso "no se pudo crear el builder docker-container: sin el, buildx no cruza arquitecturas"
  elif docker buildx build --builder "$BUILDER" \
        --platform linux/amd64,linux/arm64 \
        --output type=cacheonly .; then
    ok "las dos plataformas construyen (sin compilar nada: hay wheels manylinux para ambas)"
    info "Para publicar de verdad: docker buildx build --builder $BUILDER --platform linux/amd64,linux/arm64 -t <registro>/thumbforge:0.1.0 --push ."
  else
    mal "el build multi-arquitectura fallo"
    info "Si fallo compilando, es que a alguna dependencia le falta el wheel para esa plataforma"
  fi
fi

# ---------------------------------------------------------------------------
printf '\n%s----- resumen -----%s\n' "$C_TIT" "$C_FIN"
printf 'pruebas: %d   fallas: %d   avisos: %d\n' "$N" "$FALLOS" "$AVISOS"
if [ "$FALLOS" -gt 0 ]; then
  printf '%sEl empaquetado no esta listo.%s\n' "$C_MAL" "$C_FIN"
  exit 1
fi
printf '%sEmpaquetado verificado.%s\n' "$C_OK" "$C_FIN"
