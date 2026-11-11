import asyncio
import pickle
from unittest.mock import ANY

import pytest
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.dispatcher import redis_asio
from qgis_server_light.dispatcher.redis_asio import RedisQueue, RedisStateQueue
from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.dispatcher.common import JobState, Status
from qgis_server_light.interface.job.common.input import ExecutionMode, QslJobParameter
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.crs.input import QslJobInfoCrs, QslJobParameterCrs
from qgis_server_light.interface.job.feature.input import (
    QslJobInfoFeature,
    QslJobParameterFeature,
)
from qgis_server_light.interface.job.feature_info.input import (
    QslJobInfoFeatureInfo,
    QslJobParameterFeatureInfo,
)
from qgis_server_light.interface.job.legend.input import (
    QslJobInfoLegend,
    QslJobParameterLegend,
)
from qgis_server_light.interface.job.process.description import (
    InputDescription,
    ProcessDescription,
    ProcessDescriptions,
    Schema,
)
from qgis_server_light.interface.job.process.input import (
    ParameterInput,
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)


class TestDeriveJobInfo:
    @pytest.mark.parametrize(
        "job_parameter,expected_class",
        [
            (
                QslJobParameterRender(
                    layers=[],
                    bbox=BBox(x_min=0.0, x_max=1.0, y_min=0.0, y_max=1.0),
                    crs="EPSG:2056",
                    width=256,
                    height=256,
                ),
                QslJobInfoRender,
            ),
            (
                QslJobParameterFeatureInfo(
                    INFO_FORMAT="application/json", QUERY_LAYERS="a", I="1", J="1"
                ),
                QslJobInfoFeatureInfo,
            ),
            (QslJobParameterLegend(layers=[]), QslJobInfoLegend),
            (QslJobParameterFeature(queries=[]), QslJobInfoFeature),
        ],
    )
    def test_supported(self, job_parameter, expected_class):
        job_info = RedisQueue.derive_job_info("my_cool_id", job_parameter)
        assert isinstance(job_info, expected_class)
        assert job_info.id == "my_cool_id"
        assert job_info.type == expected_class.__name__
        assert job_info.job is job_parameter

    def test_unsupported(self):
        with pytest.raises(TypeError, match="Unsupported runner type"):
            RedisQueue.derive_job_info("blabla", QslJobParameter())


class FakePipeline:
    """Records the calls of a transaction into the call log of the client."""

    def __init__(self, calls: list):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def hset(self, key, field, value):
        self.calls.append(("hset", key, field, value))

    async def rpush(self, name, value):
        self.calls.append(("rpush", name, value))

    async def expire(self, name, seconds):
        self.calls.append(("expire", name, seconds))

    async def execute(self):
        self.calls.append(("execute",))


class FakePubSub:
    """Delivers the given message, or nothing until the timeout if there is none, like a
    worker which does not finish in time."""

    def __init__(self, calls: list, message: dict | None):
        self.calls = calls
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def subscribe(self, channel):
        self.calls.append(("subscribe", channel))

    async def get_message(self, timeout, ignore_subscribe_messages):
        if self.message is None:
            await asyncio.sleep(timeout)
        return self.message


class FakeRedisClient:
    """Records every call in order, so a test can compare them with the calls it expects.

    Each read of a job hash takes the next one of `job_hashes`, like a worker changing
    the job in between two reads.
    """

    def __init__(self, values: dict, job_hashes: list[dict], message: dict | None):
        self.calls = []
        self.values = values
        self.job_hashes = job_hashes
        self.message = message

    def pipeline(self):
        return FakePipeline(self.calls)

    def pubsub(self):
        return FakePubSub(self.calls, self.message)

    async def get(self, key):
        return self.values.get(key)

    async def hget(self, key, field):
        self.calls.append(("hget", key, field))
        return self.job_hashes.pop(0)[field.encode()]

    async def hgetall(self, key):
        self.calls.append(("hgetall", key))
        return self.job_hashes.pop(0)

    async def delete(self, key):
        self.calls.append(("delete", key))


