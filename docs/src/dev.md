## Prepare to run an instance of QGIS-Server-Light

### Run it with python and with QGIS installed locally

You can choose this solution if you have QGIS and Python in the correct versions installed on your system.

#### Preparation

The following command installs all dependencies in a local virtual environment in the project root
folder to `.venv`:

```shell
make install-dev
```

It tries to find the correct path to the `pyqgis` of your local QGIS desktop installation.

#### Run QGIS-Server-Light worker

Spin up a redis instance:

```shell
docker run --rm -d -p 1234:6379 --name georama-redis redis
```

Spin up QGIS-Server-Light worker:

```shell
make run
```

You may want start QGIS-Server-Light worker in a reloading mode so that everytime you change the source
code, the worker gets reloaded. You can do so with:

```shell
make run-dev
```

Congratulations... Your QGIS-Server-Light is running and waits for jobs in the redis queue.

### Run it within a Docker container

If you don't have QGIS installed or some versions are not matching on you machine
the recommended way of running this stack is Docker (docker need to be installed in a recent version).

#### Preparation

First you need to build the image:
```shell
docker build -t opengisch/qgis-server-light:dev --target dev .
```

#### Run QGIS-Server-Light worker

Spin up a redis instance:

```shell
docker run --rm -d -p 1234:6379 --name georama-redis redis
```

Then run:
```shell
docker run --rm -e QSL_REDIS_URL=redis://localhost:1234 -e QSL_LOG_LEVEL=debug -v $(pwd):/app --net host opengisch/qgis-server-light:dev
```

Congratulations... Your QGIS-Server-Light is running and waits for jobs in the redis queue.


### Run it with Docker Compose

Create an .env file and put the content of [.env.example](.env.example) into it. Adapt as needed.

```shell
docker compose up -d
```

- `QSL_DATA_MOUNT` has to be the valid local absolute path where your qgis projects (and their data) are stored
- Optional: `QSL_LOG_LEVEL` log levels as they are defined by pythons
  [logging](https://docs.python.org/3/library/logging.html#logging-levels) library
- Optional: `QSL_REPLICAS` can be 1 up to * (note, that this has to be balanced with your system resources)
- Optional: `QSL_REDIS_URL`=redis://redis (since we are inside our composition, this is optional)


## DEV Details

### Running things

All deps are transparent. The biggest one is QGIS and its relatives of course. If you want to develop
this package further you can use the local way described above.

If you have issues with matching QGIS version on your system and the one used by QGIS-Server-Light
you should prefer the docker way with the source code mounted to the running container.

```shell
docker run --rm -e QSL_REDIS_URL=redis://localhost:1234 -e QSL_LOG_LEVEL=debug -v $(pwd):/app --net host opengisch/qgis-server-light:dev
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
