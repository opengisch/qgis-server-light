import re

import pytest
from qgis.core import (
    Qgis,
    QgsField,
    QgsFieldConstraints,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)
from xsdata.formats.dataclass.serializers import JsonSerializer, XmlSerializer

from qgis_server_light.exporter.extract import Exporter
from qgis_server_light.interface.exporter.extract import WcsSource


class TestCreateQslSourcePostgresql:
    def test_explicit_sslmode_is_kept(self):
        # decoded datasources are stringified by Exporter.extract_datasource_dict()
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
    def project_path(self, qgis_app, tmp_path, monkeypatch):
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


class TestQgis4DatasourceDecoding:
    """
    QGIS >= 4 percent-encodes reserved characters inside datasource query values. The
    project is written by the QGIS 3 build of the test run and its save version is set
    to 4 afterwards, as if it was saved by QGIS 4.
    """

    @staticmethod
    def write_project(
        tmp_path,
        layer_uri: str,
        version: str | None = None,
    ) -> str:
        project = QgsProject()
        project.addMapLayer(QgsRasterLayer(layer_uri, "my_background", "wms"))
        path = tmp_path / "project.qgs"
        assert project.write(str(path))
        if version:
            content = path.read_text()
            path.write_text(re.sub(r'(<qgis [^>]*version=")[^"]*', rf"\g<1>{version}", content))
        return str(path)

    @pytest.fixture
    def qgis3_config(self, qgis_app, tmp_path):
        qgis3_encoded_url = "https://wms.example.com/wms?map%3Dbase"
        layer_uri = (
            "contextualWMSLegend=0&crs=EPSG:2056&format=image/png&layers=base%2525"
            f"&styles&url={qgis3_encoded_url}"
        )
        assert Qgis.version().startswith("3.")
        yield Exporter(self.write_project(tmp_path, layer_uri)).run()
        QgsProject.instance().clear()

    @pytest.fixture
    def qgis4_config(self, qgis_app, tmp_path):
        qgis4_encoded_url = "https%3A%2F%2Fwms.example.com%2Fwms%3Fmap%3Dbase"
        layer_uri = (
            "contextualWMSLegend=0&crs=EPSG%3A2056&format=image%2Fpng&layers=base%2525"
            f"&styles&url={qgis4_encoded_url}"
        )
        yield Exporter(self.write_project(tmp_path, layer_uri, version="4.0.0-Norrköping")).run()
        QgsProject.instance().clear()

    def test_qgis4_project_values_are_unquoted(self, qgis4_config):
        assert qgis4_config.project.version == "4.0.0-Norrköping"
        source = qgis4_config.datasets.raster[0].source.wms
        assert source.url == "https://wms.example.com/wms?map=base"
        assert source.crs == "EPSG:2056"
        assert source.layers == "base%25"

    def test_qgis4_project_null_values_are_none(self, qgis4_config):
        assert qgis4_config.datasets.raster[0].source.wms.styles is None

    def test_qgis3_project_preserves_percent_encoded_url_values(self, qgis3_config):
        source = qgis3_config.datasets.raster[0].source.wms
        assert source.url == "https://wms.example.com/wms?map=base"
        assert source.layers == "base%2525"


class TestWcsExport:
    """
    Exports a project with a layer of the QGIS `wcs` provider and checks that it is
    exported as a raster whose source gives back the uri read by the provider. The
    service url is unreachable, the export must not depend on the remote service.
    """

    wcs_url = "http://127.0.0.1:1/wcs"
    # dpiMode and tilePixelRatio are written by QGIS in projects but are not read by
    # the wcs provider, they are not exported
    ignored_keys = ("dpiMode", "tilePixelRatio")
    wcs_uri = (
        "IgnoreGetMapUrl=1&bbox=2668500,1223000,2717500,1284000&cache=PreferNetwork"
        "&crs=EPSG:2056&dpiMode=7&format=image/tiff&identifier=vegetationshoehe"
        f"&tilePixelRatio=0&url={wcs_url}&version=1.0.0"
    )

    @pytest.fixture
    def config(self, qgis_app, tmp_path):
        project = QgsProject()
        project.addMapLayer(QgsRasterLayer(self.wcs_uri, "my_wcs", "wcs"))
        path = tmp_path / "project.qgs"
        assert project.write(str(path))
        yield Exporter(str(path)).run()
        QgsProject.instance().clear()

    def test_wcs_layer_is_exported_as_raster(self, config):
        assert len(config.datasets.raster) == 1
        raster = config.datasets.raster[0]
        assert raster.driver == "wcs"
        assert raster.source.definition is raster.source.wcs

    def test_workaround_is_enabled_by_the_presence_of_the_parameter(self):
        # QgsWcsProvider::parseUri only checks the presence of the parameter, "0"
        # enables the workaround as well
        source = WcsSource.from_qgis_decoded_uri(
            {"url": self.wcs_url, "identifier": "vegetationshoehe", "IgnoreGetMapUrl": "0"}
        )
        assert source.ignore_get_map_url is True
        assert source.to_qgis_decoded_uri["IgnoreGetMapUrl"] == "1"

    def test_wcs_source_round_trips_to_the_qgis_uri(self, config):
        source = config.datasets.raster[0].source.wcs
        decoded = QgsProviderRegistry.instance().decodeUri("wcs", self.wcs_uri)
        for key in self.ignored_keys:
            del decoded[key]
        assert source.to_qgis_decoded_uri == decoded


NOT_NULL = QgsFieldConstraints.Constraint.ConstraintNotNull
UNIQUE = QgsFieldConstraints.Constraint.ConstraintUnique
EXPRESSION = QgsFieldConstraints.Constraint.ConstraintExpression


class TestFieldNullable:
    """
    QgsFieldConstraints.constraints() is a bitmask, the NotNull constraint can be
    combined with others. Primary keys are never nullable.
    """

    @pytest.fixture
    def qgis_field(self, constraints):
        field = QgsField("attribute")
        field_constraints = field.constraints()
        for constraint in constraints:
            field_constraints.setConstraint(constraint)
        field.setConstraints(field_constraints)
        yield field

    @pytest.mark.parametrize(
        "constraints,expected",
        [
            ([], True),
            ([UNIQUE], True),
            ([EXPRESSION], True),
            ([NOT_NULL], False),
            ([NOT_NULL, UNIQUE], False),
            ([NOT_NULL, EXPRESSION], False),
            ([NOT_NULL, UNIQUE, EXPRESSION], False),
        ],
    )
    def test_obtain_nullable(self, qgis_field, expected):
        assert Exporter.obtain_nullable(qgis_field) is expected

    @pytest.mark.parametrize(
        "constraints,is_primary_key,expected",
        [
            ([], False, True),
            ([UNIQUE], False, True),
            ([NOT_NULL], False, False),
            ([NOT_NULL, UNIQUE], False, False),
            ([], True, False),
            ([NOT_NULL], True, False),
            ([NOT_NULL, UNIQUE], True, False),
        ],
    )
    def test_create_qsl_field_from_qgis_field_nullable(self, qgis_field, is_primary_key, expected):
        field = Exporter.create_qsl_field_from_qgis_field(qgis_field, is_primary_key)
        assert field.nullable is expected