class TestRedisQueue:
    def test_protocol(self):
        assert RedisQueue.job_queue_name == "jobs"
        assert RedisQueue.job_key("my_cool_id") == "job:my_cool_id"
        assert RedisQueue.channel("my_cool_id") == "notifications:my_cool_id"

    @pytest.mark.parametrize(
        "job_parameter,job_info",
        [
            (
                QslJobParameterLegend(layers=[]),
                QslJobInfoLegend(
                    id="my_cool_id",
                    type="QslJobInfoLegend",
                    job=QslJobParameterLegend(layers=[]),
                ),
            ),
            (
                QslJobParameterCrs(identifiers=["EPSG:2056"]),
                QslJobInfoCrs(
                    id="my_cool_id",
                    type="QslJobInfoCrs",
                    job=QslJobParameterCrs(identifiers=["EPSG:2056"]),
                ),
            ),
        ],
    )
    def test_post_calls(self, monkeypatch, job_parameter, job_info):
        """Subscribes before queuing, queues with the queued status in one transaction
        on the publish queue and deletes the job hash in the end."""
        # `post` generates the job id, it is fixed so the expected calls can name it
        monkeypatch.setattr(redis_asio, "uuid4", lambda: "my_cool_id")
        client = FakeRedisClient(
            values={},
            job_hashes=[{b"status": b"succeed"}],
            message={
                "data": pickle.dumps(
                    JobResult(id="my_cool_id", data=b"png", content_type="image/png")
                )
            },
        )
        asyncio.run(RedisQueue(client).post(job_parameter))
        assert client.calls == [
            ("subscribe", "notifications:my_cool_id"),
            ("hset", "job:my_cool_id", "info", JsonSerializer().render(job_info)),
            ("hset", "job:my_cool_id", "info_type", job_info.type),
            ("hset", "job:my_cool_id", "status", "queued"),
            ("hset", "job:my_cool_id", "timestamp.queued", ANY),
            ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
            ("hset", "job:my_cool_id", "duration", ANY),
            ("rpush", "jobs", "my_cool_id"),
            ("execute",),
            ("hget", "job:my_cool_id", "status"),
            ("delete", "job:my_cool_id"),
        ]

    @pytest.mark.parametrize(
        "job_hashes,message,expected",
        [
            (
                [{b"status": b"succeed"}],
                {
                    "data": pickle.dumps(
                        JobResult(id="my_cool_id", data=b"png", content_type="image/png")
                    )
                },
                (JobResult(id="my_cool_id", data=b"png", content_type="image/png"), "succeed"),
            ),
            (
                [{b"status": b"failed"}],
                {
                    "data": pickle.dumps(
                        JobResult(id="my_cool_id", data="Layer not found", content_type="text")
                    )
                },
                (
                    JobResult(id="my_cool_id", data="Layer not found", content_type="text"),
                    "failed",
                ),
            ),
        ],
    )
    def test_post_returns_published_result(self, job_hashes, message, expected):
        client = FakeRedisClient(values={}, job_hashes=job_hashes, message=message)
        job_parameter = QslJobParameterLegend(layers=[])
        assert asyncio.run(RedisQueue(client).post(job_parameter)) == expected


