
In order to run the worker you can start it with its CLI command.

```shell
python -m qgis_server_light.worker.redis --redis-url <your-redis-host> --svg-path <svg-paths> --data-root <data-path> --log-level <log-level>
```

To get details on the parameters use:

```shell
python -m qgis_server_light.worker.redis --help
```
