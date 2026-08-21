ARG QGIS_VERSION=3.44.13
FROM ghcr.io/opengisch/qgis-slim:$QGIS_VERSION AS base

LABEL org.opencontainers.image.authors="Clemens Rudert <clemens@opengis.ch>"
LABEL org.opencontainers.image.vendor="opengis.ch"
LABEL org.opencontainers.image.title="QGIS-Server-Light Base Image"

# qgis-slim image has a non root user set up, we need to switch first to root
USER 0

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get remove -y python3-sip \
  && apt-get install -y \
    perl \
    build-essential \
    python3-dev \
    openssh-server \
    sudo

COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/

#########################
#  DEV
#########################
FROM base AS dev

ARG UID=1000
ARG GID=1000
ARG USERPWD=secret
ARG USER=appuser
ARG UV_CACHE_DIR_BUILD_TIME=/home/$USER/.cache/uv-build-time
ARG UV_CACHE_DIR_RUN_TIME=/home/$USER/.cache/uv
#https://docs.astral.sh/uv/reference/environment/#uv_override
ARG UV_PROJECT_ENVIRONMENT=/home/$USER/.venv

RUN deluser --remove-home $(id -nu $UID)

# Setup a non-root user
RUN groupadd --system --gid $GID nonroot \
 && useradd --system --gid $GID --uid $UID --create-home appuser \
 && echo "$USER:$USERPWD" | chpasswd

# We allow the non root user sudo access on decent actions
RUN echo "$USER ALL=(root) NOPASSWD: /usr/sbin/sshd, /etc/ssh/ssh_keygen, /bin/chown, /bin/chmod, /bin/mkdir" >> /etc/sudoers.d/$USER && \
    chmod 0440 /etc/sudoers.d/$USER

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
