FROM opengisch/qgis-server:3.22 AS dev

LABEL maintainer="Clemens Rudert <clemens.rudert@bl.ch>"

ENV OGIS_SERVER_LIGHT_THEMES_DIR="/io/themes"
ENV OGIS_SERVER_LIGHT_LOG_LEVEL="DEBUG"

RUN apt update && apt install -y \
      make \
      python3.8-venv

STOPSIGNAL SIGINT
WORKDIR /app

CMD ["make", "serve-dev"]

FROM dev

ENV DEVELOPMENT=FALSE \
    PYRAMID_RELOAD_TEMPLATES=0 \
    PYRAMID_RELOAD_ASSETS=0 \
    PYRAMID_DEBUG_AUTHORIZATION=0 \
    PYRAMID_DEBUG_NOTFOUND=0 \
    PYRAMID_DEBUG_ROUTEMATCH=0 \
    PYRAMID_PREVENT_HTTP_CACHE=0 \
    PYRAMID_PREVENT_CACHEBUST=0 \
    PYRAMID_DEBUG_ALL=0 \
    PYRAMID_RELOAD_ALL=0 \
    pyramid_mapnik_wms_LOG_LEVEL="INFO"

USER 1001

COPY . /app/

RUN make install && \
    for file in $(find . -name '*.pyc'); do rm -f $file; done

CMD ["/usr/bin/make", "serve"]
