# Commands

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
