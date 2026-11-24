import re
from pathlib import Path

import pytest
from qgis.core import (
    NULL,
    Qgis,
    QgsAnnotationLayer,
    QgsCoordinateReferenceSystem,
    QgsEditorWidgetSetup,
    QgsField,
    QgsFieldConstraints,
    QgsProject,
    QgsProjectVersion,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsRelation,
    QgsRelationContext,
    QgsValueMapFieldFormatter,
    QgsVectorLayer,
)
from xsdata.formats.dataclass.serializers import JsonSerializer, XmlSerializer

from qgis_server_light.exporter.exceptions import ExportFailure
from qgis_server_light.exporter.extract import Exporter
from qgis_server_light.interface.exporter.extract import (
    ExportMessage,
    FieldConstraints,
    Range,
    Relation,
    RelationFieldPair,
    RelationReference,
    ValueMap,
    ValueMapEntry,
    ValueRelation,
    WcsSource,
)


@pytest.fixture
def qgis_project(qgis_app):
    project = QgsProject.instance()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
    try:
        yield project
    finally:
        project.clear()


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
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
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
    def config(self, project_path, monkeypatch):
        # The fake PG source is expected to be invalid, exporting it is the test's purpose.
        monkeypatch.setattr(Exporter, "is_layer_valid", staticmethod(lambda _layer: True))
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

    @pytest.fixture(autouse=True)
    def mock_layer_validity(self, monkeypatch):
        # The example URL fails provider validation.
        # Here we only check is url part is properly decoded.
        monkeypatch.setattr(
            Exporter,
            "is_layer_valid",
            staticmethod(lambda layer: "url=https://" in layer.dataProvider().dataSourceUri()),
        )

    @staticmethod
    def write_project(
        tmp_path,
        layer_uri: str,
        version: str | None = None,
    ) -> str:
        project = QgsProject()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
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

    def test_qgis4_shapefile_null_and_none_values_are_not_encoded(self, qgis_app, tmp_path):
        source_path = str(tmp_path / "regions.shp")
        layer = QgsVectorLayer(source_path, "regions", "ogr")
        decoded = QgsProviderRegistry.instance().decodeUri("ogr", layer.source())
        assert decoded["layerId"] is None
        assert decoded["layerName"] == NULL
        exporter = object.__new__(Exporter)
        exporter.version = QgsProjectVersion(4, 0, 0)
        exporter.rewrite_datasource_with_qgis3_compatible_uri(layer)
        assert layer.source() == source_path

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
    def config(self, qgis_app, tmp_path, monkeypatch):
        project = QgsProject()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
        project.addMapLayer(QgsRasterLayer(self.wcs_uri, "my_wcs", "wcs"))
        path = tmp_path / "project.qgs"
        assert project.write(str(path))
        # The fake provider is expected to be invalid, but we still want to export it.
        monkeypatch.setattr(Exporter, "is_layer_valid", staticmethod(lambda _layer: True))
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


class TestFieldConstraints:
    """
    The constraints are exported as flags, the expression only if QGIS has one. The
    expression constraint flag alone does not tell anything without the expression.
    """

    @pytest.mark.parametrize(
        "constraints,expression,expected",
        [
            ([], "", FieldConstraints(not_null=False, unique=False, expression=None)),
            ([NOT_NULL], "", FieldConstraints(not_null=True, unique=False, expression=None)),
            ([UNIQUE], "", FieldConstraints(not_null=False, unique=True, expression=None)),
            (
                [NOT_NULL, UNIQUE],
                "",
                FieldConstraints(not_null=True, unique=True, expression=None),
            ),
            (
                [EXPRESSION],
                '"height" > 0',
                FieldConstraints(not_null=False, unique=False, expression='"height" > 0'),
            ),
        ],
    )
    def test_create_qsl_field_constraints(self, constraints, expression, expected):
        field = QgsField("height")
        field_constraints = field.constraints()
        for constraint in constraints:
            field_constraints.setConstraint(constraint)
        field_constraints.setConstraintExpression(expression)
        field.setConstraints(field_constraints)
        assert Exporter.create_qsl_field_constraints(field) == expected

    def test_field_carries_its_constraints(self):
        field = QgsField("height")
        field_constraints = field.constraints()
        field_constraints.setConstraint(NOT_NULL)
        field.setConstraints(field_constraints)
        # the constraints travel with the exported field, the nullable flag next to it
        # stays as it was
        qsl_field = Exporter.create_qsl_field_from_qgis_field(field, is_primary_key=False)
        assert qsl_field.constraints == FieldConstraints(not_null=True, unique=False)
        assert qsl_field.nullable is False


