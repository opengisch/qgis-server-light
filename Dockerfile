FROM ghcr.io/opengisch/qgis-slim:3.34.8 AS dev

LABEL org.opengisch.author="Clemens Rudert <clemens.rudert@bl.ch>"
LABEL org.opengisch.image.title="QGIS-Server-Light"
USER 0

RUN apt-get update -y && \
    apt-get install -y \
      python3-full \
      python3-dev \
      make \
      build-essential

WORKDIR /opt/qgis-server-light/
ADD requirements.worker.txt .
ADD requirements.interface.txt .
ADD Makefile .

ENV VENV_PATH=/opt/qgis-server-light/venv
RUN VENV_PATH=${VENV_PATH} make install

WORKDIR /app

COPY . .

RUN /opt/qgis-server-light/venv/bin/pip3 install -e . --no-cache-dir

ENTRYPOINT ["/tini", "--", "/opt/qgis-server-light/venv/bin/python3", "-m"]

CMD ["qgis_server_light.worker.redis"]
