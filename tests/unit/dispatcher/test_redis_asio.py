import asyncio
import pickle
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, call

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.dispatcher.redis_asio import RedisQueue, derive_job_info
from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.dispatcher.common import Status, Worker
from qgis_server_light.interface.job.common.input import QslJobParameter
from qgis_server_light.interface.job.common.output import JobResult
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
        job_info = derive_job_info("my_cool_id", job_parameter)
        assert isinstance(job_info, expected_class)
        assert job_info.id == "my_cool_id"
        assert job_info.type == expected_class.__name__
        assert job_info.job is job_parameter

    def test_unsupported(self):
        with pytest.raises(TypeError, match="Unsupported runner type"):
            derive_job_info("blabla", QslJobParameter())


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
