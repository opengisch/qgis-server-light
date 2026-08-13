import pytest

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobLayer,
)
from qgis_server_light.interface.job.legend.input import (
    QslJobInfoLegend,
    QslJobParameterLegend,
)
from tests.base.dataclass_test import DataclassTest


class TestQslJobParameterLegend(DataclassTest):
    field_defs = [
        ("layers", list[QslJobLayer]),
        ("format", str),
        ("width", int | None),
        ("height", int | None),
        ("dpi", int),
        ("scale", float | None),
        ("layer_title", bool),
    ]
    field_defaults = [
        ("format", "image/png"),
        ("width", None),
        ("height", None),
        ("dpi", 96),
        ("scale", None),
        ("layer_title", False),
    ]
    dataclass_to_test = QslJobParameterLegend

    def test_instantiation(self):
        job_param = QslJobParameterLegend(
            layers=[
                QslJobLayer(
                    id="ididid",
                    name="testlayer",
                    source="1.1.1.1",
                    remote=True,
                    folder_name="data",
                    driver="dbio",
                )
            ]
        )
        assert isinstance(job_param.layers, list)
        assert isinstance(job_param.layers[0], QslJobLayer)
        assert job_param.format == "image/png"

    def test_get_dataset_by_name(self):
        job_param = QslJobParameterLegend(
            layers=[
                QslJobLayer(
                    id="ididid",
                    name="testlayer",
                    source="1.1.1.1",
                    remote=True,
                    folder_name="data",
                    driver="dbio",
                )
            ]
        )
        assert isinstance(job_param.get_layer_by_name("testlayer"), QslJobLayer)

    def test_get_dataset_by_name_raises(self):
        job_param = QslJobParameterLegend(layers=[])
        with pytest.raises(LookupError):
            job_param.get_layer_by_name("testlayer")


class TestQslJobInfoLegend(DataclassTest):
    field_defs = [
        ("job", QslJobParameterLegend),
    ]
    dataclass_to_test = QslJobInfoLegend

    def test_instantiation(self):
        job_info = QslJobInfoLegend(
            id="lsadjlajs",
            type=QslJobInfoLegend.__name__,
            job=QslJobParameterLegend(layers=[]),
        )
        assert isinstance(job_info.job, QslJobParameterLegend)

    def test_super(self):
        assert issubclass(QslJobInfoLegend, QslJobInfoParameter)
