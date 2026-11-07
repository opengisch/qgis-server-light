import pytest

from qgis_server_light.interface.dispatcher.protocol import RedisProtocol


class TestRedisProtocol:
    def test_names(self):
        assert RedisProtocol.job_queue_name == "jobs"
        assert RedisProtocol.job_process_queue_name == "jobs:process"
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

    @pytest.mark.parametrize(
        "job_info_type,expected",
        [
            ("QslJobInfoRender", "jobs"),
            ("QslJobInfoFeatureInfo", "jobs"),
            ("QslJobInfoLegend", "jobs"),
            ("QslJobInfoFeature", "jobs"),
            ("QslJobInfoCrs", "jobs"),
            ("QslJobInfoExecuteProcess", "jobs:process"),
        ],
    )
    def test_queue_name(self, job_info_type, expected):
        assert RedisProtocol.queue_name(job_info_type) == expected

    def test_queue_name_unknown(self):
        with pytest.raises(KeyError, match="QslJobInfoUnknown"):
            RedisProtocol.queue_name("QslJobInfoUnknown")

    @pytest.mark.parametrize(
        "job_info_types,expected",
        [
            (["QslJobInfoRender", "QslJobInfoLegend", "QslJobInfoCrs"], ["jobs"]),
            (["QslJobInfoExecuteProcess"], ["jobs:process"]),
            (["QslJobInfoRender", "QslJobInfoExecuteProcess"], ["jobs", "jobs:process"]),
            (["QslJobInfoExecuteProcess", "QslJobInfoRender"], ["jobs:process", "jobs"]),
            ([], []),
        ],
    )
    def test_queue_names(self, job_info_types, expected):
        assert RedisProtocol.queue_names(job_info_types) == expected
