import json
import uuid

import pytest
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.exporter.extract import OgrSource
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.input import (
    ParameterInput,
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.process.output import (
    FileOutput,
    ParameterOutput,
    ProcessResult,
)
from qgis_server_light.worker.runner.common import JobContext
from qgis_server_light.worker.runner.process import ProcessRunner


class TestProcessRunnerIntegration:
    @pytest.mark.parametrize(
        "job_layer",
        [
            QslJobLayer(
                id=str(uuid.uuid4()),
                name="test-local-gpkg",
                source=json.dumps(
                    OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
                ),
                remote=False,
                folder_name="data",
                driver="ogr",
            ),
        ],
    )
    def test_execute_buffer(self, qgis_app, data_path, job_layer):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:buffer",
                parameters=[
                    ParameterInput("INPUT", job_layer),
                    ParameterInput("DISTANCE", 1.0),
                    ParameterInput("END_CAP_STYLE", "Round"),
                    ParameterInput("JOIN_STYLE", "Round"),
                    ParameterInput("MITER_LIMIT", 2.0),
                    ParameterInput("DISSOLVE", False),
                    ParameterInput("SEPARATE_DISJOINT", False),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:buffer"],
                process_output_dir=f"{data_path}/.process_output",
            ),
            job_info,
            {},
        )
        result = runner.run()
        assert isinstance(result, JobResult)
        assert result.id == job_id
        assert result.content_type == (
            "application/qgis-server-light.interface.job.process.ProcessResult"
        )
        process_result = JsonParser().from_bytes(result.data, ProcessResult)
        assert (
            ParameterOutput(
                "OUTPUT",
                FileOutput(
                    path=f"{job_id}/OUTPUT.gpkg", media_type="application/geopackage+sqlite3"
                ),
            )
            in process_result.outputs
        )

    @pytest.mark.parametrize(
        "job_layer",
        [
            QslJobLayer(
                id=str(uuid.uuid4()),
                name="test-local-gpkg",
                source=json.dumps(
                    OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
                ),
                remote=False,
                folder_name="data",
                driver="ogr",
            ),
        ],
    )
    def test_execute_centroids(self, qgis_app, data_path, job_layer):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[
                    ParameterInput("INPUT", job_layer),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:centroids"],
                process_output_dir=f"{data_path}/.process_output",
            ),
            job_info,
            {},
        )
        result = runner.run()
        assert isinstance(result, JobResult)
        assert result.id == job_id
        assert result.content_type == (
            "application/qgis-server-light.interface.job.process.ProcessResult"
        )
        process_result = JsonParser().from_bytes(result.data, ProcessResult)
        assert (
            ParameterOutput(
                "OUTPUT",
                FileOutput(
                    path=f"{job_id}/OUTPUT.gpkg", media_type="application/geopackage+sqlite3"
                ),
            )
            in process_result.outputs
        )

    def test_execute_unknown_algorithm(self, qgis_app, data_path):
        job_info = QslJobInfoExecuteProcess(
            id=str(uuid.uuid4()),
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:does_not_exist",
                parameters=[],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:does_not_exist"],
                process_output_dir=f"{data_path}/.process_output",
            ),
            job_info,
            {},
        )
        with pytest.raises(RuntimeError, match="native:does_not_exist` not found"):
            runner.run()

    def test_execute_failing_algorithm(self, qgis_app, data_path):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[
                    ParameterInput("INPUT", f"{data_path}/does_not_exist.gpkg"),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:centroids"],
                process_output_dir=f"{data_path}/.process_output",
            ),
            job_info,
            {},
        )
        with pytest.raises(RuntimeError, match="native:centroids` failed"):
            runner.run()

    def test_execute_algorithm_not_served(self, qgis_app, data_path):
        job_info = QslJobInfoExecuteProcess(
            id=str(uuid.uuid4()),
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(base_path=data_path, process_allowlist=["native:buffer"]),
            job_info,
            {},
        )
        with pytest.raises(RuntimeError, match="native:centroids` is not served"):
            runner.run()


class TestProcessRunnerInfo:
    @pytest.mark.parametrize(
        "process_allowlist",
        [
            ["native:centroids"],
            ["native:buffer", "native:centroids"],
        ],
    )
    def test_info_follows_allowlist(self, qgis_app, process_allowlist):
        process_descriptions = ProcessRunner.info(qgis_app, process_allowlist)
        assert [process.id for process in process_descriptions.processes] == process_allowlist

    def test_info_unknown_algorithm(self, qgis_app):
        with pytest.raises(LookupError, match="native:does_not_exist` of the allowlist"):
            ProcessRunner.info(qgis_app, ["native:does_not_exist"])
