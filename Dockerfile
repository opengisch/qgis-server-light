ARG QGIS_VERSION=3.44.13
FROM ghcr.io/opengisch/qgis-slim:$QGIS_VERSION AS base

# this base image defines ENTRYPOINT [ "/tini", "--", "/usr/local/bin/uid_entrypoint.sh" ]!!!

LABEL org.opencontainers.image.authors="OPENGIS.ch <info@opengis.ch>"
LABEL org.opencontainers.image.vendor="opengis.ch"
LABEL org.opencontainers.image.title="QGIS-Server-Light Base Image"

# qgis-slim image has a non root user set up, we need to switch first to root
USER 0

ENV DEBIAN_FRONTEND=noninteractive

FROM base AS base-builder

RUN apt-get update \
  && apt-get remove -y python3-sip \
  && apt-get install -y \
    build-essential \
    python3-dev

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

#########################
#  DEV (contains all interface,worker,exporter)
#########################
FROM base-builder AS dev

ARG UID=1000
ARG GID=1000
ARG USERPWD=secret
ARG USER=appuser
ARG UV_CACHE_DIR_BUILD_TIME=/home/$USER/.cache/uv-build-time
ARG UV_CACHE_DIR_RUN_TIME=/home/$USER/.cache/uv
#https://docs.astral.sh/uv/reference/environment/#uv_override
ARG UV_PROJECT_ENVIRONMENT=/home/$USER/.venv

ENV PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"

RUN apt-get update \
  && apt-get install -y \
    perl \
    git \
    zsh
RUN deluser --remove-home $(id -nu $UID)

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

COPY ./docker/dev.debug.entrypoint.sh /usr/local/bin/dev.debug.entrypoint.sh
COPY ./docker/dev.start.worker.sh /usr/local/bin/dev.start.worker.sh

# starts the worker when container starts, set this to 0 to use it with devcontainers
# or with remote development features of your favourite IDE
ENV DEV_AUTOSTART=1

ENTRYPOINT [ "/tini", "--", "/usr/local/bin/uid_entrypoint.sh", "/usr/local/bin/dev.debug.entrypoint.sh"]

CMD [ "/usr/local/bin/dev.start.worker.sh" ]


#########################
#  BUILD WORKER (FOR RELEASE)
#########################
FROM base-builder AS worker-builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv --system-site-packages
RUN uv sync --frozen --no-install-project --no-dev --group worker

COPY ./src ./src
COPY ./README.md ./
COPY ./LICENSE ./
RUN uv sync --frozen --no-dev --no-editable --group worker

#########################
#  BUILD EXPORTER (FOR RELEASE)
#########################
FROM base-builder AS exporter-builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv --system-site-packages
RUN uv sync --frozen --no-install-project --no-dev --group exporter

COPY ./src ./src
COPY ./README.md ./
COPY ./LICENSE ./
RUN uv sync --frozen --no-dev --no-editable --group exporter

#########################
#  RELEASE EXPORTER
#########################
FROM base AS exporter

ENV QSL_EXPORTER_LOG_LEVEL=info

WORKDIR /io/data
WORKDIR /io/svg
WORKDIR /app

COPY docker/prod.run-exporter.sh /usr/local/bin/
COPY --from=exporter-builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD [ "/usr/local/bin/prod.run-exporter.sh" ]

USER 1001

#########################
#  RELEASE WORKER (stays last, default target)
#########################
FROM base AS worker

ENV QSL_LOG_LEVEL=info

WORKDIR /io/data
WORKDIR /io/svg
WORKDIR /app

COPY docker/prod.run-worker.sh /usr/local/bin/
COPY --from=worker-builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

CMD [ "/usr/local/bin/prod.run-worker.sh" ]

USER 1001