class TestProcessRegistry:
    def test_protocol(self):
        assert RedisStateQueue.process_registry_key == "processes"

    def test_process_descriptions_empty_without_registry(self):
        client = FakeRedisClient(values={}, job_hashes=[], message=None)
        assert asyncio.run(RedisStateQueue(client).process_descriptions()) == ProcessDescriptions()

    @pytest.mark.parametrize(
        "values,expected",
        [
            (
                {
                    "processes": (
                        b'{"processes": [{"id": "native:centroids", "title": "Centroids", '
                        b'"inputs": [{"id": "ALL_PARTS", "title": "Create centroid for each '
                        b'part", "schema": {"type": "boolean", "default": false}, '
                        b'"minOccurs": 1, "maxOccurs": 1}], "outputs": []}]}'
                    )
                },
                ProcessDescriptions(
                    processes=[
                        ProcessDescription(
                            id="native:centroids",
                            title="Centroids",
                            inputs=[
                                InputDescription(
                                    id="ALL_PARTS",
                                    title="Create centroid for each part",
                                    schema=Schema(type="boolean", default=False),
                                )
                            ],
                        )
                    ]
                ),
            )
        ],
    )
    def test_process_descriptions(self, values, expected):
        client = FakeRedisClient(values=values, job_hashes=[], message=None)
        assert asyncio.run(RedisStateQueue(client).process_descriptions()) == expected


