
In order to run the worker you can start it with its CLI command inside the container (see
[Docker-DEV](usage.worker.docker.md)).

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --redis-url <your-redis-host> --svg-path <svg-paths> --data-root <data-path> --log-level <log-level>"
```

The runner plugins the worker boots with decide which jobs it solves and on which queues it listens. By default
it boots with the map related runners and listens on `jobs`. A worker serving processes boots with the process
runner only and listens on `jobs:process`, so long-running processes never block map rendering:

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --redis-url <your-redis-host> --svg-path <svg-paths> --data-root <data-path> --log-level <log-level> --runner-plugins qgis_server_light.worker.runner.process.ProcessRunner"
```

Which QGIS algorithms a process worker serves is limited by `--process-allowlist` (`,`-separated algorithm ids,
env `QSL_PROCESS_ALLOWLIST` in the docker boot scripts). On boot the worker writes the descriptions of these
processes into the process registry in redis (key `processes`), unless the key exists already. Since the key is
not overwritten, it has to be deleted after the allowlist was changed.

To get details on the parameters use:

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --help"
```
