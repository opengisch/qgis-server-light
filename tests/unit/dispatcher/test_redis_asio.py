import asyncio
import pickle
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, call

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.dispatcher.redis_asio import RedisQueue, RedisStateQueue
from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.dispatcher.common import JobState, Status, Worker
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
from qgis_server_light.interface.job.process.input import (
    ParameterInput,
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)
from qgis_server_light.interface.worker.info import EngineInfo, QgisInfo
from qgis_server_light.interface.worker.info import Status as WorkerStatus


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


@pytest.fixture
def pipeline():
    yield AsyncMock()


@pytest.fixture
def pubsub():
    yield AsyncMock()


@pytest.fixture
def client(pipeline, pubsub):
    # redis commands are awaited, only opening a pipeline or a subscription is not
    client = AsyncMock()
    client.pipeline = MagicMock()
    client.pipeline.return_value.__aenter__.return_value = pipeline
    client.pubsub = MagicMock()
    client.pubsub.return_value.__aenter__.return_value = pubsub
    yield client


class TestRedisQueue:
    def test_protocol(self):
        assert RedisQueue.job_queue_name == "jobs"
        assert RedisQueue.job_key("my_cool_id") == "job:my_cool_id"
        assert RedisQueue.channel("my_cool_id") == "notifications:my_cool_id"

    def test_post_subscribes_before_queuing(self, client, pipeline, pubsub, monkeypatch):
        monkeypatch.setattr("qgis_server_light.dispatcher.redis_asio.uuid4", lambda: "my_cool_id")
        # the worker finished the job successfully
        pubsub.get_message.return_value = {
            "data": pickle.dumps(JobResult(id="my_cool_id", data=b"", content_type="image/png"))
        }
        client.hget.return_value = Status.SUCCESS.value.encode()
        # one recorder for both, so the order of subscribing and queuing is visible
        recorder = Mock()
        recorder.attach_mock(pubsub.subscribe, "subscribe")
        recorder.attach_mock(pipeline.rpush, "rpush")

        result, status = asyncio.run(RedisQueue(client).post(QslJobParameterLegend(layers=[])))
        assert status == Status.SUCCESS.value
        # a fast job could publish its result before anyone listens, so we subscribe first
        assert recorder.mock_calls == [
            call.subscribe("notifications:my_cool_id"),
            call.rpush("jobs", "my_cool_id"),
        ]

    def test_post_sets_queued_status_in_queuing_transaction(
        self, client, pipeline, pubsub, monkeypatch
    ):
        monkeypatch.setattr("qgis_server_light.dispatcher.redis_asio.uuid4", lambda: "my_cool_id")
        pubsub.get_message.return_value = {
            "data": pickle.dumps(JobResult(id="my_cool_id", data=b"", content_type="image/png"))
        }
        client.hget.return_value = Status.SUCCESS.value.encode()

        asyncio.run(RedisQueue(client).post(QslJobParameterLegend(layers=[])))
        # the queued status is written before the job is queued and in the same
        # transaction, so it can't overwrite a status the worker set already
        assert pipeline.mock_calls == [
            call.hset("job:my_cool_id", "info", ANY),
            call.hset("job:my_cool_id", "info_type", "QslJobInfoLegend"),
            call.hset("job:my_cool_id", "status", "queued"),
            call.hset("job:my_cool_id", "timestamp.queued", ANY),
            call.hset("job:my_cool_id", "timestamp.last_update", ANY),
            call.hset("job:my_cool_id", "duration", ANY),
            call.rpush("jobs", "my_cool_id"),
            call.execute(),
        ]

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
    def test_post_calls(self, client, pipeline, pubsub, monkeypatch, job_parameter, job_info):
        """Subscribes before queuing, queues with the queued status in one transaction
        on the publish queue and deletes the job hash in the end."""
        # `post` generates the job id, it is fixed so the expected calls can name it
        monkeypatch.setattr("qgis_server_light.dispatcher.redis_asio.uuid4", lambda: "my_cool_id")
        pubsub.get_message.return_value = {
            "data": pickle.dumps(JobResult(id="my_cool_id", data=b"png", content_type="image/png"))
        }
        client.hget.return_value = Status.SUCCESS.value.encode()
        # one recorder for all, so the order of the calls is visible
        recorder = Mock()
        recorder.attach_mock(pubsub.subscribe, "subscribe")
        recorder.attach_mock(pipeline, "pipeline")
        recorder.attach_mock(client.hget, "hget")
        recorder.attach_mock(client.delete, "delete")

        asyncio.run(RedisQueue(client).post(job_parameter))
        assert recorder.mock_calls == [
            call.subscribe("notifications:my_cool_id"),
            call.pipeline.hset("job:my_cool_id", "info", JsonSerializer().render(job_info)),
            call.pipeline.hset("job:my_cool_id", "info_type", job_info.type),
            call.pipeline.hset("job:my_cool_id", "status", "queued"),
            call.pipeline.hset("job:my_cool_id", "timestamp.queued", ANY),
            call.pipeline.hset("job:my_cool_id", "timestamp.last_update", ANY),
            call.pipeline.hset("job:my_cool_id", "duration", ANY),
            call.pipeline.rpush("jobs", "my_cool_id"),
            call.pipeline.execute(),
            call.hget("job:my_cool_id", "status"),
            call.delete("job:my_cool_id"),
        ]

    @pytest.mark.parametrize(
        "status,message,expected",
        [
            (
                b"succeed",
                {
                    "data": pickle.dumps(
                        JobResult(id="my_cool_id", data=b"png", content_type="image/png")
                    )
                },
                (JobResult(id="my_cool_id", data=b"png", content_type="image/png"), "succeed"),
            ),
            (
                b"failed",
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
    def test_post_returns_published_result(self, client, pubsub, status, message, expected):
        pubsub.get_message.return_value = message
        client.hget.return_value = status
        job_parameter = QslJobParameterLegend(layers=[])
        assert asyncio.run(RedisQueue(client).post(job_parameter)) == expected


@pytest.fixture
def engine_info():
    yield EngineInfo(
        id="worker-a",
        qgis_info=QgisInfo(version=34400, version_name="3.44", path="/usr"),
        status=WorkerStatus.WAITING,
        started=0.0,
    )


class TestRedisQueueIsReachable:
    def test_reachable(self):
        client = AsyncMock()
        client.ping.return_value = True
        assert asyncio.run(RedisQueue(client).is_reachable()) is True

    @pytest.mark.parametrize(
        "ping_error",
        [
            RedisConnectionError("Error 111 connecting to qsl-redis:6379. Connection refused."),
            RedisTimeoutError("Timeout connecting to server"),
        ],
    )
    def test_unreachable(self, ping_error):
        # the caller only gets to know that redis is not reachable, the redis exception
        # stays inside the dispatcher
        client = AsyncMock()
        client.ping.side_effect = ping_error
        assert asyncio.run(RedisQueue(client).is_reachable()) is False


class TestRedisQueueRegisteredWorkers:
    def test_stale_and_crashed_workers_are_registered(self, engine_info):
        now = datetime.now(UTC)
        alive_last_seen = now - timedelta(seconds=1)
        stale_last_seen = now - timedelta(seconds=60)
        crashed_info = replace(engine_info, status=WorkerStatus.CRASHED)
        client = AsyncMock()
        client.smembers.return_value = {b"worker-alive", b"worker-stale", b"worker-crashed"}
        # last_seen and info of each worker, in the order of the sorted ids
        client.hmget.side_effect = [
            [alive_last_seen.isoformat().encode(), JsonSerializer().render(engine_info).encode()],
            [alive_last_seen.isoformat().encode(), JsonSerializer().render(crashed_info).encode()],
            [stale_last_seen.isoformat().encode(), JsonSerializer().render(engine_info).encode()],
        ]

        # every worker redis still knows is reported, the consumer tells them apart by
        # the age of the heartbeat and the status in the info
        assert asyncio.run(RedisQueue(client).registered_workers()) == [
            Worker(id="worker-alive", last_seen=alive_last_seen, info=engine_info),
            Worker(id="worker-crashed", last_seen=alive_last_seen, info=crashed_info),
            Worker(id="worker-stale", last_seen=stale_last_seen, info=engine_info),
        ]
        # these are the keys the dispatcher reads
        client.smembers.assert_awaited_once_with("workers")
        assert client.hmget.await_args_list == [
            call("worker:worker-alive", ["last_seen", "info"]),
            call("worker:worker-crashed", ["last_seen", "info"]),
            call("worker:worker-stale", ["last_seen", "info"]),
        ]

    def test_worker_without_heartbeat_is_left_out(self):
        # the worker is still in the list but its hash expired already (e.g. it was killed)
        client = AsyncMock()
        client.smembers.return_value = {b"worker-gone"}
        client.hmget.return_value = [None, None]
        assert asyncio.run(RedisQueue(client).registered_workers()) == []

    def test_worker_without_info_is_left_out(self):
        # a worker of an older version lost its info with a redis restart, only its
        # heartbeat came back
        client = AsyncMock()
        client.smembers.return_value = {b"worker-old"}
        client.hmget.return_value = [datetime.now(UTC).isoformat().encode(), None]
        assert asyncio.run(RedisQueue(client).registered_workers()) == []


class TestRedisQueueAliveWorkers:
    def test_alive_and_stale_workers(self, engine_info):
        now = datetime.now(UTC)
        alive_last_seen = now - timedelta(seconds=1)
        stale_last_seen = now - timedelta(seconds=60)
        client = AsyncMock()
        client.smembers.return_value = {b"worker-alive", b"worker-stale"}
        client.hmget.side_effect = [
            [alive_last_seen.isoformat().encode(), JsonSerializer().render(engine_info).encode()],
            [stale_last_seen.isoformat().encode(), JsonSerializer().render(engine_info).encode()],
        ]
        # the stale worker missed far more heartbeats than allowed, it is not reported
        assert asyncio.run(RedisQueue(client).alive_workers()) == [
            Worker(id="worker-alive", last_seen=alive_last_seen, info=engine_info)
        ]

    def test_crashed_worker_is_left_out(self, engine_info):
        client = AsyncMock()
        client.smembers.return_value = {b"worker-crashed"}
        client.hmget.return_value = [
            datetime.now(UTC).isoformat().encode(),
            JsonSerializer().render(replace(engine_info, status=WorkerStatus.CRASHED)).encode(),
        ]
        # the crashed worker beat just now, but it won't serve any job anymore
        assert asyncio.run(RedisQueue(client).alive_workers()) == []

    def test_worker_without_heartbeat_is_left_out(self):
        # the worker is still in the list but its hash expired already (e.g. it was killed)
        client = AsyncMock()
        client.smembers.return_value = {b"worker-gone"}
        client.hmget.return_value = [None, None]
        assert asyncio.run(RedisQueue(client).alive_workers()) == []

    def test_no_workers_registered(self):
        client = AsyncMock()
        client.smembers.return_value = set()
        assert asyncio.run(RedisQueue(client).alive_workers()) == []

    def test_workers_are_sorted_by_id(self, engine_info):
        last_seen = datetime.now(UTC).isoformat().encode()
        client = AsyncMock()
        client.smembers.return_value = {b"worker-b", b"worker-c", b"worker-a"}
        client.hmget.return_value = [last_seen, JsonSerializer().render(engine_info).encode()]
        # redis sets have no order, the dispatcher gives a stable one
        workers = asyncio.run(RedisQueue(client).alive_workers())
        assert [worker.id for worker in workers] == ["worker-a", "worker-b", "worker-c"]

    def test_naive_heartbeat_of_older_worker_is_alive(self, engine_info):
        # workers before the UTC heartbeat write their time without offset
        naive_last_seen = datetime.now(UTC).replace(tzinfo=None)
        client = AsyncMock()
        client.smembers.return_value = {b"worker-old"}
        client.hmget.return_value = [
            naive_last_seen.isoformat().encode(),
            JsonSerializer().render(engine_info).encode(),
        ]
        assert asyncio.run(RedisQueue(client).alive_workers()) == [
            Worker(id="worker-old", last_seen=naive_last_seen.replace(tzinfo=UTC), info=engine_info)
        ]


class TestParseLastSeen:
    @pytest.mark.parametrize(
        "last_seen,expected",
        [
            # heartbeat of a current worker, UTC with offset
            (
                b"2026-11-10T11:02:03.123456+00:00",
                datetime(2026, 11, 10, 11, 2, 3, 123456, tzinfo=UTC),
            ),
            # heartbeat of a worker before the UTC heartbeat, read as UTC
            (
                b"2026-11-10T11:02:03.123456",
                datetime(2026, 11, 10, 11, 2, 3, 123456, tzinfo=UTC),
            ),
            # an offset other than UTC is kept, comparing aware datetimes still works
            (
                b"2026-11-10T12:02:03.123456+01:00",
                datetime(2026, 11, 10, 11, 2, 3, 123456, tzinfo=UTC),
            ),
        ],
    )
    def test_parse_last_seen(self, last_seen, expected):
        assert RedisQueue.parse_last_seen(last_seen) == expected


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
    def test_submit_calls(self, client, pipeline, execution_mode, job_info):
        """Queues with the execution mode in the job info, the queued status and the
        expiry in one transaction on the state queue."""
        job_parameter = QslJobParameterExecuteProcess(
            process_id="native:centroids",
            parameters=[ParameterInput("ALL_PARTS", False)],
        )
        asyncio.run(RedisStateQueue(client).submit("my_cool_id", job_parameter, execution_mode))
        assert pipeline.mock_calls == [
            call.hset("job:my_cool_id", "info", JsonSerializer().render(job_info)),
            call.hset("job:my_cool_id", "info_type", "QslJobInfoExecuteProcess"),
            call.hset("job:my_cool_id", "status", "queued"),
            call.hset("job:my_cool_id", "timestamp.queued", ANY),
            call.hset("job:my_cool_id", "timestamp.last_update", ANY),
            call.hset("job:my_cool_id", "duration", ANY),
            call.rpush("jobs:process", "my_cool_id"),
            call.expire("job:my_cool_id", 86400),
            call.execute(),
        ]

    def test_submit_unsupported(self, client):
        with pytest.raises(TypeError, match="Unsupported runner type"):
            asyncio.run(RedisStateQueue(client).submit("my_cool_id", QslJobParameter()))

    def test_state_missing(self, client):
        # redis answers an empty hash for a key which does not exist
        client.hgetall.return_value = {}
        assert asyncio.run(RedisStateQueue(client).state("my_cool_id")) is None

    @pytest.mark.parametrize(
        "job_hash,expected",
        [
            (
                {b"status": b"queued"},
                JobState(id="my_cool_id", status=Status.QUEUED),
            ),
            (
                {
                    b"status": b"running",
                    b"timestamp.last_update": b"2026-11-08T13:00:00",
                },
                JobState(id="my_cool_id", status=Status.RUNNING, last_update="2026-11-08T13:00:00"),
            ),
            (
                {
                    b"status": b"succeed",
                    b"timestamp.last_update": b"2026-11-08T13:00:01",
                    b"result": b'{"outputs": [], "log": ""}',
                    b"result_content_type": (
                        b"application/qgis-server-light.interface.job.process.ProcessResult"
                    ),
                },
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
                {
                    b"status": b"failed",
                    b"timestamp.last_update": b"2026-11-08T13:00:01",
                    b"message": b"Algorithm `native:centroids` failed",
                },
                JobState(
                    id="my_cool_id",
                    status=Status.FAILURE,
                    last_update="2026-11-08T13:00:01",
                    message="Algorithm `native:centroids` failed",
                ),
            ),
        ],
    )
    def test_state(self, client, job_hash, expected):
        client.hgetall.return_value = job_hash
        assert asyncio.run(RedisStateQueue(client).state("my_cool_id")) == expected
        client.hgetall.assert_awaited_once_with("job:my_cool_id")

    def test_wait_missing(self, client, pubsub):
        # redis answers an empty hash for a key which does not exist
        client.hgetall.return_value = {}
        assert asyncio.run(RedisStateQueue(client).wait("my_cool_id")) is None
        pubsub.subscribe.assert_awaited_once_with("notifications:my_cool_id")
        # nothing to wait for, the state is read only once
        client.hgetall.assert_awaited_once_with("job:my_cool_id")

    @pytest.mark.parametrize(
        "job_hash,expected_status",
        [
            ({b"status": b"succeed"}, Status.SUCCESS),
            ({b"status": b"failed"}, Status.FAILURE),
        ],
    )
    def test_wait_returns_finished_state_immediately(
        self, client, pubsub, job_hash, expected_status
    ):
        client.hgetall.return_value = job_hash
        job_state = asyncio.run(RedisStateQueue(client).wait("my_cool_id"))
        assert job_state.status == expected_status
        pubsub.subscribe.assert_awaited_once_with("notifications:my_cool_id")
        # the job is finished already, the dispatcher does not wait for a notification
        client.hgetall.assert_awaited_once_with("job:my_cool_id")
        pubsub.get_message.assert_not_awaited()

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
    def test_wait_on_finish(self, client, pubsub, job_hashes, message, expected_status):
        """The first read finds the job running, the notification wakes the dispatcher
        and the second read finds it finished."""
        client.hgetall.side_effect = job_hashes
        pubsub.get_message.return_value = message
        job_state = asyncio.run(RedisStateQueue(client).wait("my_cool_id"))
        assert job_state.status == expected_status

    def test_wait_timeout_returns_current_state(self, client, pubsub):
        """Subscribes before reading the state, so a notification in between is not lost,
        and reads the state again after the timeout."""

        async def no_message(timeout, ignore_subscribe_messages):
            # like a worker which does not finish in time, nothing arrives until the
            # timeout
            await asyncio.sleep(timeout)

        pubsub.get_message.side_effect = no_message
        client.hgetall.return_value = {b"status": b"running"}
        # one recorder for both, so the order of subscribing and reading is visible
        recorder = Mock()
        recorder.attach_mock(pubsub.subscribe, "subscribe")
        recorder.attach_mock(client.hgetall, "hgetall")

        job_state = asyncio.run(RedisStateQueue(client).wait("my_cool_id", to=0.01))
        assert job_state.status == Status.RUNNING
        assert recorder.mock_calls == [
            call.subscribe("notifications:my_cool_id"),
            call.hgetall("job:my_cool_id"),
            call.hgetall("job:my_cool_id"),
        ]
