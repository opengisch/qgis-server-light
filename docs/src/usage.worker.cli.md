
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

To get details on the parameters use:

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --help"
```
