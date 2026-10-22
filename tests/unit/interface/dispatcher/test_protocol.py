from qgis_server_light.interface.dispatcher.protocol import RedisProtocol


class TestRedisProtocol:
    def test_names(self):
        assert RedisProtocol.job_queue_name == "jobs"
        assert RedisProtocol.job_info_key == "info"
        assert RedisProtocol.job_info_type_key == "info_type"
        assert RedisProtocol.job_channel_name == "notifications"
        assert RedisProtocol.job_status_key == "status"
        assert RedisProtocol.job_duration_key == "duration"
        assert RedisProtocol.job_timestamp_key == "timestamp"
        assert RedisProtocol.job_last_update_key == "timestamp.last_update"

    def test_job_key(self):
        assert RedisProtocol.job_key("ididid") == "job:ididid"

    def test_channel(self):
        assert RedisProtocol.channel("ididid") == "notifications:ididid"
