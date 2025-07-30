This variant is meant to be used for development purpose. In any case you need a running redis
instance where QGIS-Server-Light can handle the jobs. See
[Docker Usage](usage.qsl.docker.md#spin-up-a-redis-instance) for instructions how to spin up your own local
instance easily.

### Runtime explained

For more easy handling we use [GNU Make](https://www.gnu.org/software/make/) to prepare everything in short
and usable targets so you can start straight away. We recommend to use this prepared make targets when you
handle QGIS-Server-Light locally. This ensures everything you need (especially the dependencies) are nicely
wrapped into a venv in the folder `.venv`.

!!! important
    This means, you need to have GNU Make installed on you system!

#### Most important targets

- `make install-dev` => Installs QGIS-Server-Light into the `.venv`, so that you can use it locally. This
    trys to find the local path to pyqgis (part of the qgis installation) and links it. If that step is not
    successful, QGIS-Server-Light won't work
- `make run` => Starts up one QGIS-Server-Light process. This only works if above-mentioned step was
    successful.
- `make run-reload` => Same as above but reloads process everytime code was changed.
- `make doc-html` => Produces the HTML version of the documentation in `docs/site`
- `make test` => Run the tests.

### Spin up one QGIS-Server-Light worker

This step assumes you have the locally running redis instance as described in the above linked instructions.

```shell
make run
```

This spins up the worker with these settings:

| Parameter | Value                  |
|-----------|------------------------|
| redis-url | redis://localhost:1234 |
| svg-path  | /io/svg                |
| data-root | /io/data               |
| log-level | info                   |

### Environment variables available with make

If you want to manipulate the default values, you can do so by set environment variables. Whether directly
with you call or in the systems' environment.

The following variables are available:

| ENV Variable    | Default value          |
|-----------------|------------------------|
| QSL_REDIS_URL   | redis://localhost:1234 |
| QSL_SVG_PATH    | /io/svg                |
| QSL_DATA_ROOT   | /io/data               |
| QSL_LOG_LEVEL   | info                   |

You can easily overwrite these default values by defining ENVIRONMENT variables with your command execution:
```shell
QSL_REDIS_URL=redis://my.redis.host:9999 make run
```

In addition, you may want to use an `.env`. If you place such a file
in the project root you can run the command and variables from the `.env` file
will be applied as available.
