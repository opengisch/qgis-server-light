import math

from qgis_server_light.interface.worker.info import (
    EngineInfo,
    QgisInfo,
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


class TestQgisInfo(DataclassTest):
    field_defs = [
        ("version", int),
        ("version_name", str),
        ("path", str),
    ]
    dataclass_to_test = QgisInfo

    def test_instantiation(self):
        qgis_info = QgisInfo(version_name="3.44", version=340000, path="/usr")
        assert qgis_info.version_name == "3.44"
        assert qgis_info.version == 340000
        assert qgis_info.path == "/usr"


class TestEngineInfo(DataclassTest):
    field_defs = [
        ("id", str),
        ("qgis_info", QgisInfo),
        ("status", Status),
        ("started", float),
    ]
    dataclass_to_test = EngineInfo

    def test_instantiation(self):
        engine_info = EngineInfo(
            id="ididi",
            qgis_info=QgisInfo(version_name="3.44", version=340000, path="/usr"),
            status=Status.STARTING,
            started=123.0,
        )
        assert engine_info.id == "ididi"
        assert isinstance(engine_info.qgis_info, QgisInfo)
        assert engine_info.status == Status.STARTING
        assert math.isclose(engine_info.started, 123.0)
