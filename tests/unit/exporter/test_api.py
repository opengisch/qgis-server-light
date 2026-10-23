import json
from pathlib import Path

import pytest

from qgis_server_light.exporter import api
from qgis_server_light.exporter.api import (
    assemble_output_file_path,
    assemble_project_base_path,
)


class TestExporter:
    @pytest.mark.parametrize(
        "data_path,,project_name,expected",
        [
            (
                "/tmp/test",
                "test_project.qgs",
                "/tmp/test/test_project.qgs",
            ),
            (
                "/tmp/test",
                "test.project.qgz",
                "/tmp/test/test.project.qgz",
            ),
            (
                "/tmp/test",
                "test.project.4.2.5.qgz",
                "/tmp/test/test.project.4.2.5.qgz",
            ),
            (
                "/tmp/test",
                "subfolder/test.project.4.2.5.qgz",
                "/tmp/test/subfolder/test.project.4.2.5.qgz",
            ),
            (
                "/tmp/test",
                "subfolder/subsubfolder/test.project.4.2.5.qgz",
                "/tmp/test/subfolder/subsubfolder/test.project.4.2.5.qgz",
            ),
        ],
    )
    def test_assemble_project_base_path_behaves(self, data_path, project_name, expected):
        assert str(assemble_project_base_path(Path(data_path), project_name)) == expected

    @pytest.mark.parametrize(
        "project_base_path,output_format,expected",
        [
            (
                Path("/tmp/test/test_mandant/test_project"),
                "json",
                "/tmp/test/test_mandant/test_project.json",
            ),
            (
                Path("/tmp/test/test.mandant/test.project"),
                "json",
                "/tmp/test/test.mandant/test.project.json",
            ),
            (
                Path("/tmp/test/test.mandant/test.project.3.44.10"),
                "json",
                "/tmp/test/test.mandant/test.project.3.44.10.json",
            ),
        ],
    )
    def test_assemble_output_file_path_behaves(self, project_base_path, output_format, expected):
        assert str(assemble_output_file_path(project_base_path, output_format)) == expected


class TestApiExport:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(api, "DATA_ROOT", tmp_path)
        yield api.app.test_client()

    def test_pg_service_configs_is_rejected(self, client, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("the export must not be started")

        monkeypatch.setattr(api.subprocess, "run", fail)
        body = json.dumps(
            {
                "project_path": "project.qgz",
                "pg_service_configs": [{"name": "my_service", "password": "secret"}],
            }
        )
        response = client.post("/export", json=body)
        result = json.loads(response.data)
        assert result["successful"] is False
        assert "pg_service_configs" in result["content"]
