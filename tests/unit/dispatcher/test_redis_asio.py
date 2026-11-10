import asyncio
import pickle
from datetime import UTC, datetime, timedelta

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

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


class FakePipeline:
    def __init__(self, calls: list):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def hset(self, key, field, value):
        self.calls.append(("hset", key, field))

    async def rpush(self, name, value):
        self.calls.append(("rpush", name, value))

    async def execute(self):
        self.calls.append(("execute",))


class FakePubSub:
    def __init__(self, calls: list):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def subscribe(self, channel):
        self.calls.append(("subscribe", channel))

    async def get_message(self, timeout, ignore_subscribe_messages):
        job_id = next(call[2] for call in self.calls if call[0] == "rpush")
        return {"data": pickle.dumps(JobResult(id=job_id, data=b"", content_type="image/png"))}


class FakeRedisClient:
    def __init__(self):
        self.calls = []

    def pipeline(self):
        return FakePipeline(self.calls)

    def pubsub(self):
        return FakePubSub(self.calls)

    async def hget(self, key, field):
        return Status.SUCCESS.value.encode()

    async def delete(self, key):
        self.calls.append(("delete", key))


class TestRedisQueue:
    def test_protocol(self):
        assert RedisQueue.job_queue_name == "jobs"
        assert RedisQueue.job_key("my_cool_id") == "job:my_cool_id"
        assert RedisQueue.channel("my_cool_id") == "notifications:my_cool_id"

    def test_post_subscribes_before_queuing(self):
        client = FakeRedisClient()
        result, status = asyncio.run(RedisQueue(client).post(QslJobParameterLegend(layers=[])))
        assert status == Status.SUCCESS.value
        names = [call[0] for call in client.calls]
        assert names.index("subscribe") < names.index("rpush")

    def test_post_sets_queued_status_in_queuing_transaction(self):
        client = FakeRedisClient()
        asyncio.run(RedisQueue(client).post(QslJobParameterLegend(layers=[])))
        job_id = next(call[2] for call in client.calls if call[0] == "rpush")
        job_key = RedisQueue.job_key(job_id)
        status_index = client.calls.index(("hset", job_key, RedisQueue.job_status_key))
        rpush_index = next(index for index, call in enumerate(client.calls) if call[0] == "rpush")
        execute_indexes = [index for index, call in enumerate(client.calls) if call[0] == "execute"]
        assert execute_indexes == [rpush_index + 1]
        assert status_index < rpush_index


class FakeWorkerRedisClient:
    """Holds sets and hashes the way they are laid out in redis, keyed by their redis
    names, so the test shows which keys the dispatcher has to read."""

    def __init__(self, sets: dict, hashes: dict, ping_error: Exception | None = None):
        self.sets = sets
        self.hashes = hashes
        self.ping_error = ping_error

    async def ping(self):
        if self.ping_error is not None:
            raise self.ping_error
        return True

    async def smembers(self, name):
        return self.sets.get(name, set())

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)


class TestRedisQueueIsReachable:
    def test_reachable(self):
        client = FakeWorkerRedisClient(sets={}, hashes={})
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
        client = FakeWorkerRedisClient(sets={}, hashes={}, ping_error=ping_error)
        assert asyncio.run(RedisQueue(client).is_reachable()) is False


class TestRedisQueueAliveWorkers:
    def test_alive_and_stale_workers(self):
        now = datetime.now(UTC)
        alive_last_seen = now - timedelta(seconds=1)
        stale_last_seen = now - timedelta(seconds=60)
        client = FakeWorkerRedisClient(
            sets={"workers": {b"worker-alive", b"worker-stale"}},
            hashes={
                "worker:worker-alive": {"last_seen": alive_last_seen.isoformat().encode()},
                "worker:worker-stale": {"last_seen": stale_last_seen.isoformat().encode()},
            },
        )
        # the stale worker missed far more heartbeats than allowed, it is not reported
        assert asyncio.run(RedisQueue(client).alive_workers()) == [
            Worker(id="worker-alive", last_seen=alive_last_seen)
        ]

    def test_worker_without_heartbeat_is_left_out(self):
        # the worker is still in the list but its hash expired already (e.g. it was killed)
        client = FakeWorkerRedisClient(sets={"workers": {b"worker-gone"}}, hashes={})
        assert asyncio.run(RedisQueue(client).alive_workers()) == []

    def test_no_workers_registered(self):
        client = FakeWorkerRedisClient(sets={}, hashes={})
        assert asyncio.run(RedisQueue(client).alive_workers()) == []

    def test_workers_are_sorted_by_id(self):
        last_seen = datetime.now(UTC).isoformat().encode()
        client = FakeWorkerRedisClient(
            sets={"workers": {b"worker-b", b"worker-c", b"worker-a"}},
            hashes={
                "worker:worker-a": {"last_seen": last_seen},
                "worker:worker-b": {"last_seen": last_seen},
                "worker:worker-c": {"last_seen": last_seen},
            },
        )
        # redis sets have no order, the dispatcher gives a stable one
        workers = asyncio.run(RedisQueue(client).alive_workers())
        assert [worker.id for worker in workers] == ["worker-a", "worker-b", "worker-c"]

    def test_naive_heartbeat_of_older_worker_is_alive(self):
        # workers before the UTC heartbeat write their time without offset
        naive_last_seen = datetime.now(UTC).replace(tzinfo=None)
        client = FakeWorkerRedisClient(
            sets={"workers": {b"worker-old"}},
            hashes={"worker:worker-old": {"last_seen": naive_last_seen.isoformat().encode()}},
        )
        assert asyncio.run(RedisQueue(client).alive_workers()) == [
            Worker(id="worker-old", last_seen=naive_last_seen.replace(tzinfo=UTC))
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