class TestValueMap:
    """
    QGIS knows two forms of the value map configuration: the current one, a list of
    single entry dicts, and the old one, a single dict. Both map description to key.
    """

    @pytest.mark.parametrize(
        "config,expected",
        [
            # current form, the order of QGIS is kept
            (
                {"map": [{"Forest": "F"}, {"Meadow": "M"}, {"Lake": "L"}]},
                ValueMap(
                    entries=[
                        ValueMapEntry(key="F", description="Forest"),
                        ValueMapEntry(key="M", description="Meadow"),
                        ValueMapEntry(key="L", description="Lake"),
                    ]
                ),
            ),
            # old form, one dict holding all entries
            (
                {"map": {"Forest": "F", "Meadow": "M"}},
                ValueMap(
                    entries=[
                        ValueMapEntry(key="F", description="Forest"),
                        ValueMapEntry(key="M", description="Meadow"),
                    ]
                ),
            ),
            # keys which are no strings are exported as strings
            (
                {"map": [{"one": 1}, {"two": 2}]},
                ValueMap(
                    entries=[
                        ValueMapEntry(key="1", description="one"),
                        ValueMapEntry(key="2", description="two"),
                    ]
                ),
            ),
            # no map configured at all
            ({}, ValueMap(entries=[])),
        ],
    )
    def test_create_qsl_value_map(self, config, expected):
        assert Exporter.create_qsl_value_map(config) == expected

    def test_null_entry_becomes_the_null_representation(self):
        config = {
            "map": [
                {"<unknown>": QgsValueMapFieldFormatter.NULL_VALUE},
                {"Forest": "F"},
            ]
        }
        value_map = Exporter.create_qsl_value_map(config)
        # the NULL entry is no selectable value, it only tells how NULL is shown
        assert value_map.entries == [ValueMapEntry(key="F", description="Forest")]
        assert value_map.null_representation == "<unknown>"


class TestEditorWidget:
    """
    Only the editor widgets which define value lists or domains are exported, all
    others end up as None. The exported one is the definition of the editor widget.
    """

    @pytest.mark.parametrize(
        "widget_type,config,expected_definition",
        [
            (
                "ValueMap",
                {"map": [{"Forest": "F"}]},
                ValueMap(entries=[ValueMapEntry(key="F", description="Forest")]),
            ),
            (
                "ValueRelation",
                {
                    "Layer": "land_use_types_3f1c",
                    "Key": "code",
                    "Value": "label",
                    "FilterExpression": '"active" = true',
                    "AllowMulti": True,
                    "OrderByValue": True,
                },
                ValueRelation(
                    layer_id="land_use_types_3f1c",
                    key_field="code",
                    value_field="label",
                    filter_expression='"active" = true',
                    allow_multi=True,
                    order_by_value=True,
                ),
            ),
            (
                "RelationReference",
                {"Relation": "parcels_owners_rel"},
                RelationReference(relation_id="parcels_owners_rel"),
            ),
            (
                "Range",
                {"Min": 0, "Max": "100", "Step": 0.5},
                Range(minimum=0.0, maximum=100.0, step=0.5),
            ),
        ],
    )
    def test_create_qsl_editor_widget(self, widget_type, config, expected_definition):
        setup = QgsEditorWidgetSetup(widget_type, config)
        editor_widget = Exporter.create_qsl_editor_widget(setup)
        assert editor_widget.definition == expected_definition

    @pytest.mark.parametrize("widget_type", ["TextEdit", "DateTime", "CheckBox", ""])
    def test_other_editor_widgets_are_not_exported(self, widget_type):
        setup = QgsEditorWidgetSetup(widget_type, {})
        assert Exporter.create_qsl_editor_widget(setup) is None

    def test_value_relation_defaults(self):
        # QGIS writes an empty filter expression when none is set, it must not reach the
        # consumer as a filter
        config = {
            "Layer": "land_use_types_3f1c",
            "Key": "code",
            "Value": "label",
            "FilterExpression": "",
        }
        assert Exporter.create_qsl_value_relation(config) == ValueRelation(
            layer_id="land_use_types_3f1c",
            key_field="code",
            value_field="label",
            filter_expression=None,
            allow_multi=False,
            order_by_value=False,
        )

    def test_range_without_limits(self):
        assert Exporter.create_qsl_range({}) == Range(minimum=None, maximum=None, step=None)

    def test_field_carries_its_editor_widget(self):
        field = QgsField("land_use")
        field.setEditorWidgetSetup(QgsEditorWidgetSetup("ValueMap", {"map": [{"Forest": "F"}]}))
        qsl_field = Exporter.create_qsl_field_from_qgis_field(field, is_primary_key=False)
        assert qsl_field.editor_widget.value_map == ValueMap(
            entries=[ValueMapEntry(key="F", description="Forest")]
        )


