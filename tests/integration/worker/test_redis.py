import pytest

from qgis_server_light.interface.dispatcher.protocol import RedisProtocol
from qgis_server_light.worker.engine import Engine
from qgis_server_light.worker.redis import DEFAULT_RUNNER_PLUGINS


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
