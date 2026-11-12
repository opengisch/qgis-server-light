Every worker registers itself in redis and keeps telling it that it is alive.
Applications which queue jobs,
can use this to check whether jobs can be served at all, for example in a health check.

### What a worker writes to redis

| Key           | Type | Content                                                                                        |
|---------------|------|------------------------------------------------------------------------------------------------|
| `workers`     | set  | The ids of the registered workers.                                                             |
| `worker:{id}` | hash | Field `info`: the engine info as JSON, including the current status. Field `last_seen`: UTC timestamp of the last heartbeat. |

- On start the worker removes stale ids from `workers` and sends its first heartbeat.
- Every second (`RedisProtocol.worker_heartbeat_interval`) the heartbeat writes everything
  again: the `info` with the current status, `last_seen`, the expiry of the hash
  (300 seconds) and the id in `workers`. If redis loses its keys (a restart, a flush or an
  eviction), the workers are back within one second, without being restarted.
- The status in `info` tells what the worker is doing: `starting`, `waiting` (for a job),
  `processing` (a job) or `crashed`.
- If the job loop of a worker breaks with an unexpected error, the worker sets its status
  to `crashed` and sends one more heartbeat before it exits.
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

# the workers with a heartbeat younger than RedisProtocol.worker_alive_age (10 seconds),
# which did not crash
for worker in await queue.alive_workers():
    print(worker.id, worker.last_seen, worker.info.status)

# every worker redis still knows, also crashed ones and ones which stopped beating
for worker in await queue.registered_workers():
    print(worker.id, worker.last_seen, worker.info.status)
```

Both return `Worker` dataclasses (`qgis_server_light.interface.dispatcher.common`) sorted
by id. Next to the id and `last_seen`, each one carries the engine info of its last
heartbeat (status, QGIS version, start time).

- `alive_workers` answers whether jobs can be served. Workers which stopped beating or
  crashed are left out.
- `registered_workers` is meant for showing the state of all workers, for example a crashed
  one. A worker stays in there until its hash expires, 300 seconds after its last heartbeat.

!!! note
`is_reachable` has no timeout of its own. If the connection to redis may hang, limit the
call on your side,
e.g. with `asyncio.wait_for`.