class TestRedisStateQueue:
    def test_protocol(self):
        assert RedisStateQueue.job_queue_name == "jobs:process"
        assert RedisStateQueue.job_key("my_cool_id") == "job:my_cool_id"
        assert RedisStateQueue.channel("my_cool_id") == "notifications:my_cool_id"

    @pytest.mark.parametrize(
        "execution_mode,job_info",
        [
            (
                ExecutionMode.SYNC,
                QslJobInfoExecuteProcess(
                    id="my_cool_id",
                    type="QslJobInfoExecuteProcess",
                    job=QslJobParameterExecuteProcess(
                        process_id="native:centroids",
                        parameters=[ParameterInput("ALL_PARTS", False)],
                    ),
                    execution_mode=ExecutionMode.SYNC,
                ),
            ),
            (
                ExecutionMode.ASYNC,
                QslJobInfoExecuteProcess(
                    id="my_cool_id",
                    type="QslJobInfoExecuteProcess",
                    job=QslJobParameterExecuteProcess(
                        process_id="native:centroids",
                        parameters=[ParameterInput("ALL_PARTS", False)],
                    ),
                    execution_mode=ExecutionMode.ASYNC,
                ),
            ),
        ],
    )
    def test_submit_calls(self, execution_mode, job_info):
        """Queues with the execution mode in the job info, the queued status and the
        expiry in one transaction on the state queue."""
        client = FakeRedisClient(values={}, job_hashes=[], message=None)
        job_parameter = QslJobParameterExecuteProcess(
            process_id="native:centroids",
            parameters=[ParameterInput("ALL_PARTS", False)],
        )
        asyncio.run(RedisStateQueue(client).submit("my_cool_id", job_parameter, execution_mode))
        assert client.calls == [
            ("hset", "job:my_cool_id", "info", JsonSerializer().render(job_info)),
            ("hset", "job:my_cool_id", "info_type", "QslJobInfoExecuteProcess"),
            ("hset", "job:my_cool_id", "status", "queued"),
            ("hset", "job:my_cool_id", "timestamp.queued", ANY),
            ("hset", "job:my_cool_id", "timestamp.last_update", ANY),
            ("hset", "job:my_cool_id", "duration", ANY),
            ("rpush", "jobs:process", "my_cool_id"),
            ("expire", "job:my_cool_id", 86400),
            ("execute",),
        ]

    def test_submit_unsupported(self):
        client = FakeRedisClient(values={}, job_hashes=[], message=None)
        with pytest.raises(TypeError, match="Unsupported runner type"):
            asyncio.run(RedisStateQueue(client).submit("my_cool_id", QslJobParameter()))

    def test_state_missing(self):
        # redis answers an empty hash for a key which does not exist
        client = FakeRedisClient(values={}, job_hashes=[{}], message=None)
        assert asyncio.run(RedisStateQueue(client).state("my_cool_id")) is None

    @pytest.mark.parametrize(
        "job_hashes,expected",
        [
            (
                [{b"status": b"queued"}],
                JobState(id="my_cool_id", status=Status.QUEUED),
            ),
            (
                [
                    {
                        b"status": b"running",
                        b"timestamp.last_update": b"2026-11-08T13:00:00",
                    }
                ],
                JobState(id="my_cool_id", status=Status.RUNNING, last_update="2026-11-08T13:00:00"),
            ),
            (
                [
                    {
                        b"status": b"succeed",
                        b"timestamp.last_update": b"2026-11-08T13:00:01",
                        b"result": b'{"outputs": [], "log": ""}',
                        b"result_content_type": (
                            b"application/qgis-server-light.interface.job.process.ProcessResult"
                        ),
                    }
                ],
                JobState(
                    id="my_cool_id",
                    status=Status.SUCCESS,
                    last_update="2026-11-08T13:00:01",
                    result=JobResult(
                        id="my_cool_id",
                        data=b'{"outputs": [], "log": ""}',
                        content_type=(
                            "application/qgis-server-light.interface.job.process.ProcessResult"
                        ),
                    ),
                ),
            ),
            (
                [
                    {
                        b"status": b"failed",
                        b"timestamp.last_update": b"2026-11-08T13:00:01",
                        b"message": b"Algorithm `native:centroids` failed",
                    }
                ],
                JobState(
                    id="my_cool_id",
                    status=Status.FAILURE,
                    last_update="2026-11-08T13:00:01",
                    message="Algorithm `native:centroids` failed",
                ),
            ),
        ],
    )
    def test_state(self, job_hashes, expected):
        client = FakeRedisClient(values={}, job_hashes=job_hashes, message=None)
        assert asyncio.run(RedisStateQueue(client).state("my_cool_id")) == expected

    def test_wait_missing(self):
        # redis answers an empty hash for a key which does not exist
        client = FakeRedisClient(values={}, job_hashes=[{}], message=None)
        assert asyncio.run(RedisStateQueue(client).wait("my_cool_id")) is None
        assert client.calls == [
            ("subscribe", "notifications:my_cool_id"),
            ("hgetall", "job:my_cool_id"),
        ]

    @pytest.mark.parametrize(
        "job_hashes,expected_status",
        [
            ([{b"status": b"succeed"}], Status.SUCCESS),
            ([{b"status": b"failed"}], Status.FAILURE),
        ],
    )
    def test_wait_returns_finished_state_immediately(self, job_hashes, expected_status):
        client = FakeRedisClient(values={}, job_hashes=job_hashes, message=None)
        job_state = asyncio.run(RedisStateQueue(client).wait("my_cool_id"))
        assert job_state.status == expected_status
        assert client.calls == [
            ("subscribe", "notifications:my_cool_id"),
            ("hgetall", "job:my_cool_id"),
        ]

    @pytest.mark.parametrize(
        "job_hashes,message,expected_status",
        [
            (
                [{b"status": b"running"}, {b"status": b"succeed"}],
                {"data": b"succeed"},
                Status.SUCCESS,
            ),
            (
                [{b"status": b"running"}, {b"status": b"failed"}],
                {"data": b"failed"},
                Status.FAILURE,
            ),
        ],
    )
    def test_wait_on_finish(self, job_hashes, message, expected_status):
        """The first read finds the job running, the notification wakes the dispatcher
        and the second read finds it finished."""
        client = FakeRedisClient(values={}, job_hashes=job_hashes, message=message)
        job_state = asyncio.run(RedisStateQueue(client).wait("my_cool_id"))
        assert job_state.status == expected_status

    def test_wait_timeout_returns_current_state(self):
        """Subscribes before reading the state, so a notification in between is not lost,
        and reads the state again after the timeout."""
        client = FakeRedisClient(
            values={},
            job_hashes=[{b"status": b"running"}, {b"status": b"running"}],
            message=None,
        )
        job_state = asyncio.run(RedisStateQueue(client).wait("my_cool_id", to=0.01))
        assert job_state.status == Status.RUNNING
        assert client.calls == [
            ("subscribe", "notifications:my_cool_id"),
            ("hgetall", "job:my_cool_id"),
            ("hgetall", "job:my_cool_id"),
        ]
