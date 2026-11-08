import pickle
import socket
from unittest.mock import ANY, Mock, call

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.dispatcher.protocol import RedisProtocol
from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)
from qgis_server_light.interface.job.common.input import ExecutionMode
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.description import ProcessDescriptions
from qgis_server_light.interface.job.process.input import (
    ParameterInput,
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.worker.info import EngineInfo, QgisInfo
from qgis_server_light.interface.worker.info import Status as EngineStatus
from qgis_server_light.worker.redis import (
    DEFAULT_RUNNER_PLUGINS,
    RedisEngine,
    RedisPublishEngine,
    RedisStateEngine,
    engine_classes,
)
from qgis_server_light.worker.runner.process import ProcessRunner


class WithoutQgis:
    """Skips booting and exiting QGIS, advertising a worker only depends on the protocol
    and the engine info."""

    def __init__(self):
        self.info = EngineInfo(
            id="worker_id",
            qgis_info=QgisInfo(version=34400, version_name="3.44", path="/usr"),
            status=EngineStatus.STARTING,
            started=0.0,
        )
        self.info_expire = 300
        self.shutdown = False
        self.redis_client = None

    def __del__(self):
        pass


class RedisEngineWithoutQgis(WithoutQgis, RedisEngine):
    pass


class PublishEngineWithoutQgis(WithoutQgis, RedisPublishEngine):
    pass


class StateEngineWithoutQgis(WithoutQgis, RedisStateEngine):
    pass


@pytest.fixture
def engine():
    yield RedisEngineWithoutQgis()


@pytest.fixture
def client():
    yield Mock()


@pytest.fixture
def pipeline():
    yield Mock()


class TestRedisEngineHeartbeat:
    def test_beat_writes_full_advertisement(self, engine, client):
        last_seen = engine.heartbeat(client)

        # the beat reads nothing, it writes everything a dispatcher needs in one
        # transaction, so it heals a redis which lost all keys (restart) just the same
        # way as it renews a registered worker
        assert client.pipeline.return_value.mock_calls == [
            call.hset(
                "worker:worker_id",
                mapping={"info": ANY, "last_seen": last_seen.isoformat()},
            ),
            # the hash expires when the worker stops beating
            call.expire("worker:worker_id", 300),
            call.sadd("workers", "worker_id"),
            call.execute(),
        ]
        info_json = client.pipeline.return_value.hset.call_args.kwargs["mapping"]["info"]
        assert JsonParser().from_string(info_json, EngineInfo) == engine.info

    def test_beat_writes_current_status(self, engine, client):
        # the worker waits for a job
        engine.set_waiting()
        engine.heartbeat(client)
        info_json = client.pipeline.return_value.hset.call_args.kwargs["mapping"]["info"]
        assert JsonParser().from_string(info_json, EngineInfo).status == EngineStatus.WAITING

        # the worker took a job, the next beat tells it
        engine.set_processing()
        engine.heartbeat(client)
        info_json = client.pipeline.return_value.hset.call_args.kwargs["mapping"]["info"]
        assert JsonParser().from_string(info_json, EngineInfo).status == EngineStatus.PROCESSING


class TestRedisEngineRegisterWorker:
    def test_vanished_workers_are_pruned(self, engine, client):
        # worker-killed is still in the list, but its hash expired already
        client.smembers.return_value = {"worker-killed", "worker-alive"}
        client.exists.side_effect = lambda key: key == "worker:worker-alive"

        engine.register_worker(client)
        # only the killed worker is removed, the registering worker joins the list
        client.srem.assert_called_once_with("workers", "worker-killed")
        client.pipeline.return_value.sadd.assert_called_once_with("workers", "worker_id")


class TestRedisEngineWaitForConnection:
    def test_retries_are_counted_per_outage(self, engine, monkeypatch):
        retry_connection = Mock()
        monkeypatch.setattr(engine, "retry_connection", retry_connection)
        # a first outage, redis answers on the third ping
        client = Mock()
        client.ping.side_effect = [
            RedisConnectionError("Connection refused."),
            RedisConnectionError("Connection refused."),
            True,
        ]
        engine.wait_for_connection(client, "redis://qsl-redis:6379")
        # a second outage, redis answers on the second ping
        client.ping.side_effect = [RedisConnectionError("Connection refused."), True]
        engine.wait_for_connection(client, "redis://qsl-redis:6379")

        # the second outage counts from the beginning, the outages don't add up until
        # the worker gives up
        assert retry_connection.call_args_list == [
            call("redis://qsl-redis:6379", 1),
            call("redis://qsl-redis:6379", 2),
            call("redis://qsl-redis:6379", 1),
        ]


class TestRedisEngineServeJobs:
    def test_failed_job_is_reported_as_failed(self, engine, client, monkeypatch):
        # a render job with a point bbox is waiting in the queue
        engine.available_job_info_classes = {"QslJobInfoRender": QslJobInfoRender}
        client.blpop.return_value = ("jobs", "job_1")
        client.hget.side_effect = [
            JsonSerializer().render(
                QslJobInfoRender(
                    id="job_1",
                    type="QslJobInfoRender",
                    job=QslJobParameterRender(
                        layers=[],
                        bbox=BBox(2600000, 2600000, 1200000, 1200000),
                        crs="EPSG:2056",
                        width=256,
                        height=256,
                    ),
                )
            ),
            "QslJobInfoRender",
        ]

        # the runner fails on it, meanwhile the worker is told to stop, so this
        # stays the only job it takes
        def process(job_info):
            engine.shutdown = True
            raise RuntimeError("Invalid map settings")

        monkeypatch.setattr(engine, "process", process)
        pipeline = Mock()
        engine.serve_jobs(client, pipeline, "redis://qsl-redis:6379")

        # the job was running and is failed now, the dispatcher must not see it
        # running forever
        assert call.hset("job:job_1", "status", "running") in pipeline.mock_calls
        assert call.hset("job:job_1", "status", "failed") in pipeline.mock_calls
        assert call.hset("job:job_1", "status", "succeed") not in pipeline.mock_calls
        # the subscriber gets the reason of the failure
        channel, data = pipeline.publish.call_args.args
        assert channel == "notifications:job_1"
        assert pickle.loads(data).data == "Invalid map settings"


class TestRedisEngineCrash:
    def test_crash_in_job_loop_is_reported(self, engine, client, monkeypatch):
        # the worker is connected to a redis without other workers and no heartbeat
        # thread runs in between
        client.smembers.return_value = set()
        monkeypatch.setattr(engine, "start", Mock(return_value=client))
        monkeypatch.setattr(engine, "start_heartbeat_worker", Mock())
        # something unexpected breaks the job loop
        monkeypatch.setattr(engine, "serve_jobs", Mock(side_effect=RuntimeError("unexpected")))

        # the error is not swallowed, the worker still goes down with it
        with pytest.raises(RuntimeError, match="unexpected"):
            engine.run("redis://qsl-redis:6379")
        # but its last beat tells redis that it crashed
        info_json = client.pipeline.return_value.hset.call_args.kwargs["mapping"]["info"]
        assert JsonParser().from_string(info_json, EngineInfo).status == EngineStatus.CRASHED

    def test_exit_is_no_crash(self, engine, client, monkeypatch):
        client.smembers.return_value = set()
        monkeypatch.setattr(engine, "start", Mock(return_value=client))
        monkeypatch.setattr(engine, "start_heartbeat_worker", Mock())
        # the worker gives up on redis or got a signal, both exit on purpose
        monkeypatch.setattr(engine, "serve_jobs", Mock(side_effect=SystemExit(404)))

        with pytest.raises(SystemExit):
            engine.run("redis://qsl-redis:6379")
        # the last beat is still the one from registering
        info_json = client.pipeline.return_value.hset.call_args.kwargs["mapping"]["info"]
        assert JsonParser().from_string(info_json, EngineInfo).status == EngineStatus.STARTING

    def test_crash_report_without_redis_is_only_logged(self, engine, client, caplog):
        # redis is gone as well, the original error must not be covered by a redis one
        client.pipeline.return_value.execute.side_effect = RedisConnectionError(
            "Error 111 connecting to qsl-redis:6379. Connection refused."
        )
        engine.report_crash(client)
        assert engine.info.status == EngineStatus.CRASHED
        assert "Crash could not be reported to Redis" in caplog.text


class TestEngineQueues:
    """The queue a worker listens on follows from the protocol of its engine."""

    @pytest.mark.parametrize(
        "engine_class,expected",
        [
            (RedisPublishEngine, "jobs"),
            (RedisStateEngine, "jobs:process"),
        ],
    )
    def test_queue_name(self, engine_class, expected):
        assert engine_class.protocol.queue_name() == expected

    @pytest.mark.parametrize(
        "engine_name,expected",
        [
            ("publish", RedisPublishEngine),
            ("state", RedisStateEngine),
        ],
    )
    def test_engine_classes(self, engine_name, expected):
        assert engine_classes[engine_name] is expected

    def test_default_runner_plugins_without_process(self):
        assert "ProcessRunner" not in DEFAULT_RUNNER_PLUGINS


class TestWriteProcessRegistry:
    """A process-worker writes the descriptions of its processes into the registry once."""

    def test_write(self, qgis_app, client):
        process_descriptions = ProcessRunner.info(qgis_app, ["native:centroids"])
        # the registry is still empty
        client.set.return_value = True
        assert RedisEngine.write_process_registry(client, process_descriptions)
        # the descriptions are written only if no other worker did it already
        assert client.set.call_args.args[0] == "processes"
        assert client.set.call_args.kwargs == {"nx": True}
        registry_json = client.set.call_args.args[1]
        assert JsonParser().from_string(registry_json, ProcessDescriptions) == process_descriptions

    def test_second_write_keeps_entry(self, qgis_app, client):
        # another worker wrote the registry already, redis refuses to set it again
        client.set.return_value = None
        assert not RedisEngine.write_process_registry(
            client, ProcessRunner.info(qgis_app, ["native:buffer"])
        )


class TestRedisStateEngine:
    """The state engine keeps the result in the job hash, expiring with the final status
    in one transaction, and only notifies a waiting dispatcher afterwards."""

    @pytest.fixture
    def engine(self):
        yield StateEngineWithoutQgis()

    @pytest.mark.parametrize(
        "job_info,expected",
        [
            (
                QslJobInfoExecuteProcess(
                    id="my_cool_id",
                    type="QslJobInfoExecuteProcess",
                    job=QslJobParameterExecuteProcess(
                        process_id="native:centroids",
                        parameters=[ParameterInput("ALL_PARTS", False)],
                    ),
                    execution_mode=ExecutionMode.SYNC,
                ),
                [
                    call.hset("job:my_cool_id", "result", b'{"outputs": [], "log": ""}'),
                    call.hset(
                        "job:my_cool_id",
                        "result_content_type",
                        "application/qgis-server-light.interface.job.process.ProcessResult",
                    ),
                    call.expire("job:my_cool_id", 86400),
                    call.hset("job:my_cool_id", "status", "succeed"),
                    call.hset("job:my_cool_id", "timestamp.succeed", ANY),
                    call.hset("job:my_cool_id", "timestamp.last_update", ANY),
                    call.hset("job:my_cool_id", "duration", ANY),
                    call.execute(),
                    call.publish("notifications:my_cool_id", "succeed"),
                ],
            ),
            (
                QslJobInfoExecuteProcess(
                    id="my_cool_id",
                    type="QslJobInfoExecuteProcess",
                    job=QslJobParameterExecuteProcess(
                        process_id="native:centroids",
                        parameters=[ParameterInput("ALL_PARTS", False)],
                    ),
                    execution_mode=ExecutionMode.ASYNC,
                ),
                [
                    call.hset("job:my_cool_id", "result", b'{"outputs": [], "log": ""}'),
                    call.hset(
                        "job:my_cool_id",
                        "result_content_type",
                        "application/qgis-server-light.interface.job.process.ProcessResult",
                    ),
                    call.expire("job:my_cool_id", 86400),
                    call.hset("job:my_cool_id", "status", "succeed"),
                    call.hset("job:my_cool_id", "timestamp.succeed", ANY),
                    call.hset("job:my_cool_id", "timestamp.last_update", ANY),
                    call.hset("job:my_cool_id", "duration", ANY),
                    call.execute(),
                ],
            ),
        ],
    )
    def test_succeed_job(self, engine, pipeline, job_info, expected):
        result = JobResult(
            id="my_cool_id",
            data=b'{"outputs": [], "log": ""}',
            content_type="application/qgis-server-light.interface.job.process.ProcessResult",
        )
        engine.succeed_job("my_cool_id", job_info, result, pipeline, 0.0)
        assert pipeline.mock_calls == expected

    @pytest.mark.parametrize(
        "job_info,expected",
        [
            (
                QslJobInfoExecuteProcess(
                    id="my_cool_id",
                    type="QslJobInfoExecuteProcess",
                    job=QslJobParameterExecuteProcess(
                        process_id="native:centroids",
                        parameters=[ParameterInput("ALL_PARTS", False)],
                    ),
                    execution_mode=ExecutionMode.SYNC,
                ),
                [
                    call.hset("job:my_cool_id", "message", "Algorithm failed"),
                    call.expire("job:my_cool_id", 86400),
                    call.hset("job:my_cool_id", "status", "failed"),
                    call.hset("job:my_cool_id", "timestamp.failed", ANY),
                    call.hset("job:my_cool_id", "timestamp.last_update", ANY),
                    call.hset("job:my_cool_id", "duration", ANY),
                    call.execute(),
                    call.publish("notifications:my_cool_id", "failed"),
                ],
            ),
            (
                QslJobInfoExecuteProcess(
                    id="my_cool_id",
                    type="QslJobInfoExecuteProcess",
                    job=QslJobParameterExecuteProcess(
                        process_id="native:centroids",
                        parameters=[ParameterInput("ALL_PARTS", False)],
                    ),
                    execution_mode=ExecutionMode.ASYNC,
                ),
                [
                    call.hset("job:my_cool_id", "message", "Algorithm failed"),
                    call.expire("job:my_cool_id", 86400),
                    call.hset("job:my_cool_id", "status", "failed"),
                    call.hset("job:my_cool_id", "timestamp.failed", ANY),
                    call.hset("job:my_cool_id", "timestamp.last_update", ANY),
                    call.hset("job:my_cool_id", "duration", ANY),
                    call.execute(),
                ],
            ),
        ],
    )
    def test_fail_job(self, engine, pipeline, job_info, expected):
        engine.fail_job("my_cool_id", job_info, RuntimeError("Algorithm failed"), pipeline, 0.0)
        assert pipeline.mock_calls == expected

    def test_fail_job_without_job_info(self, engine, pipeline):
        """The job info was not readable, a waiting dispatcher must not miss the end."""
        engine.fail_job("my_cool_id", None, RuntimeError("Algorithm failed"), pipeline, 0.0)
        assert pipeline.mock_calls == [
            call.hset("job:my_cool_id", "message", "Algorithm failed"),
            call.expire("job:my_cool_id", 86400),
            call.hset("job:my_cool_id", "status", "failed"),
            call.hset("job:my_cool_id", "timestamp.failed", ANY),
            call.hset("job:my_cool_id", "timestamp.last_update", ANY),
            call.hset("job:my_cool_id", "duration", ANY),
            call.execute(),
            call.publish("notifications:my_cool_id", "failed"),
        ]


class TestRedisPublishEngine:
    """The publish engine publishes the pickled result after the final status and keeps
    neither result fields nor an expiry in the job hash."""

    @pytest.fixture
    def engine(self):
        yield PublishEngineWithoutQgis()

    @pytest.mark.parametrize(
        "result,expected_published_result",
        [
            (
                JobResult(id="my_cool_id", data=b"png", content_type="image/png"),
                JobResult(
                    id="my_cool_id",
                    data=b"png",
                    content_type="image/png",
                    worker_id="worker_id",
                    worker_host_name=socket.gethostname(),
                ),
            )
        ],
    )
    def test_succeed_job(self, engine, pipeline, result, expected_published_result):
        engine.succeed_job("my_cool_id", None, result, pipeline, 0.0)
        assert pipeline.mock_calls == [
            call.hset("job:my_cool_id", "status", "succeed"),
            call.hset("job:my_cool_id", "timestamp.succeed", ANY),
            call.hset("job:my_cool_id", "timestamp.last_update", ANY),
            call.hset("job:my_cool_id", "duration", ANY),
            call.execute(),
            call.publish("notifications:my_cool_id", pickle.dumps(expected_published_result)),
        ]

    @pytest.mark.parametrize(
        "expected_published_result",
        [
            JobResult(
                id="my_cool_id",
                data="Layer not found",
                content_type="text",
                worker_id="worker_id",
                worker_host_name=socket.gethostname(),
            )
        ],
    )
    def test_fail_job(self, engine, pipeline, expected_published_result):
        engine.fail_job("my_cool_id", None, RuntimeError("Layer not found"), pipeline, 0.0)
        assert pipeline.mock_calls == [
            call.hset("job:my_cool_id", "status", "failed"),
            call.hset("job:my_cool_id", "timestamp.failed", ANY),
            call.hset("job:my_cool_id", "timestamp.last_update", ANY),
            call.hset("job:my_cool_id", "duration", ANY),
            call.execute(),
            call.publish("notifications:my_cool_id", pickle.dumps(expected_published_result)),
        ]
