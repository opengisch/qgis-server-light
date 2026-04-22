![Image build](https://github.com/opengisch/qgis-server-light/actions/workflows/image.yml/badge.svg)
![Docs build](https://github.com/opengisch/qgis-server-light/actions/workflows/docs.yml/badge.svg)

# QGIS-Server-Light

QGIS-Server-Light is a python worker process which uses pyqgis
to:

- render a map from a set of layers
- extract vector features

All configuration happens at runtime through a lean interface at runtime.

It is backed by Redis as a queue system.

## Quick start

```shell
docker run --rm -d -p 1234:6379 --name qsl-redis redis
```

```shell
docker run -ti --rm --net host --name qsl opengisch/qgis-server-light:latest
```

In case you have local geodata which is used in your QGIS projects, you need to make it
available to
QGIS-Server-Light through a volume mount:

```shell
docker run -ti --rm --net host --name qsl -v <local-path-to-your-qgis-projects>:/io/data opengisch/qgis-server-light:latest
```

## Documentation

The complete documentation is available at the
[documentation](https://opengisch.github.io/qgis-server-light).
