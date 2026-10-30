The following sections explain how to use QGIS-Server-Light within a docker container for development purpose.
It assumes, you are in the root of the project directory when calling the `docker` command.

### Why docker only

The worker and the exporter depend tightly on pyqgis and its native libraries. Running them against a local QGIS
installation is not supported, since the risk is too high that it breaks things in a way which is hard to track:

- the QGIS version is pinned in the image, a local QGIS in another version behaves differently
- the python version is dictated by the QGIS build, uv can't control it
- the venv needs access to the system site packages, distro packages (e.g. numpy) mix with the locked
  dependencies and may conflict
- native libraries (GDAL, PROJ, GEOS, Qt) and fonts differ per system, rendering results differ and
  the image comparing tests fail
- the local QGIS profile, plugins and environment variables (e.g. `QGIS_PREFIX_PATH`) leak in
- bugs are not reproducible across machines

!!! note
    This does not apply to the **interface** and the **dispatcher**. They don't depend on QGIS and are meant to be
    installed in 3rd party applications (see [Dev the project](dev.md#github)).

### Prepare the environment

Create an `.env` file from the provided example. Adapt as needed.

```shell
cp .env.dev.example .env
```

This tells compose to use [compose.yml](https://github.com/opengisch/qgis-server-light/blob/master/compose.yml)
extended by [compose.dev.yml](https://github.com/opengisch/qgis-server-light/blob/master/compose.dev.yml). The
composition contains the services `worker`, `exporter` and `redis`.

!!! info
    The `dev` stage is not published, it is always built locally. Published on Docker Hub
    (`opengisch/qgis-server-light`) are the worker and the exporter only: `pr-<n>` / `pr-<n>-exporter`
    follow the head of pull request `n` and are deleted when it is closed.

### Spin up QGIS-Server-Light worker

!!! info
    Either one of the following sections are meant to be executed.

#### Run the worker for development

```shell
docker compose up --watch --remove-orphans
```

This builds the `dev` image, starts redis and the worker connected to it. The source code directory is mounted
into the container so that you can change source code locally, and it is reflected transparently inside the
container.

In addition, the worker is started in reload mode. This means the worker process is restarted automatically
everytime you apply changes to the source code. Changes on the `Dockerfile` or the scripts in `docker/`
rebuild the image.

!!! note
    The pip dependencies are synced on container start. Changes on them don't need a rebuild of the image.

The geodata used in your QGIS projects is mounted into the container from the paths `LOCAL_PROJECTS` and
`LOCAL_SVGS` defined in your `.env`.

#### Run the worker in the devcontainer

The project provides a [devcontainer](https://github.com/opengisch/qgis-server-light/blob/master/.devcontainer/devcontainer.json)
which attaches your IDE to the `worker` service. Inside the devcontainer the worker is not started automatically
(`DEV_AUTOSTART=0`), so you can start it yourself, e.g. with the debugger of your IDE or with:

```shell
/usr/local/bin/dev.start.worker.sh
```

The same behaviour can be reached without devcontainer by setting `DEV_AUTOSTART=0` in your `.env`. The container
then idles and you can connect to it with the remote development features of your favourite IDE.

### Run commands inside the container

```shell
docker compose run --rm --entrypoint bash worker -c "uv run pytest"
```

!!! note
    You can configure QGIS-Server-Light differently inside you container by setting environment variables
    in your `.env` or with `-e <ENV_VAR>=<ENV_VALUE>` in the docker command. See
    [.env.dev.example](https://github.com/opengisch/qgis-server-light/blob/master/.env.dev.example) for details.
