from unittest.mock import ANY, Mock, call

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.worker.info import EngineInfo, QgisInfo
from qgis_server_light.interface.worker.info import Status as EngineStatus
from qgis_server_light.worker.redis import RedisEngine


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


@pytest.fixture
def engine():
    yield RedisEngineWithoutQgis()


@pytest.fixture
def client():
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
