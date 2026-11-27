import pytest
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.job.process.output import (
    ProcessResult,
    Reference,
    ResultOutput,
)
from tests.base.dataclass_test import DataclassTest


class TestReference(DataclassTest):
    field_defs = [
        ("href", str),
        ("type", str),
    ]
    dataclass_to_test = Reference

    def test_instantiation(self):
        reference = Reference(href="a1b2/OUTPUT.gpkg", type="application/geopackage+sqlite3")
        assert reference.href == "a1b2/OUTPUT.gpkg"
        assert reference.type == "application/geopackage+sqlite3"


class TestResultOutput(DataclassTest):
    field_defs = [
        ("id", str),
        ("value", Reference | str | int | float | bool),
    ]
    dataclass_to_test = ResultOutput

    def test_instantiation(self):
        result_output = ResultOutput(id="OUTPUT", value="/io/data/Centroids.geojson")
        assert result_output.id == "OUTPUT"
        assert result_output.value == "/io/data/Centroids.geojson"


class TestProcessResult(DataclassTest):
    field_defs = [
        ("outputs", list[ResultOutput]),
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
                    ResultOutput(id="OUTPUT", value="/io/data/Centroids.geojson"),
                    ResultOutput(id="FEATURE_COUNT", value=42),
                    ResultOutput(id="AREA", value=1.5),
                    ResultOutput(id="OK", value=True),
                ],
                log="Processing finished",
            ),
            ProcessResult(
                outputs=[
                    ResultOutput(
                        id="OUTPUT",
                        value=Reference(
                            href="a1b2/OUTPUT.gpkg", type="application/geopackage+sqlite3"
                        ),
                    ),
                    ResultOutput(id="FEATURE_COUNT", value=42),
                ],
            ),
        ],
    )
    def test_json_roundtrip(self, process_result):
        process_result_json = JsonSerializer().render(process_result).encode()
        assert JsonParser().from_bytes(process_result_json, ProcessResult) == process_result
