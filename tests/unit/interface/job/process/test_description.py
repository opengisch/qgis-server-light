import json

import pytest
from qgis.core import (
    Qgis,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExpression,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
)
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer
from xsdata.formats.dataclass.serializers.dict import DictFactory

from qgis_server_light.interface.job.process.description import (
    InputDescription,
    OutputDescription,
    ProcessDescription,
    ProcessDescriptions,
    QslLayerKind,
    QslLayerMarker,
    Schema,
)
from qgis_server_light.processing.description import ProcessDescriptionMapper

CENTROIDS = ProcessDescription(
    id="native:centroids",
    title="Centroids",
    description="This algorithm creates a new point layer with points representing the centroid of the geometries in an input layer.\n\nThe attributes associated to each point in the output layer are the same ones associated to the original features.",  # noqa: E501
    inputs=[
        InputDescription(
            id="INPUT",
            title="Input layer",
            schema=Schema(
                type="string",
                format="qsl-layer",
                x_qsl_layer=QslLayerMarker(
                    kind=QslLayerKind.VECTOR,
                    geometry_types=["Point", "Line", "Polygon", "Null"],
                    source="QgsProcessingParameterFeatureSource",
                ),
            ),
        ),
        InputDescription(
            id="ALL_PARTS",
            title="Create centroid for each part",
            schema=Schema(type="boolean", default=False),
        ),
    ],
    outputs=[
        OutputDescription(
            id="OUTPUT",
            title="Centroids",
            schema=Schema(
                one_of=[
                    Schema(type="string", content_media_type="application/geo+json"),
                    Schema(type="string", content_media_type="application/geopackage+sqlite3"),
                    Schema(type="string", content_media_type="application/flatgeobuf"),
                ]
            ),
        ),
    ],
)


def render(instance) -> dict:
    return json.loads(JsonSerializer(dict_factory=DictFactory.FILTER_NONE).render(instance))


def test_process_description_native_centroids(qgis_app):
    centroids = qgis_app.processingRegistry().algorithmById("native:centroids")
    assert ProcessDescriptionMapper().process_description(centroids) == CENTROIDS


def test_process_description_without_destinations(qgis_app):
    buffer = qgis_app.processingRegistry().algorithmById("native:buffer")
    description = ProcessDescriptionMapper().process_description(buffer)
    assert [input_description.id for input_description in description.inputs] == [
        "INPUT",
        "DISTANCE",
        "SEGMENTS",
        "END_CAP_STYLE",
        "JOIN_STYLE",
        "MITER_LIMIT",
        "DISSOLVE",
        "SEPARATE_DISJOINT",
    ]
    assert [output_description.id for output_description in description.outputs] == ["OUTPUT"]


@pytest.mark.parametrize(
    "parameter_name,expected",
    [
        (
            "SEGMENTS",
            {
                "id": "SEGMENTS",
                "title": "Segments",
                "description": "The segments parameter controls the number of line segments to use to approximate a quarter circle when creating rounded offsets.",  # noqa: E501
                "schema": {"type": "integer", "minimum": 1, "default": 5},
                "minOccurs": 1,
                "maxOccurs": 1,
            },
        ),
        (
            "END_CAP_STYLE",
            {
                "id": "END_CAP_STYLE",
                "title": "End cap style",
                "schema": {
                    "type": "integer",
                    "default": 0,
                    "oneOf": [
                        {"title": "Round", "const": 0},
                        {"title": "Flat", "const": 1},
                        {"title": "Square", "const": 2},
                    ],
                },
                "minOccurs": 1,
                "maxOccurs": 1,
            },
        ),
        (
            "INPUT",
            {
                "id": "INPUT",
                "title": "Input layer",
                "schema": {
                    "type": "string",
                    "format": "qsl-layer",
                    "x-qsl-layer": {
                        "kind": "vector",
                        "geometry_types": ["Point", "Line", "Polygon", "Null"],
                        "source": "QgsProcessingParameterFeatureSource",
                    },
                },
                "minOccurs": 1,
                "maxOccurs": 1,
            },
        ),
    ],
)
def test_input_description_native_buffer_json(qgis_app, parameter_name, expected):
    buffer = qgis_app.processingRegistry().algorithmById("native:buffer")
    param = buffer.parameterDefinition(parameter_name)
    assert render(ProcessDescriptionMapper().input_description(param)) == expected


