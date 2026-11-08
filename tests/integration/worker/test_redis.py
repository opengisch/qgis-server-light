import pickle
import socket
from unittest.mock import ANY

import pytest
from xsdata.formats.dataclass.parsers import JsonParser

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


class FakeRedisClient:
    def __init__(self):
        self.values = {}

    def set(self, key, value, nx):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True


class TestWriteProcessRegistry:
    """A process-worker writes the descriptions of its processes into the registry once."""

    @pytest.fixture
    def client(self):
        yield FakeRedisClient()

    def test_write(self, qgis_app, client):
        process_descriptions = ProcessRunner.info(qgis_app, ["native:centroids"])
        assert RedisEngine.write_process_registry(client, process_descriptions)
        registry_json = client.values["processes"]
        assert JsonParser().from_string(registry_json, ProcessDescriptions) == process_descriptions

    def test_second_write_keeps_entry(self, qgis_app, client):
        centroids_descriptions = ProcessRunner.info(qgis_app, ["native:centroids"])
        RedisEngine.write_process_registry(client, centroids_descriptions)
        assert not RedisEngine.write_process_registry(
            client, ProcessRunner.info(qgis_app, ["native:buffer"])
        )
        registry_json = client.values["processes"]
        assert JsonParser().from_string(registry_json, ProcessDescriptions) == (
            centroids_descriptions
        )


class WithoutQgis:
    """Skips booting and exiting QGIS, finishing a job only depends on the protocol
    and the engine info."""

    def __init__(self):
        self.info = EngineInfo(
            id="worker_id",
            qgis_info=QgisInfo(version=34400, version_name="3.44", path="/usr"),
            status=EngineStatus.WAITING,
            started=0.0,
        )

    def __del__(self):
        pass


class PublishEngineWithoutQgis(WithoutQgis, RedisPublishEngine):
    pass


class StateEngineWithoutQgis(WithoutQgis, RedisStateEngine):
    pass


class FakePipeline:
    """Records every call in order, so a test can compare them with the calls it expects."""

    def __init__(self):
        self.calls = []

    def hset(self, key, field, value):
        self.calls.append(("hset", key, field, value))

    def expire(self, name, seconds):
        self.calls.append(("expire", name, seconds))

    def publish(self, channel, message):
        self.calls.append(("publish", channel, message))

    def execute(self):
        self.calls.append(("execute",))


@pytest.fixture
def pipeline():
    yield FakePipeline()


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
                    ("hset", "job:my_cool_id", "result", b'{"outputs": [], "log": ""}'),
                    (
                        "hset",
                        "job:my_cool_id",
                        "result_content_type",
                        "application/qgis-server-light.interface.job.process.ProcessResult",
                    ),
                    ("expire", "job:my_cool_id", 86400),
                    ("hset", "job:my_cool_id", "status", "succeed"),
                    ("hset", "job:my_cool_id", "timestamp.succeed", ANY),
                    ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
                    ("hset", "job:my_cool_id", "duration", ANY),
                    ("execute",),
                    ("publish", "notifications:my_cool_id", "succeed"),
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
                    ("hset", "job:my_cool_id", "result", b'{"outputs": [], "log": ""}'),
                    (
                        "hset",
                        "job:my_cool_id",
                        "result_content_type",
                        "application/qgis-server-light.interface.job.process.ProcessResult",
                    ),
                    ("expire", "job:my_cool_id", 86400),
                    ("hset", "job:my_cool_id", "status", "succeed"),
                    ("hset", "job:my_cool_id", "timestamp.succeed", ANY),
                    ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
                    ("hset", "job:my_cool_id", "duration", ANY),
                    ("execute",),
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
        assert pipeline.calls == expected

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
                    ("hset", "job:my_cool_id", "message", "Algorithm failed"),
                    ("expire", "job:my_cool_id", 86400),
                    ("hset", "job:my_cool_id", "status", "failed"),
                    ("hset", "job:my_cool_id", "timestamp.failed", ANY),
                    ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
                    ("hset", "job:my_cool_id", "duration", ANY),
                    ("execute",),
                    ("publish", "notifications:my_cool_id", "failed"),
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
                    ("hset", "job:my_cool_id", "message", "Algorithm failed"),
                    ("expire", "job:my_cool_id", 86400),
                    ("hset", "job:my_cool_id", "status", "failed"),
                    ("hset", "job:my_cool_id", "timestamp.failed", ANY),
                    ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
                    ("hset", "job:my_cool_id", "duration", ANY),
                    ("execute",),
                ],
            ),
        ],
    )
    def test_fail_job(self, engine, pipeline, job_info, expected):
        engine.fail_job("my_cool_id", job_info, RuntimeError("Algorithm failed"), pipeline, 0.0)
        assert pipeline.calls == expected

    def test_fail_job_without_job_info(self, engine, pipeline):
        """The job info was not readable, a waiting dispatcher must not miss the end."""
        engine.fail_job("my_cool_id", None, RuntimeError("Algorithm failed"), pipeline, 0.0)
        assert pipeline.calls == [
            ("hset", "job:my_cool_id", "message", "Algorithm failed"),
            ("expire", "job:my_cool_id", 86400),
            ("hset", "job:my_cool_id", "status", "failed"),
            ("hset", "job:my_cool_id", "timestamp.failed", ANY),
            ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
            ("hset", "job:my_cool_id", "duration", ANY),
            ("execute",),
            ("publish", "notifications:my_cool_id", "failed"),
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
        assert pipeline.calls == [
            ("hset", "job:my_cool_id", "status", "succeed"),
            ("hset", "job:my_cool_id", "timestamp.succeed", ANY),
            ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
            ("hset", "job:my_cool_id", "duration", ANY),
            ("execute",),
            ("publish", "notifications:my_cool_id", pickle.dumps(expected_published_result)),
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
        assert pipeline.calls == [
            ("hset", "job:my_cool_id", "status", "failed"),
            ("hset", "job:my_cool_id", "timestamp.failed", ANY),
            ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
            ("hset", "job:my_cool_id", "duration", ANY),
            ("execute",),
            ("publish", "notifications:my_cool_id", pickle.dumps(expected_published_result)),
        ]
