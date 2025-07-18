![Image build](https://github.com/opengisch/qgis-server-light/actions/workflows/image.yml/badge.svg)
![Docs build](https://github.com/opengisch/qgis-server-light/actions/workflows/docs.yml/badge.svg)


# QGIS-Server-Light

QGIS-Server-light is a python worker process which uses pyqgis
to render a set of layers into an image. It is backed by Redis
as a queue system.
All configuration happens at runtime through a lean interface.

## Quick start

```shell
docker run --rm -d -p 1234:6379 --name georama-redis redis
```

```shell
docker run --rm -e QSL_REDIS_URL=redis://localhost:1234 --net host ghcr.io/opengisch/qgis-server-light:latest
```

## Quick start DEV

Create an .env file and put the content of [.env.example](.env.example) into it. Adapt as needed.

```shell
docker compose up -d
```

## Documentation

For further details and a better understanding please refer to the
[documentation](https://opengisch.github.io/qgis-server-light).


# run it locally

```shell
QGIS_PY_PATH=/usr/lib/python3.13/site-packages make clean-all install-dev
# run worker with hot reload on source changes (useful for development)
hupper -m qgis_server_light.worker.redis --redis-url redis://localhost:1234 --log-level debug --data-root /home/kalle/projects/opengis/georama.test_data/
# run worker just as is without hot reload
python -m qgis_server_light.worker.redis --redis-url redis://localhost:1234 --log-level debug --data-root /home/kalle/projects/opengis/georama.test_data/
```
