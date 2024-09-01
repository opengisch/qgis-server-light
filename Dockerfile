FROM ghcr.io/opengisch/qgis-slim:3.34.10 AS base

# switch to root user for install
USER 0

RUN apt-get update && \
    apt-get install -y \
      python3-pip \
      python3-setuptools

#########################
#  DEV
#########################
FROM base AS dev

LABEL org.opengisch.author="Clemens Rudert <clemens.rudert@bl.ch>"
LABEL org.opengisch.image.title="QGIS-Server-Light"
USER 0

RUN apt-get install -y \
      python3-venv \
      make

WORKDIR /opt/qgis-server-light/
ADD requirements.worker.txt .
ADD requirements.interface.txt .
ADD requirements.exporter.txt .
ADD Makefile .

ENV VENV_PATH=/opt/qgis-server-light/venv
RUN VENV_PATH=${VENV_PATH} make install

WORKDIR /app

COPY ./ .

RUN VENV_PATH=${VENV_PATH} make dev

ENTRYPOINT ["/tini", "--", "/opt/qgis-server-light/venv/bin/python3", "-m"]

CMD ["qgis_server_light.worker.redis"]

#########################
#  BUILDER (FOR RELEASE)
#########################
FROM base AS builder

WORKDIR /app
COPY ./ .
RUN WITH_WORKER=true python3 setup.py bdist_wheel

#########################
#  RELEASE
#########################
FROM base AS release
COPY --from=builder /app/dist/*.whl /tmp
RUN pip3 install /tmp/*.whl

USER 1001

CMD ["redis_worker"]
