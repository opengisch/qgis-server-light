## Prepare to run an instance of QGIS-Server-Light

QGIS-Server-Light is developed and run in docker only (docker need to be installed in a recent version). See
[why docker only](usage.worker.docker.md#why-docker-only).

### Run it with Docker Compose

Create an .env file and put the content of [.env.dev.example](https://github.com/opengisch/qgis-server-light/blob/master/.env.dev.example)
into it. Adapt as needed.

```shell
cp .env.dev.example .env
docker compose up --watch --remove-orphans
```

- `LOCAL_PROJECTS` has to be the valid local path where your qgis projects (and their data) are stored
- `LOCAL_SVGS` has to be the valid local path where your additional svg files are stored
- Optional: `QSL_LOG_LEVEL` log levels as they are defined by pythons
  [logging](https://docs.python.org/3/library/logging.html#logging-levels) library
- Optional: `REPLICAS` can be 1 up to * (note, that this has to be balanced with your system resources)
- Optional: `DEV_AUTOSTART` start the worker on container start (1) or just idle (0)

Congratulations... Your QGIS-Server-Light is running and waits for jobs in the redis queue.

See [Docker-DEV](usage.worker.docker.md) for details and the devcontainer.


## DEV Details

### Running things

All deps are transparent. The biggest one is QGIS and its relatives of course. The source code is mounted
to the running container, that way the current changes you make are transparently available in the container.

Tests, linting and docs are run inside the container too:

```shell
docker compose run --rm --entrypoint bash worker -c "uv run pytest"
docker compose run --rm --entrypoint bash worker -c "uv run ruff check"
docker compose run --rm --entrypoint bash worker -c "uv run mkdocs build -f docs/mkdocs.yml -d site"
```

For better IDE support it is to be mentioned that the python interpreter inside the container with access
to all the necessary python libs is available at `/home/appuser/.venv/bin/python`. The provided
devcontainer is already configured to use it.

### PyPi Dependencies

If you decide to add new requirements to this project, please consider for which part of the project
you need them. Remember, it's split into 3 parts, each one has its own dependency group in
[pyproject.toml](https://github.com/opengisch/qgis-server-light/blob/master/pyproject.toml):
- exporter (`exporter`)
- interface (`interface`)
- worker (`worker`)

```shell
docker compose run --rm --entrypoint bash worker -c "uv add --group worker <package>"
```

In general its save to add dependencies to **exporter** and **worker** since they are used only in this project.
The **interface** should have as fewer dependencies as possible and should implement only the minimal
understanding of items to be passed around with third party applications through redis. The main goal of all
this is to keep the 3rd party application clean of heavy deps.

Dependencies of the **interface** and the **dispatcher** have to be added to the extras in
`[project.optional-dependencies]` too, since these are the ones 3rd party applications install.

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

If your application posts jobs to the redis queue with the dispatcher (`qgis_server_light.dispatcher`),
install it with the extra `dispatcher`. It adds the dependencies of the dispatcher (`redis`, `xsdata`).
The interface alone has no dependencies.

```requirements
qgis_server_light[dispatcher] @ git+ssh://git@github.com/opengisch/qgis-server-light.git@master
```

### Release

Releases are cut from `master` only and go forward only, there are no maintenance branches.
A fix, also a security fix, is a regular PR and goes out with the next release.

Versions are calendar style `vYY.N`, `N` counting up within the year from `0` (`v26.1`, `v26.2`, …,
`v27.0`). The number carries no compatibility promise.

To release, tag the `master` commit and push the tag:

```shell
git switch master
git pull
git tag v26.1
git push origin v26.1
```

The tag triggers the workflow [release.yml](https://github.com/opengisch/qgis-server-light/blob/master/.github/workflows/release.yml):

- fails if the tagged commit is not reachable from `master`
- sets the package version from the tag (`26.1`), not committed
- builds and pushes `opengisch/qgis-server-light:26.1-worker` / `26.1-exporter` and moves
  `latest-worker` / `latest-exporter`
- creates the GitHub release, the notes list the PRs merged since the previous tag, grouped by label
  (see [release.yml](https://github.com/opengisch/qgis-server-light/blob/master/.github/release.yml))

The `version` in `pyproject.toml` is a placeholder (`0.0.0`). Only images built by the workflow carry
the real version, an install from git reports `0.0.0`.
