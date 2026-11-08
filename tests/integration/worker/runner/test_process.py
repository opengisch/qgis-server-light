import uuid

import pytest
from xsdata.formats.dataclass.parsers import JsonParser

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
    def test_execute_buffer(self, qgis_app, data_path, placenames_layer):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:buffer",
                parameters=[
                    ParameterInput("INPUT", placenames_layer),
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

    def test_execute_centroids(self, qgis_app, data_path, placenames_layer):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[
                    ParameterInput("INPUT", placenames_layer),
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

    def test_execute_without_process_output_dir(self, qgis_app, data_path):
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
            JobContext(base_path=data_path, process_allowlist=["native:centroids"]),
            job_info,
            {},
        )
        with pytest.raises(RuntimeError, match="No process output dir configured"):
            runner.run()

    def test_execute_writes_destination_into_job_dir(
        self, qgis_app, data_path, tmp_path, placenames_layer
    ):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[
                    ParameterInput("INPUT", placenames_layer),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:centroids"],
                process_output_dir=tmp_path,
            ),
            job_info,
            {},
        )
        runner.run()
        assert (tmp_path / job_id / "OUTPUT.gpkg").is_file()

    def test_execute_file_and_literal_outputs(
        self, qgis_app, data_path, tmp_path, placenames_layer
    ):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:basicstatisticsforfields",
                parameters=[
                    ParameterInput("INPUT_LAYER", placenames_layer),
                    ParameterInput("FIELD_NAME", "name"),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:basicstatisticsforfields"],
                process_output_dir=tmp_path,
            ),
            job_info,
            {},
        )
        result = runner.run()
        process_result = JsonParser().from_bytes(result.data, ProcessResult)
        assert (
            ParameterOutput(
                "OUTPUT_HTML_FILE",
                FileOutput(path=f"{job_id}/OUTPUT_HTML_FILE.html", media_type="text/html"),
            )
            in process_result.outputs
        )
        assert ParameterOutput("COUNT", 93) in process_result.outputs
        assert ParameterOutput("MIN", "Aarau") in process_result.outputs

    def test_execute_client_destination_rejected(
        self, qgis_app, data_path, tmp_path, placenames_layer
    ):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[
                    ParameterInput("INPUT", placenames_layer),
                    ParameterInput("OUTPUT", "/tmp/somewhere_else.gpkg"),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=["native:centroids"],
                process_output_dir=tmp_path,
            ),
            job_info,
            {},
        )
        with pytest.raises(ValueError, match="Destination `OUTPUT` is set by the worker"):
            runner.run()
        assert not (tmp_path / job_id).exists()

    @pytest.mark.parametrize(
        "process_id",
        [
            # destination extension `file`
            "native:filedownloader",
            # folder destination, no extension at all
            "native:splitvectorlayer",
        ],
    )
    def test_execute_unknown_destination_extension(self, qgis_app, data_path, tmp_path, process_id):
        job_id = str(uuid.uuid4())
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id=process_id,
                parameters=[],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(
                base_path=data_path,
                process_allowlist=[process_id],
                process_output_dir=tmp_path,
            ),
            job_info,
            {},
        )
        with pytest.raises(ValueError, match="No media type for extension"):
            runner.run()
        assert not (tmp_path / job_id).exists()

    def test_execute_failing_algorithm_removes_job_dir(self, qgis_app, data_path, tmp_path):
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
                process_output_dir=tmp_path,
            ),
            job_info,
            {},
        )
        with pytest.raises(RuntimeError, match="native:centroids` failed"):
            runner.run()
        assert not (tmp_path / job_id).exists()

    def test_execute_existing_job_dir_kept(self, qgis_app, data_path, tmp_path):
        job_id = str(uuid.uuid4())
        (tmp_path / job_id).mkdir()
        (tmp_path / job_id / "OUTPUT.gpkg").write_text("result of an earlier job")
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
                process_output_dir=tmp_path,
            ),
            job_info,
            {},
        )
        with pytest.raises(FileExistsError):
            runner.run()
        assert (tmp_path / job_id / "OUTPUT.gpkg").read_text() == "result of an earlier job"


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
