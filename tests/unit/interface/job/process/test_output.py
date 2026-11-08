import pytest
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.job.process.output import ParameterOutput, ProcessResult
from tests.base.dataclass_test import DataclassTest


class TestParameterOutput(DataclassTest):
    field_defs = [
        ("name", str),
        ("value", str | int | float | bool),
    ]
    dataclass_to_test = ParameterOutput

    def test_instantiation(self):
        parameter_output = ParameterOutput(name="OUTPUT", value="/io/data/Centroids.geojson")
        assert parameter_output.name == "OUTPUT"
        assert parameter_output.value == "/io/data/Centroids.geojson"


class TestProcessResult(DataclassTest):
    field_defs = [
        ("outputs", list[ParameterOutput]),
        ("log", str),
    ]
    field_defaults = [
        ("log", ""),
    ]
    field_default_factories = [
        ("outputs", list),
    ]
    dataclass_to_test = ProcessResult

    def test_super(self):
        assert issubclass(ProcessResult, BaseInterface)

    def test_configured_shortened_fields(self):
        assert ProcessResult().shortened_fields == {"log"}

    @pytest.mark.parametrize(
        "process_result",
        [
            ProcessResult(),
            ProcessResult(
                outputs=[
                    ParameterOutput(name="OUTPUT", value="/io/data/Centroids.geojson"),
                    ParameterOutput(name="FEATURE_COUNT", value=42),
                    ParameterOutput(name="AREA", value=1.5),
                    ParameterOutput(name="OK", value=True),
                ],
                log="Processing finished",
            ),
        ],
    )
    def test_json_roundtrip(self, process_result):
        process_result_json = JsonSerializer().render(process_result).encode()
        assert JsonParser().from_bytes(process_result_json, ProcessResult) == process_result
