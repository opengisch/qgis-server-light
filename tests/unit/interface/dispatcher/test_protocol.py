import pytest

from qgis_server_light.interface.dispatcher.protocol import (
    RedisProtocol,
    RedisPublishProtocol,
    RedisStateProtocol,
)


class TestRedisProtocol:
    def test_names(self):
        assert RedisProtocol.job_info_key == "info"
        assert RedisProtocol.job_info_type_key == "info_type"
        assert RedisProtocol.job_channel_name == "notifications"
        assert RedisProtocol.job_status_key == "status"
        assert RedisProtocol.job_duration_key == "duration"
        assert RedisProtocol.job_timestamp_key == "timestamp"
        assert RedisProtocol.job_last_update_key == "timestamp.last_update"
        assert RedisProtocol.process_registry_key == "processes"

    def test_job_key(self):
        assert RedisProtocol.job_key("ididid") == "job:ididid"

    def test_channel(self):
        assert RedisProtocol.channel("ididid") == "notifications:ididid"


class TestRedisPublishProtocol:
    def test_super(self):
        assert issubclass(RedisPublishProtocol, RedisProtocol)

    def test_queue_name(self):
        assert RedisPublishProtocol.queue_name() == "jobs"

    @pytest.mark.parametrize(
        "result_field",
        ["job_result_key", "job_result_content_type_key", "job_message_key", "job_expire"],
    )
    def test_keeps_no_state(self, result_field):
        assert not hasattr(RedisPublishProtocol, result_field)


class TestRedisStateProtocol:
    def test_super(self):
        assert issubclass(RedisStateProtocol, RedisProtocol)

    def test_queue_name(self):
        assert RedisStateProtocol.queue_name() == "jobs:process"

    def test_names(self):
        assert RedisStateProtocol.job_result_key == "result"
        assert RedisStateProtocol.job_result_content_type_key == "result_content_type"
        assert RedisStateProtocol.job_message_key == "message"
        assert RedisStateProtocol.job_expire == 86400
