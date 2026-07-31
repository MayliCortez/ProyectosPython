# syntax=docker/dockerfile:1
#
# thumbforge - imagen de SOLO CODIGO.
#
# perfiles/, data/, salida/ y .cache/ NO entran aca: son volumenes bind
# (ver compose.yaml). Reconstruir o actualizar la imagen no toca el trabajo.
#
# Base pinneada POR DIGEST, no por tag: un tag muta debajo de los pies, un
# digest no. El digest es el del INDICE multi-arquitectura, no el de una
# plataforma concreta: asi el mismo Dockerfile sirve para amd64 y arm64.
#
#   python:3.12-slim -> indice sha256:57cd7c3a...710de (Python 3.12.13, 2026-07-14)
#     linux/amd64  sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464
#     linux/arm64  sha256:55842c72c6b3584d06ec84c731fc516b30b8a53ad262ebd085e47ab568b3bfc1
#
# Para actualizar la base: scripts/verificar_imagen.sh --solo-digest resuelve
# el digest actual del tag y lo compara con el que esta pinneado aca.
ARG BASE_IMAGEN=python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de


# ---------------------------------------------------------------------------
# Etapa 1: builder. Arma el virtualenv y nada mas.
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGEN} AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_ROOT_USER_ACTION=ignore

# Extras opcionales del paquete: "" para la CLI, "[web]" para el servicio web
# del paso 8. Se pasa desde compose.yaml (build.args).
ARG TF_EXTRAS=""

WORKDIR /origen

# Sin build-essential a proposito. Las cuatro dependencias publican wheels
# manylinux cp312 para x86_64 y aarch64, asi que no hay nada que compilar. Si
# este RUN falla intentando compilar, es que falta un wheel para esa
# plataforma: eso hay que mirarlo, no taparlo agregando gcc.
#
# Primero solo los metadatos y un paquete vacio: instala las dependencias en
# una capa que no se invalida cuando cambia el codigo de app/.
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install ".${TF_EXTRAS}"

# Ahora el codigo real. --no-deps porque las dependencias ya estan resueltas.
COPY app ./app
RUN /opt/venv/bin/pip install --no-deps --force-reinstall ".${TF_EXTRAS}"

# La imagen final no instala paquetes: pip dentro del venv son ~20 MB
# duplicados (la base ya trae el suyo en /usr/local) y una invitacion a
# parchear un contenedor en caliente, cambio que se pierde al recrearlo.
RUN /opt/venv/bin/python -m pip uninstall -y pip


# ---------------------------------------------------------------------------
# Etapa 2: imagen final. Solo el virtualenv, que ya contiene el paquete
# thumbforge instalado y su comando en /opt/venv/bin/thumbforge. Ningun
# compilador, ningun cache de pip, ningun archivo de build.
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGEN} AS final

LABEL org.opencontainers.image.title="thumbforge" \
      org.opencontainers.image.description="Motor de miniaturas multi-nicho. CPU-only, sin GPU, sin difusion local." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="python:3.12-slim" \
      org.opencontainers.image.base.digest="sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:${PATH}"

# El contenedor corre con el UID/GID del host (ver 'user:' en compose.yaml),
# que puede ser cualquiera. HOME tiene que ser escribible por ese UID sea cual
# sea: /tmp siempre lo es, y nada de la app guarda estado en HOME.
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/app/.cache

# Los cuatro volumenes, con los nombres de variable que lee app/rutas.py.
ENV TF_PERFILES_DIR=/app/perfiles
ENV TF_DATA_DIR=/app/data
ENV TF_SALIDA_DIR=/app/salida
ENV TF_CACHE_DIR=/app/.cache
ENV TF_EN_CONTENEDOR=1

# Usuario no-root por defecto. compose.yaml lo pisa con el UID/GID del host
# para que lo que aparece en ./salida no quede propiedad de root; este usuario
# cubre el caso de un 'docker run' pelado.
RUN groupadd --gid 1000 forge \
 && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin forge

COPY --from=builder --chown=1000:1000 /opt/venv /opt/venv

# Puntos de montaje de los cuatro volumenes. En uso real el bind del host los
# tapa y mandan los permisos del host; el 0777 existe para que un 'docker run'
# con un UID arbitrario y sin binds tampoco se trabe escribiendo.
RUN mkdir -p /app/perfiles /app/data /app/salida /app/.cache \
 && chown -R 1000:1000 /app \
 && chmod -R 0777 /app

WORKDIR /app
USER 1000:1000

# 'doctor --quiet' no toca la red y sale 1 si hay errores que impiden trabajar
# (entre ellos: no encontrar ningun perfil, o no poder escribir un volumen).
HEALTHCHECK --interval=60s --timeout=20s --start-period=10s --retries=3 \
    CMD ["thumbforge", "doctor", "--quiet"]

# Sin ENTRYPOINT: el uso normal es 'docker compose run --rm app thumbforge ...'
# y un entrypoint fijo obligaria a omitir el nombre del comando o a repetirlo.
CMD ["thumbforge", "doctor"]
