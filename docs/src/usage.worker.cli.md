
In order to run the worker you can start it with its CLI command inside the container (see
[Docker-DEV](usage.worker.docker.md)).

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --redis-url <your-redis-host> --svg-path <svg-paths> --data-root <data-path> --log-level <log-level>"
```

The engine the worker boots with (`--engine`, env `QSL_ENGINE` in the docker boot scripts) decides how it
delivers the results and on which queue it listens:

- `publish` (default) listens on `jobs`. The worker publishes the result to the waiting dispatcher, the job is
  removed from redis afterwards. This is what the map related jobs need.
- `state` listens on `jobs:process`. The worker keeps the status and the result in the job hash, so they can be
  read at any time until the hash expires (24 hours after submit). This is what processes need.

The runner plugins the worker boots with (`--runner-plugins`, env `QSL_RUNNER_PLUGINS`) decide which jobs it
solves. By default it boots with the map related runners. A worker serving processes boots with the state engine
and the process runner only, so long-running processes never block map rendering:

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --redis-url <your-redis-host> --svg-path <svg-paths> --data-root <data-path> --log-level <log-level> --engine state --runner-plugins qgis_server_light.worker.runner.process.ProcessRunner"
```

Which QGIS algorithms a process worker serves is limited by `--process-allowlist` (`,`-separated algorithm ids,
env `QSL_PROCESS_ALLOWLIST` in the docker boot scripts). On boot the worker writes the descriptions of these
processes into the process registry in redis (key `processes`), unless the key exists already. Since the key is
not overwritten, it has to be deleted after the allowlist was changed.

The file outputs of the processes are written by the worker itself, the client can't choose where they go. Every
job writes into its own dir `{process-output-dir}/{job_id}`, each file is named after its output
(e.g. `OUTPUT.geojson`). The client chooses the format of each file output among the media types the process
description offers for it (vector layers: GeoJSON, GeoPackage, FlatGeobuf; raster layers: GeoTIFF; reports: HTML),
without a
choice the first one is used. Vector layers default to GeoJSON because it takes any data: a GeoPackage takes an
input attribute `fid` as its feature id and the job fails if its values are not unique, FlatGeobuf refuses
features without geometry. The dir is set by
`--process-output-dir` (env `QSL_PROCESS_OUTPUT_DIR` in the docker boot scripts, default `/io/process_output`).
If a job fails, its dir is removed, so only succeeded jobs leave files behind. Outputs which are not written to a
file (e.g. numbers or strings) are part of the result directly.

To get details on the parameters use:

```shell
docker compose run --rm --entrypoint bash worker -c "uv run python -m qgis_server_light.worker.redis --help"
```
