![Image build](https://github.com/opengisch/qgis-server-light/actions/workflows/image.yml/badge.svg)
![Docs build](https://github.com/opengisch/qgis-server-light/actions/workflows/docs.yml/badge.svg)


# QGIS-Server-Light

QGIS-Server-light is a python worker process which uses pyqgis
to render a set of layers into an image. It is backed by Redis
as a queue system.
All configuration happens at runtime through a lean interface.

## Quick start

```shell
docker run --rm -d -p 1234:6379 --name qsl-redis redis
```

```shell
docker run -ti --rm --net host --name qsl opengisch/qgis-server-light:latest
```

In case you have local geodata which is used in your QGIS projects, you need to make it available to
QGIS-Server-Light through a volume mount:

```shell
docker run -ti --rm --net host --name qsl -v <local-path-to-your-qgis-projects>:/io/data opengisch/qgis-server-light:latest
```

## Documentation

For further details and a better understanding please refer to the
[documentation](https://opengisch.github.io/qgis-server-light).