class TestGeneratedPrimaryKey:
    """
    A primary key is generated when the source assigns it on insert. OGR always does
    (GeoPackage fid, ...), other providers tell it with a default value clause.
    """

    def test_ogr_primary_key_is_generated(self, qgis_app, data_path, tmp_path):
        qgis_project = QgsProject()
        layer = QgsVectorLayer(
            f"{Path(data_path).resolve()}/data/placenames.gpkg|layername=placenames",
            "placenames",
            "ogr",
        )
        qgis_project.addMapLayer(layer)
        path = tmp_path / "project.qgs"
        assert qgis_project.write(str(path))
        exporter = Exporter(str(path))

        fields = exporter.create_qsl_fields_from_qgis_field(layer)
        # the fid is the primary key of the GeoPackage and assigned by GDAL
        fid = fields[0]
        assert fid.name == "fid"
        assert fid.is_primary_key is True
        assert fid.is_generated is True
        # all the others are neither primary key nor generated
        for field in fields[1:]:
            assert field.is_primary_key is False
            assert field.is_generated is False

    def test_provider_without_default_value_does_not_generate(self, qgis_app):
        layer = QgsVectorLayer("Point?field=id:integer", "memory", "memory")
        # the memory provider has no default value clause, nothing is generated
        assert Exporter.obtain_is_generated(layer.dataProvider(), 0) is False


class TestExportMessages:
    def test_unreadable_project_fails_with_a_structured_error(self, qgis_app, tmp_path):
        path = tmp_path / "broken.qgs"
        path.write_text("not xml")

        with pytest.raises(ExportFailure) as exc_info:
            Exporter(str(path)).run()

        assert [(m.level, m.code) for m in exc_info.value.messages] == [
            (ExportMessage.Level.ERROR, ExportMessage.Code.PROJECT_READ_FAILED)
        ]

    def test_wgs84_reprojection_failure_is_structured(self, qgis_project, tmp_path):
        layer = QgsVectorLayer(
            "?query=SELECT ST_GeomFromText('LINESTRING(-1e9 -1e9, 1e9 1e9)', 3035) AS geometry"
            "&geometry=geometry:2:3035",  # 2 = LineString, 3035 = SRID
            "line",
            "virtual",
        )
        assert layer.isValid()

        qgis_project.setCrs(layer.crs())
        qgis_project.addMapLayer(layer)
        layer_id = layer.id()
        path = tmp_path / "project.qgs"
        assert qgis_project.write(str(path))

        with pytest.raises(ExportFailure) as exc_info:
            Exporter(str(path)).run()

        assert [(m.level, m.code, m.layer_id) for m in exc_info.value.messages] == [
            (
                ExportMessage.Level.ERROR,
                ExportMessage.Code.LAYER_EXTENT_REPROJECTION_FAILED,
                layer_id,
            ),
        ]

    def test_unhandled_field_editor_widget_is_reported(self, qgis_project, data_path, tmp_path):
        layer = QgsVectorLayer(
            f"{Path(data_path).resolve()}/data/placenames.gpkg|layername=placenames",
            "places",
            "ogr",
        )
        layer.setEditorWidgetSetup(0, QgsEditorWidgetSetup("UnsupportedWidget", {}))
        qgis_project.addMapLayer(layer)
        layer_id = layer.id()
        path = tmp_path / "project.qgs"
        assert qgis_project.write(str(path))

        config = Exporter(str(path)).run()

        assert any(
            m.code == ExportMessage.Code.FIELD_EDITOR_WIDGET_TYPE_UNSUPPORTED
            and m.layer_id == layer_id
            and "fid" in m.message
            for m in config.messages
        )

    def test_unsupported_layer_type_is_reported(self, qgis_project, tmp_path):
        layer = QgsAnnotationLayer(
            "my_annotations", QgsAnnotationLayer.LayerOptions(qgis_project.transformContext())
        )
        qgis_project.addMapLayer(layer)
        layer_id = layer.id()
        path = tmp_path / "project.qgs"
        assert qgis_project.write(str(path))

        config = Exporter(str(path)).run()

        assert config.datasets.custom == []
        assert [(m.level, m.code, m.layer_id) for m in config.messages] == [
            (ExportMessage.Level.WARNING, ExportMessage.Code.LAYER_TYPE_UNSUPPORTED, layer_id)
        ]


