FROM ghcr.io/opengisch/qgis-slim:3.40.9 AS base

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

LABEL org.opengisch.author="Clemens Rudert <clemens@opengis.ch>"
LABEL org.opengisch.image.title="QGIS-Server-Light"
USER 0

RUN apt-get install -y \
      python3-venv \
      make

WORKDIR /opt/qgis-server-light/
WORKDIR /app
COPY ./ .

ENV VENV_PATH=/opt/qgis-server-light/venv
RUN make install-dev

ENTRYPOINT ["/tini", "--", "make"]
CMD ["run-reload"]

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
COPY --chmod=+x docker/run /bin
RUN pip3 install --break-system-packages /tmp/*.whl

ENV QSL_REDIS_URL=redis://localhost:1234
ENV QSL_SVG_PATH=/io/svg
ENV QSL_DATA_ROOT=/io/data
ENV QSL_LOG_LEVEL=info

USER 1001
ENTRYPOINT ["/tini", "--"]
CMD [\
    "sh", "-c", "redis_worker \
    --redis-url \"$QSL_REDIS_URL\" \
    --svg-path \"$QSL_SVG_PATH\" \
    --data-root \"$QSL_DATA_ROOT\" \
    --log-level \"$QSL_LOG_LEVEL\""\
]
