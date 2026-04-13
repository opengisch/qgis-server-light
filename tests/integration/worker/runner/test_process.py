import json
import uuid
from pathlib import Path

import pytest

from qgis_server_light.interface.exporter.extract import OgrSource
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.input import (
    ParameterInput,
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
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
                    OgrSource(
                        path="placenames.gpkg", layer_name="placenames"
                    ).to_qgis_decoded_uri
                ),
                remote=False,
                folder_name="data",
                driver="ogr",
            ),
        ],
    )
    def test_execute_buffer(self, qgis_app, data_path, job_layer):
        job_id = str(uuid.uuid4())
        output_layer_path = f"{data_path}/process_output/{job_id}/Buffered.gpkg"
        Path(output_layer_path).parent.mkdir(parents=True)
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:buffer",
                parameters=[
                    ParameterInput("INPUT", job_layer),
                    ParameterInput("DISTANCE", 1.0),
                    ParameterInput("OUTPUT", str(output_layer_path)),
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
            JobContext(base_path=data_path),
            job_info,
            {},
        )
        result = runner.run()
        assert isinstance(result, JobResult)
        assert result.id == job_id
        assert result.data["ok"]
        assert result.data["result"]["OUTPUT"] == output_layer_path

    @pytest.mark.parametrize(
        "job_layer",
        [
            QslJobLayer(
                id=str(uuid.uuid4()),
                name="test-local-gpkg",
                source=json.dumps(
                    OgrSource(
                        path="placenames.gpkg", layer_name="placenames"
                    ).to_qgis_decoded_uri
                ),
                remote=False,
                folder_name="data",
                driver="ogr",
            ),
        ],
    )
    def test_execute_centroids(self, qgis_app, data_path, job_layer):
        job_id = str(uuid.uuid4())
        output_layer_path = f"{data_path}/process_output/{job_id}/Centroids.gpkg"
        Path(output_layer_path).parent.mkdir(parents=True)
        job_info = QslJobInfoExecuteProcess(
            id=job_id,
            type=QslJobInfoExecuteProcess.__name__,
            job=QslJobParameterExecuteProcess(
                process_id="native:centroids",
                parameters=[
                    ParameterInput("INPUT", job_layer),
                    ParameterInput("OUTPUT", output_layer_path),
                ],
            ),
        )

        runner = ProcessRunner(
            qgis_app,
            JobContext(base_path=data_path),
            job_info,
            {},
        )
        result = runner.run()
        assert isinstance(result, JobResult)
        assert result.id == job_id
        assert result.data["ok"]
        assert result.data["result"]["OUTPUT"] == output_layer_path