class TestRelations:
    """
    All relations of the project are exported with their layers as QGIS layer ids, the
    consumer resolves them.
    """

    def test_create_qsl_relations(self, qgis_app):
        project = QgsProject()
        owners = QgsVectorLayer(
            "None?field=id:integer&field=country:string&field=name:string", "owners", "memory"
        )
        parcels = QgsVectorLayer(
            "Polygon?field=id:integer&field=owner_id:integer&field=owner_country:string",
            "parcels",
            "memory",
        )
        project.addMapLayers([owners, parcels])
        # a parcel references its owner by a composite key, the relation needs the
        # context of our project, otherwise it looks for the layers in the global one
        relation = QgsRelation(QgsRelationContext(project))
        relation.setId("parcels_owners_rel")
        relation.setName("Parcel owner")
        relation.setReferencingLayer(parcels.id())
        relation.setReferencedLayer(owners.id())
        relation.addFieldPair("owner_id", "id")
        relation.addFieldPair("owner_country", "country")
        relation.setStrength(Qgis.RelationshipStrength.Composition)
        project.relationManager().addRelation(relation)

        # PyQGIS hands the field pairs over as a dict built from a QMap, so they come
        # sorted by the referencing field and not in the order they were added
        assert Exporter.create_qsl_relations(project) == [
            Relation(
                id="parcels_owners_rel",
                name="Parcel owner",
                referencing_layer_id=parcels.id(),
                referenced_layer_id=owners.id(),
                field_pairs=[
                    RelationFieldPair(
                        referencing_field="owner_country", referenced_field="country"
                    ),
                    RelationFieldPair(referencing_field="owner_id", referenced_field="id"),
                ],
                strength="Composition",
            )
        ]

    def test_project_without_relations(self, qgis_app):
        assert Exporter.create_qsl_relations(QgsProject()) == []


class TestLayerCrs:
    """
    Some providers report no CRS (e.g. PostGIS geometry columns without SRID), the CRS
    of the layer is taken then.
    """

    def test_provider_crs_is_preferred(self, qgis_app):
        layer = QgsVectorLayer("Point?crs=EPSG:2056", "with_crs", "memory")
        # a layer CRS overridden in the project does not change what the data is in
        layer.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        assert Exporter.create_qsl_crs_from_qgs_layer(layer).auth_id == "EPSG:2056"

    def test_layer_crs_is_taken_when_provider_has_none(self, qgis_app):
        # without any crs parameter the memory provider falls back to EPSG:4326, only an
        # empty one leaves it without CRS
        layer = QgsVectorLayer("Point?crs=", "without_crs", "memory")
        assert not layer.dataProvider().crs().isValid()
        layer.setCrs(QgsCoordinateReferenceSystem("EPSG:2056"))
        assert Exporter.create_qsl_crs_from_qgs_layer(layer).auth_id == "EPSG:2056"
