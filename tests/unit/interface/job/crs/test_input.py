from qgis_server_light.interface.job.common.input import (
    ExecutionMode,
    QslJobInfoParameter,
    QslJobParameter,
)
from qgis_server_light.interface.job.crs.input import QslJobInfoCrs, QslJobParameterCrs
from tests.base.dataclass_test import DataclassTest


class TestQslJobParameterCrs(DataclassTest):
    field_defs = [
        ("identifiers", list[str]),
    ]
    dataclass_to_test = QslJobParameterCrs

    def test_instantiation(self):
        job_param = QslJobParameterCrs(identifiers=["EPSG:4326", "urn:ogc:def:crs:EPSG::2056"])
        assert job_param.identifiers == ["EPSG:4326", "urn:ogc:def:crs:EPSG::2056"]

    def test_super(self):
        assert issubclass(QslJobParameterCrs, QslJobParameter)


class TestQslJobInfoCrs(DataclassTest):
    field_defs = [
        ("job", QslJobParameterCrs),
    ]
    dataclass_to_test = QslJobInfoCrs

    def test_instantiation(self):
        job_info = QslJobInfoCrs(
            id="lsadjlajs",
            type=QslJobInfoCrs.__name__,
            job=QslJobParameterCrs(identifiers=["EPSG:4326"]),
            execution_mode=ExecutionMode.SYNC,
        )
        assert isinstance(job_info.job, QslJobParameterCrs)

    def test_super(self):
        assert issubclass(QslJobInfoCrs, QslJobInfoParameter)