@pytest.mark.parametrize(
    "param,expected_min_occurs,expected_max_occurs",
    [
        (
            QgsProcessingParameterMultipleLayers(
                "LAYERS", "Layers", Qgis.ProcessingSourceType.VectorPolygon
            ),
            1,
            "unbounded",
        ),
        (
            QgsProcessingParameterMultipleLayers(
                "LAYERS", "Layers", Qgis.ProcessingSourceType.VectorPolygon, optional=True
            ),
            0,
            "unbounded",
        ),
        (
            QgsProcessingParameterNumber("NUMBER", "Number", optional=True),
            0,
            1,
        ),
    ],
)
def test_input_description_occurs(param, expected_min_occurs, expected_max_occurs):
    input_description = ProcessDescriptionMapper().input_description(param)
    assert input_description.min_occurs == expected_min_occurs
    assert input_description.max_occurs == expected_max_occurs


def test_input_description_multiple_layers_minimum():
    param = QgsProcessingParameterMultipleLayers(
        "LAYERS", "Layers", Qgis.ProcessingSourceType.Raster
    )
    param.setMinimumNumberInputs(2)
    input_description = ProcessDescriptionMapper().input_description(param)
    assert input_description.min_occurs == 2
    assert input_description.schema.x_qsl_layer == QslLayerMarker(
        kind=QslLayerKind.RASTER,
        geometry_types=[],
        source="QgsProcessingParameterMultipleLayers",
    )


def test_input_description_number_with_lower_bound_zero():
    param = QgsProcessingParameterNumber(
        "NUMBER", "Number", Qgis.ProcessingNumberParameterType.Double, minValue=0
    )
    assert ProcessDescriptionMapper().input_description(param).schema == Schema(
        type="number", minimum=0.0
    )


def test_input_description_enum_static_strings():
    param = QgsProcessingParameterEnum(
        "ENUM", "Enum", options=["a", "b"], defaultValue="b", usesStaticStrings=True
    )
    assert ProcessDescriptionMapper().input_description(param).schema == Schema(
        type="string",
        default="b",
        one_of=[Schema(const="a", title="a"), Schema(const="b", title="b")],
    )


@pytest.mark.parametrize(
    "param,match",
    [
        (QgsProcessingParameterExpression("EXPRESSION", "Expression"), "unsupported parameter"),
        (
            QgsProcessingParameterEnum("ENUM", "Enum", options=["a"], allowMultiple=True),
            "unsupported enum with multiple options",
        ),
    ],
)
def test_input_description_unsupported(param, match):
    with pytest.raises(ValueError, match=match):
        ProcessDescriptionMapper().input_description(param)


@pytest.mark.parametrize(
    "source_types,expected_geometry_types",
    [
        ([], ["Point", "Line", "Polygon", "Null"]),
        ([Qgis.ProcessingSourceType.VectorAnyGeometry], ["Point", "Line", "Polygon"]),
        (
            [Qgis.ProcessingSourceType.VectorPoint, Qgis.ProcessingSourceType.VectorLine],
            ["Point", "Line"],
        ),
    ],
)
def test_input_description_feature_source(source_types, expected_geometry_types):
    param = QgsProcessingParameterFeatureSource("INPUT", "Input", types=source_types)
    schema = ProcessDescriptionMapper().input_description(param).schema
    assert schema.type == "string"
    assert schema.format == "qsl-layer"
    assert schema.x_qsl_layer == QslLayerMarker(
        kind=QslLayerKind.VECTOR,
        geometry_types=expected_geometry_types,
        source="QgsProcessingParameterFeatureSource",
    )


@pytest.mark.parametrize(
    "param,match",
    [
        (
            QgsProcessingParameterMultipleLayers(
                "LAYERS", "Layers", Qgis.ProcessingSourceType.Mesh
            ),
            "unsupported ProcessingSourceType",
        ),
        (
            QgsProcessingParameterFeatureSource(
                "INPUT",
                "Input",
                types=[Qgis.ProcessingSourceType.VectorPoint, Qgis.ProcessingSourceType.Raster],
            ),
            "mixed layer kinds",
        ),
    ],
)
def test_input_description_unsupported_layer(param, match):
    with pytest.raises(ValueError, match=match):
        ProcessDescriptionMapper().input_description(param)


def test_process_descriptions_json_roundtrip():
    process_descriptions = ProcessDescriptions(processes=[CENTROIDS])
    process_descriptions_json = JsonSerializer(dict_factory=DictFactory.FILTER_NONE).render(
        process_descriptions
    )
    assert (
        JsonParser().from_string(process_descriptions_json, ProcessDescriptions)
        == process_descriptions
    )


def test_process_by_id():
    process_descriptions = ProcessDescriptions(processes=[CENTROIDS])
    assert process_descriptions.process_by_id("native:centroids") is CENTROIDS
    with pytest.raises(LookupError, match="native:buffer` is not described"):
        process_descriptions.process_by_id("native:buffer")
