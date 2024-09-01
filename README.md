# Documentation of QGIS-Server-Light

QGIS-Server-light is a python worker process which uses pyqgis
to render a set of layers into an image. It is backed by Redis
as a queue system.
All configuration happens at runtime through a lean interface.

## General idea

Driving many instances of QGIS-Server for rendering WMS maps gave us many insights of the actual needs.
Especially when it comes to deployment strategies fitting environments other than a metal server
driving your QGIS-Server, there are a bit of pitfalls here and there which are difficult to handle.

In bigger environments we deal with zero downtime requirements for PROD instances. Varying datasource
definitions dependent on the layer (not only database). Massive amount of QGIS project files
which need to be tracked for validity and content over time. We often need rollback mechanisms of deployments.
In short: Small to big environments utilizing QGIS-Server ending up often in the classic pattern of
administer => integrate => publish.

We can state, that we are perfectly able to implement this with QGIS-Server. However, it lacks several simple
patterns of automatisation and scalability.

QGIS-Server-Light tries to overcome this issues with the following main concepts:

- separate QGIS project from QGIS-Server runtime
- isolate rendering into a minuscule python process
- provide ephemeral runtime

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

## Spin up a redis instance

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
docker build -t opengisch/qgis-server-light:dev --target dev .
```

Then run:
```shell
docker run --rm -e REDIS_URL=redis://localhost:1234 -e LOG_LEVEL=debug -v $(pwd):/app --net host opengisch/qgis-server-light:dev
```

Congratulations... Your QGIS-Server-Light is running and waits for jobs in the redis queue.

## DEV

### Running things

All deps are transparent. The biggest one is QGIS and its relatives of course. If you want to develop
this package further you can use the local way described above.

If you have issues with matching QGIS version on your system and the one used by QGIS-Server-Light
you should prefer the docker way with the source code mounted to the running container.

```shell
docker run --rm -e REDIS_URL=redis://localhost:1234 -e LOG_LEVEL=debug -v $(pwd):/app --net host opengisch/qgis-server-light:dev
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

## Generate QGIS Project config

By separating QGIS project information from the servers runtime we save a lot of headaches and be sure to
have the server know only what it should know. With that we minimize the amount of potential bugs drastically.
There is another idea embedded here. Thinking of a big amount of QGIS projects with a ton of layer in each
served by 4 instances of QGIS-Server (in a classical setup) for load balancing reasons as WMS. This means each
server has to solve several tasks (Capabilities, Rendering, LayerTree knowledge etc.). Not only that rendering
a WMS request does not need any knowledge of a tree structure but a one dimensional ordered stacking list
of layers. Serving the capabilities with lets say a permission system is not being implemented easily.

However, this comes with a downside:

* We need to extract this information from a QGIS-Project to feed the server with it at runtime to empower it
  for rendering our requested layers.

QGIS-Server-Light gives you a typed way
([python lib](src/qgis_server_light/interface)) to store extracted information of a QGIS project. This is
what you can use programmatically in your 3rd party application. In addition, it offers a
[CLI](src/qgis_server_light/exporter/cli.py) to just do a command line call to extract the information.

### Using the CLI

You can extract information of a QGIS-Project like this:

```shell
.venv/bin/python3 -m qgis_server_light.exporter.cli --project [path-to-your-project]
```

This uses the default output format `json` and does not `unify layer names` in the project.

| :exclamation:  This command writes to stdout! |
|-----------------------------------------------|

If you want to save the output to a file, you can do by:

```shell
.venv/bin/python3 -m qgis_server_light.exporter.cli --project [path-to-your-project] > project_config.json
```

#### Supported QGIS project extensions

- `qgs`
- `qgz`

#### Supported output formats

`--output_format`

- `json` (default)
- `xml`

#### Unify layer names

`--unify_layer_names_by_group`

- `False` (default)
- `True`

There is an option `unify_layer_names_by_group`. It allows you to reflect the structure of your tree in the
layer names.

Let's say you have a tree structure like that:
```
environment
├── ground_coverage
│   ├── forest
│   ├── field
│   └── lake
└── forest
```

And presume it is the layer names we see. So the short name which is the name used for exposition to WMS.
This would end up in forest being not addressable in a WMS request easily unless we would use the layer id
of QGIS project layer. But this is not so nicely read in the capabilities in the end.

So enabling this option, will produce the following names for the layers:

- `environment.forest`
- `environment.ground_coverage.forest`
- `environment.ground_coverage.field`
- `environment.ground_coverage.lake`

## Job interface

Todo...
