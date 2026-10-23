import logging

import pytest
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer
from xsdata.formats.dataclass.serializers import JsonSerializer, XmlSerializer

from qgis_server_light.exporter.extract import Exporter
from qgis_server_light.worker.qgis import Qgis


class TestCreateQslSourcePostgresql:
    def test_explicit_sslmode_is_kept(self):
        # decoded datasources are stringified by Exporter.decode_datasource
        datasource = {"service": "my_service", "table": "my_table", "key": "id", "sslmode": "3"}
        source = Exporter.create_qsl_source_postgresql(datasource)
        assert source.sslmode == 3
        assert source.ssl_mode_text == "require"

    def test_credentials_from_project_are_kept(self):
        datasource = {
            "host": "db.example.com",
            "port": "5432",
            "dbname": "gis",
            "username": "reader",
            "password": "secret",  # NOSONAR
            "schema": "public",
            "table": "my_table",
            "key": "id",
        }
        source = Exporter.create_qsl_source_postgresql(datasource)
        assert source.service is None
        assert source.host == "db.example.com"
        assert source.port == 5432
        assert source.username == "reader"
        assert source.password == "secret"


@pytest.fixture(scope="module")
def qgis_application():
    yield QgsApplication.instance() or Qgis(None, logging.INFO)


class TestPostgresServiceExport:
    """
    Exports a project whose postgres layer references a pg_service and checks the
    serialized output, as the cli renders it. The service credentials must stay in
    the pg_service.conf and never reach the exported configuration.
    """

    service_user = "qsl_service_user"
    service_password = "qsl_service_password"  # NOSONAR
    service_dbname = "qsl_service_db"

    @pytest.fixture
    def project_path(self, qgis_application, tmp_path, monkeypatch):
        pg_service_file = tmp_path / "pg_service.conf"
        # unreachable port, so that libpq fails right away instead of connecting
        pg_service_file.write_text(
            "[qsl_test]\n"
            "host=127.0.0.1\n"
            "port=1\n"
            f"dbname={self.service_dbname}\n"
            f"user={self.service_user}\n"
            f"password={self.service_password}\n"
            "sslmode=require\n"
            "connect_timeout=1\n"
        )
        monkeypatch.setenv("PGSERVICEFILE", str(pg_service_file))
        project = QgsProject()
        project.addMapLayer(
            QgsVectorLayer(
                "service='qsl_test' key='id' type=Point srid=2056 "
                'table="public"."my_table" (geom)',
                "my_layer",
                "postgres",
            )
        )
        path = tmp_path / "project.qgs"
        assert project.write(str(path))
        yield str(path)
        QgsProject.instance().clear()

    @pytest.fixture
    def config(self, project_path):
        yield Exporter(project_path).run()

    def test_postgres_layer_is_exported(self, config):
        assert len(config.datasets.vector) == 1
        assert config.datasets.vector[0].source.postgres is not None

    def test_source_only_references_the_service(self, config):
        source = config.datasets.vector[0].source.postgres
        assert source.service == "qsl_test"
        assert source.host is None
        assert source.port is None
        assert source.dbname is None
        assert source.username is None
        assert source.password is None
        assert source.sslmode is None
        # the worker must take the sslmode from its own pg_service.conf
        assert "sslmode" not in source.to_qgis_decoded_uri

    @pytest.mark.parametrize("serializer_class", [JsonSerializer, XmlSerializer])
    def test_service_credentials_are_not_serialized(self, config, serializer_class):
        output = serializer_class().render(config)
        assert "qsl_test" in output
        assert self.service_password not in output
        assert self.service_user not in output
        assert self.service_dbname not in output
