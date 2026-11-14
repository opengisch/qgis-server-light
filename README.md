<div align="center">
  <a href="https://github.com/opengisch/qgis-server-light">
    <img src="https://socialify.git.ci/opengisch/qgis-server-light/image?description=1&forks=1&issues=1&language=1&owner=1&pulls=1&stargazers=1&theme=Auto" alt="qgis-server-light" width="640" />
  </a>
</div>

# QGIS-Server-Light

QGIS workers in pure python. Stateless, fed by a redis queue, every job brings
everything the worker needs to know about the layers it has to handle.

[![TestSuite](https://github.com/opengisch/qgis-server-light/actions/workflows/test.yaml/badge.svg)](https://github.com/opengisch/qgis-server-light/actions/workflows/test.yaml)
[![Release](https://img.shields.io/github/v/release/opengisch/qgis-server-light)](https://github.com/opengisch/qgis-server-light/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/opengisch/qgis-server-light)](https://hub.docker.com/r/opengisch/qgis-server-light)
[![License](https://img.shields.io/github/license/opengisch/qgis-server-light)](LICENSE)

[![Docs](https://github.com/opengisch/qgis-server-light/actions/workflows/docs.yml/badge.svg)](https://opengisch.github.io/qgis-server-light/)
![Python](https://img.shields.io/badge/python-%3E%3D3.12-blue)
![GitHub Contributors](https://img.shields.io/github/contributors/opengisch/qgis-server-light)
![GitHub Issues](https://img.shields.io/github/issues/opengisch/qgis-server-light)
![GitHub Pull Requests](https://img.shields.io/github/issues-pr/opengisch/qgis-server-light)
![GitHub last commit](https://img.shields.io/github/last-commit/opengisch/qgis-server-light)

[![Powered by QGIS](https://img.shields.io/badge/powered%20by-QGIS-589632?logo=qgis&logoColor=white)](https://qgis.org)
[![Fed by Redis](https://img.shields.io/badge/fed%20by-Redis-DC382D?logo=redis&logoColor=white)](https://redis.io)

## Commands

```shell
cp .env.dev.example .env
```

```shell
docker compose up --watch --remove-orphans
```

```shell
docker compose run --rm --entrypoint bash worker -c "uv run pytest"
```

```shell
docker compose run --rm --entrypoint bash worker -c "uv run mkdocs build -f docs/mkdocs.yml -d site"
```

## DEV

The provided compose does offer a virtual environment inside the
worker service container. You may want to use this with your IDE for
code completion. It's located inside the container at `/home/appuser/.venv`.

Either you use the container directly or the provided [devcontainer](.devcontainer/devcontainer.json)
which attaches your IDE to the worker service. Inside the devcontainer the worker is not started
automatically (`DEV_AUTOSTART=0`), you start it yourself:

```shell
/usr/local/bin/dev.start.worker.sh
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=opengisch/qgis-server-light&type=Date)](https://star-history.com/#opengisch/qgis-server-light&Date)

## Contributors

[![Contributors](https://contrib.rocks/image?repo=opengisch/qgis-server-light)](https://github.com/opengisch/qgis-server-light/graphs/contributors)
