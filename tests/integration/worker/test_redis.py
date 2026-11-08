import pytest
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.dispatcher.protocol import RedisProtocol
from qgis_server_light.interface.job.process.description import ProcessDescriptions
from qgis_server_light.worker.engine import Engine
from qgis_server_light.worker.redis import DEFAULT_RUNNER_PLUGINS, RedisEngine
from qgis_server_light.worker.runner.process import ProcessRunner


class TestRunnerPluginQueues:
    """The queues a worker listens on follow from the runner plugins it boots with."""

    @pytest.mark.parametrize(
        "runner_plugins,expected",
        [
            (DEFAULT_RUNNER_PLUGINS, ["jobs"]),
            ("qgis_server_light.worker.runner.process.ProcessRunner", ["jobs:process"]),
            (
                f"{DEFAULT_RUNNER_PLUGINS}:qgis_server_light.worker.runner.process.ProcessRunner",
                ["jobs", "jobs:process"],
            ),
        ],
    )
    def test_queue_names(self, runner_plugins, expected):
        job_info_types = [
            Engine._load_runner_class(path).job_info_class.__name__
            for path in runner_plugins.split(":")
        ]
        assert RedisProtocol.queue_names(job_info_types) == expected

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

    def test_write(self, qgis_app):
        process_descriptions = ProcessRunner.info(qgis_app, ["native:centroids"])
        client = FakeRedisClient()
        assert RedisEngine.write_process_registry(client, process_descriptions)
        registry_json = client.values[RedisProtocol.process_registry_key]
        assert JsonParser().from_string(registry_json, ProcessDescriptions) == process_descriptions

    def test_second_write_keeps_entry(self, qgis_app):
        client = FakeRedisClient()
        RedisEngine.write_process_registry(
            client, ProcessRunner.info(qgis_app, ["native:centroids"])
        )
        registry_json = client.values[RedisProtocol.process_registry_key]
        assert not RedisEngine.write_process_registry(
            client, ProcessRunner.info(qgis_app, ["native:buffer"])
        )
        assert client.values[RedisProtocol.process_registry_key] == registry_json
