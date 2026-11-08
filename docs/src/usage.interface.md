## Job interface

Todo...

## Dispatcher

The dispatcher (`qgis_server_light.dispatcher`, installed with the extra `dispatcher`, see
[Dev the project](dev.md#github)) is what your 3rd party application uses to put jobs into the redis queue and
to get their results back. There are two of them, one for each way a worker delivers the result. Each one needs
workers booted with the matching engine (see [CLI](usage.worker.cli.md)).

### Jobs you wait for

`RedisQueue` is meant for the short living map related jobs (render, feature info, legend, feature, crs). `post`
queues the job, waits maximum `to` seconds for the result and returns it together with the status. The worker
publishes the result to the dispatcher, nothing is kept in redis afterwards. It needs workers with the `publish`
engine.

```python
from qgis_server_light.dispatcher.redis_asio import RedisQueue

queue = RedisQueue.create("redis://redis:6379")
job_result, status = await queue.post(job_parameter, to=10.0)
```

### Jobs which keep their state

`RedisStateQueue` is meant for processes, which may run for a long time. `submit` queues the job and returns right
away. The job id is given by you, so you can refer to the job later. The worker keeps the status and the result in
the job hash, which expires 24 hours after submit. Until then:

- `state` reads the current state of the job (`JobState`: status, last update, result or error message). It
  returns `None` if the job does not exist (anymore).
- `wait` waits maximum `to` seconds for the job to finish and returns its state. This is how a synchronous
  execution is done. The worker only notifies a waiting dispatcher if the job was submitted with
  `ExecutionMode.SYNC`, otherwise `wait` always runs into the timeout.
- `process_descriptions` reads the descriptions of the processes the process workers serve from the process
  registry.

It needs workers with the `state` engine.

```python
from qgis_server_light.dispatcher.redis_asio import RedisStateQueue
from qgis_server_light.interface.job.common.input import ExecutionMode

queue = RedisStateQueue.create("redis://redis:6379")
await queue.submit(job_id, job_parameter, ExecutionMode.SYNC)
job_state = await queue.wait(job_id, to=30.0)
```

The result of a succeeded process is a `ProcessResult` (the outputs and the log of the QGIS algorithm) as JSON in
`job_state.result.data`. It is parsed back with xsdata:

```python
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.job.process.output import ProcessResult

process_result = JsonParser().from_bytes(job_state.result.data, ProcessResult)
```
