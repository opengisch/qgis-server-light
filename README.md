# Commands

```shell
docker compose up --watch --remove-orphans
```

```shell
docker compose run --rm --entrypoint bash qsl -c "uv run pytest"
```

```shell
docker compose run --rm --entrypoint bash qsl -c "uv run mkdocs build -f docs/mkdocs.yml -d site"
```

## DEV

The provided compose does offer a virtual environment inside the
qsl service container. You may want to use this with your IDE for
code completion. It's located inside the container at `/home/appuser/.venv`.

Either you use the container directly or the ssh which is
running in qsl service for this purpose.
