# syntax=docker/dockerfile:1.17
ARG QGIS_VERSION=3.44.13
FROM ghcr.io/opengisch/qgis-slim:$QGIS_VERSION AS base

LABEL org.opencontainers.image.authors="OPENGIS.ch <info@opengis.ch>"
LABEL org.opencontainers.image.vendor="opengis.ch"
LABEL org.opencontainers.image.title="QGIS-Server-Light Base Image"

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

#########################
#  BUILD BASE
#########################
FROM base AS build-base

USER 0
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
     build-essential \
     python3-dev \
     git \
 && rm -rf /var/lib/apt/lists/*

#########################
#  DEV
#########################
FROM build-base AS dev

# Configurable user / group to allow for editing files in mounted volumes with the host system user
ARG UID=1000
ARG GID=1000
ARG USERPWD=secret
ARG USER=appuser

ARG UV_CACHE_DIR_BUILD_TIME=/home/$USER/.cache/uv-build-time
ARG UV_CACHE_DIR_RUN_TIME=/home/$USER/.cache/uv
#https://docs.astral.sh/uv/reference/environment/#uv_override
ARG UV_PROJECT_ENVIRONMENT=/home/$USER/.venv

RUN deluser --remove-home $(id -nu 1000)

# Setup a non-root user
RUN groupadd --system --gid $GID nonroot \
 && useradd --system --gid $GID --uid $UID --create-home appuser \
 && echo "$USER:$USERPWD" | chpasswd

WORKDIR /app

RUN chown -R $UID:$GID /app
RUN mkdir -p $UV_CACHE_DIR_RUN_TIME
RUN chown -R $UID:$GID $UV_CACHE_DIR_RUN_TIME

# https://docs.astral.sh/uv/reference/environment/#uv_python_cache_dir
ENV UV_PYTHON_CACHE_DIR=$UV_CACHE_DIR_RUN_TIME
# https://docs.astral.sh/uv/reference/environment/#uv_link_mode
ENV UV_LINK_MODE=copy
#https://docs.astral.sh/uv/reference/environment/#uv_override
ENV UV_PROJECT_ENVIRONMENT=$UV_PROJECT_ENVIRONMENT

# We install only the deps at build time,
#   not the project itself
USER appuser

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=$UV_CACHE_DIR_BUILD_TIME,uid=$UID,gid=$GID \
    python3 -c "import platform; print(platform.python_version())" > .python-version \
 && mkdir -p $(python3 -m site --user-site) \
 && echo $(python3 -c 'import os; import qgis; from pathlib import Path; print(Path(os.path.dirname(qgis.__file__)).parent)') > $(python3 -m site --user-site)/qgis.pth \
 && uv venv --system-site-packages $UV_PROJECT_ENVIRONMENT \
 && uv sync --frozen --no-install-project --group dev \
 && cp -r $UV_CACHE_DIR_BUILD_TIME/. $UV_CACHE_DIR_RUN_TIME

# switch back to root user for development
USER 0

#########################
#  PROD
#########################
FROM build-base AS prod-builder

WORKDIR /app

USER 0

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_PYTHON_CACHE_DIR=/tmp/uv-python-cache
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH=$UV_PROJECT_ENVIRONMENT/bin:$PATH
RUN mkdir -p $UV_CACHE_DIR $UV_PYTHON_CACHE_DIR $UV_PROJECT_ENVIRONMENT

RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv venv --system-site-packages $UV_PROJECT_ENVIRONMENT \
 && uv sync --frozen --no-install-project --group worker --group exporter

FROM base AS prod

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH=$UV_PROJECT_ENVIRONMENT/bin:$PATH

COPY --from=prod-builder /opt/venv /opt/venv
COPY src /app/src
COPY pyproject.toml /app/pyproject.toml
