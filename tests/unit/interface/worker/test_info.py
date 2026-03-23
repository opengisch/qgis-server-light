import math

from qgis_server_light.interface.worker.info import (
    Algorithm,
    EngineInfo,
    FeatureInfo,
    Features,
    Legend,
    Output,
    Parameter,
    Process,
    QgisInfo,
    Render,
    Status,
)
from tests.base.dataclass_test import DataclassTest
from tests.base.enum_test import EnumTest


class TestStatus(EnumTest):
    enum_names = {
        "STARTING",
        "CRASHED",
        "WAITING",
        "PROCESSING",
    }
    enum_values = {
        "starting",
        "crashed",
        "waiting",
        "processing",
    }
    enum_class_to_test = Status


class TestMap(DataclassTest):
    field_defs = [("formats", list[str])]
    dataclass_to_test = Render

    def test_instantiation(self):
        render = Render(formats=["image/png"])
        assert isinstance(render.formats, list)
        assert isinstance(render.formats[0], str)


class TestFeature(DataclassTest):
    dataclass_to_test = Features


class TestFeatureInfo(DataclassTest):
    dataclass_to_test = FeatureInfo


class TestMapLegend(DataclassTest):
    dataclass_to_test = Legend


class TestParameter(DataclassTest):
    field_defs = [("name", str), ("type", str), ("description", str | None)]
    field_defaults = [("description", None)]
    dataclass_to_test = Parameter

    def test_instantiation(self):
        parameter = Parameter(
            name="layer_path", type="str", description="This a longer text"
        )
        assert parameter.name == "layer_path"
        assert parameter.type == "str"
        assert parameter.description == "This a longer text"

    def test_configured_shortened_fields(self):
        parameter = Parameter(
            name="layer_path", type="str", description="This a longer text"
        )
        assert parameter.shortened_fields == {"description"}


class TestOutput(DataclassTest):
    field_defs = [("name", str), ("type", str), ("description", str | None)]
    field_defaults = [("description", None)]
    dataclass_to_test = Output

    def test_instantiation(self):
        output = Output(
            name="path_to_result", type="str", description="This a longer text"
        )
        assert output.name == "path_to_result"
        assert output.type == "str"
        assert output.description == "This a longer text"

    def test_configured_shortened_fields(self):
        output = Output(
            name="path_to_result", type="str", description="This a longer text"
        )
        assert output.shortened_fields == {"description"}


class TestAlgorithm(DataclassTest):
    field_defs = [
        ("id", str),
        ("name", str),
        ("display_name", str),
        ("help_string", str | None),
        ("parameters", list[Parameter]),
        ("outputs", list[Output]),
    ]
    field_defaults = [
        ("help_string", None),
    ]
    field_default_factories = [
        ("parameters", list),
        ("outputs", list),
    ]
    dataclass_to_test = Algorithm

    def test_instantiation(self):
        algorythm = Algorithm(
            id="abc",
            name="buffer",
            display_name="Calculate Buffer",
            help_string="RTFM",
            parameters=[
                Parameter(
                    name="layer_path", type="str", description="This a longer text"
                )
            ],
            outputs=[
                Output(
                    name="path_to_result", type="str", description="This a longer text"
                )
            ],
        )
        assert algorythm.id == "abc"
        assert algorythm.name == "buffer"
        assert algorythm.display_name == "Calculate Buffer"
        assert algorythm.help_string == "RTFM"
        assert isinstance(algorythm.parameters, list)
        assert isinstance(algorythm.parameters[0], Parameter)
        assert isinstance(algorythm.outputs, list)
        assert isinstance(algorythm.outputs[0], Output)


class TestProcess(DataclassTest):
    field_defs = [("algorithms", list[Algorithm])]
    field_default_factories = [("algorithms", list)]
    dataclass_to_test = Process

    def test_instantiation(self):
        process = Process(
            algorithms=[
                Algorithm(
                    id="abc",
                    name="buffer",
                    display_name="Calculate Buffer",
                )
            ]
        )
        assert isinstance(process.algorithms, list)
        assert isinstance(process.algorithms[0], Algorithm)


class TestQgisInfo(DataclassTest):
    field_defs = [
        ("version", str),
        ("path", str),
        ("providers", list[str]),
    ]
    dataclass_to_test = QgisInfo

    def test_instantiation(self):
        qgis_info = QgisInfo(version="3.44", path="/usr", providers=["OGR", "GDAL"])
        assert qgis_info.version == "3.44"
        assert qgis_info.path == "/usr"
        assert isinstance(qgis_info.providers, list)
        assert isinstance(qgis_info.providers[0], str)


class TestEngineInfo(DataclassTest):
    field_defs = [
        ("id", str),
        ("qgis_info", QgisInfo),
        ("status", Status),
        ("started", float),
        (
            "runner_infos",
            list[Render | FeatureInfo | Features | Process | Legend],
        ),
    ]
    field_default_factories = [("runner_infos", list)]
    dataclass_to_test = EngineInfo

    def test_instantiation(self):
        engine_info = EngineInfo(
            id="ididi",
            qgis_info=QgisInfo(version="3.44", path="/usr", providers=["OGR", "GDAL"]),
            status=Status.STARTING,
            started=123.0,
        )
        assert engine_info.id == "ididi"
        assert isinstance(engine_info.qgis_info, QgisInfo)
        assert engine_info.status == Status.STARTING
        assert math.isclose(engine_info.started, 123.0)
