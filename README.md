# Documentation of QGIS-Server-Light

QGIS-Server-light is a python worker process which uses pyqgis
to render a set of layers into an image. It is backed by Redis
as a queue system.
All configuration happens at runtime through a lean interface.

## Structure

QGIS-Server-Light is made of three subparts.

- exporter => export necesary data from a qgis project to a simple json (has deps to pyqgis)
- interface => defines all entities shipped around and may be used in 3rd party software (no deps to pyqgis)
- worker => the actual rendering system which you can spawn

## Prerequisites

QGIS-Server-light is nothing but a renderer. It does not know what a WMS request is nor
does it know which layer it can render. All information is delivered at runtime by a
3rd party application which is not part of this stack. The current implementation chose
Redis as an intermediate broker/store where the 3rd party application can push its
requests, and they will be picked and processed by QGIS-Server-Light.

So to further proceed you need a running instance of Redis. If you want to feed QGIS-Server-Light
with actual rendering jobs you will need an application which puts jobs in the redis queue.

### Spin up a redis instance

```shell
docker run --rm -d -p 1234:6379 --name georama-redis redis
```

This redis instance will be available with url: `redis://localhost:1234`

## Prepare to run an instance of QGIS-Server-Light

### Local DEV instance with QGIS installed

If pyqgis is installed into your system python you can run:
```shell
make install
```
else you must pass the path to pyqgis (`/usr/share/qgis/python`) usually:
```shell
QGIS_PY_PATH=<path to python of qgis installation> make dev
```

### Run QGIS-Server-Light worker

```shell
REDIS_URL=redis://localhost:1234 .venv/bin/python3 -m qgis_server_light.worker.redis
```

Congratulations... Your QGIS-Server-Light is running and waits for jobs in the redis queue.

### Docker Image

If you don't have QGIS installed or some versions are not matching on you machine
the recommended way of running this stack is Docker (docker need to be installed in a recent version).

First you need to build the image:
```shell
docker build -t qgis-server-light:3.34.8-dev --target dev .
```

Then run:
```shell
docker run --rm -e REDIS_URL=redis://localhost:1234 -e LOG_LEVEL=debug -v $(pwd):/app --net host qgis-server-light:3.34.8-dev
```

Congratulations... Your QGIS-Server-Light is running and waits for jobs in the redis queue.

## DEV

### Running things

All deps are transparent. The biggest one is QGIS and its relatives of course. If you want to develop
this package further you can use the local way described above.

If you have issues with matching QGIS version on your system and the one used by QGIS-Server-Light
you should prefer the docker way with the source code mounted to the running container.

```shell
docker run --rm -e REDIS_URL=redis://localhost:1234 -e LOG_LEVEL=debug -v $(pwd):/app --net host qgis-server-light:3.34.8-dev
```

That way the current changes you make are transparently available in the container.

For better IDE support it is to be mentioned that the python interpreter inside the container with access
to all the necessary python libs is available at `opt/qgis-server-light/venv/bin/python3`

### PyPi Dependencies

If you decide to add new requirements to this project, please consider for which part of the project
you need them. Remember, it's split into 3 parts:
- exporter ([requirements.exporter.txt](requirements.exporter.txt))
- interface ([requirements.interface.txt](requirements.interface.txt))
- worker ([requirements.worker.txt](requirements.worker.txt))

In general its save to add dependencies to **exporter** and **worker** since they are used only in this project.
The **interface** should have as less dependencies as possible and should implement only the minimal
understanding of items to be passed around with third party applications through redis. The main goal of all
this is to keep the 3rd party application clean of heavy deps.

### PyPy Package

The pypi package consists only the part of the interface since it is the part we need to use in 3rd party
apps.

#### PyPi

Not set up yet

#### GitHub

It is possible to install a package as a dependency in you 3rd party application requirements using a
GitHub link.

```requirements
git+ssh://git@github.com/opengisch/qgis-server-light.git@master#egg=qgis_server_light
```
