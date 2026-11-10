Every worker registers itself in redis and keeps telling it that it is alive.
Applications which queue jobs,
can use this to check whether jobs can be served at all, for example in a health check.

### What a worker writes to redis

| Key           | Type | Content                                                                                        |
|---------------|------|------------------------------------------------------------------------------------------------|
| `workers`     | set  | The ids of the registered workers.                                                             |
| `worker:{id}` | hash | Field `info`: the engine info as JSON. Field `last_seen`: UTC timestamp of the last heartbeat. |

- On start the worker adds its id to `workers` and writes its `worker:{id}` hash.
- Every second (`RedisProtocol.worker_heartbeat_interval`) it writes `last_seen` and
  renews the expiry of its
  hash (300 seconds).
- On a graceful shutdown (`SIGTERM`, `SIGINT`) it removes its id and its hash.
- A worker which is killed can't clean up. Its hash expires and the next starting worker
  removes the stale id from
  `workers`.

The key and field names are defined in `RedisProtocol`
(`qgis_server_light.interface.dispatcher.protocol`), so
nobody needs to repeat them.

### Asking the dispatcher

The dispatcher reads this for you, no redis knowledge is needed on the consuming side:

```python
from qgis_server_light.dispatcher.redis_asio import RedisQueue

queue = RedisQueue.create("redis://qsl-redis:6379")

# True if redis answered, redis exceptions are logged and not raised
reachable = await queue.is_reachable()

# the workers with a heartbeat younger than RedisProtocol.worker_alive_age (10 seconds)
for worker in await queue.alive_workers():
    print(worker.id, worker.last_seen)
```

`alive_workers` returns `Worker` dataclasses
(`qgis_server_light.interface.dispatcher.common`) sorted by id.
Workers which are registered but stopped beating are left out.

!!! note
`is_reachable` has no timeout of its own. If the connection to redis may hang, limit the
call on your side,
e.g. with `asyncio.wait_for`.
