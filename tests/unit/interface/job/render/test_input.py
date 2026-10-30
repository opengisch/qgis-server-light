import pytest

from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobLayer,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)
from tests.base.dataclass_test import DataclassTest


class TestQslJobParameterRender(DataclassTest):
    field_defs = [
        ("layers", list[QslJobLayer]),
        ("bbox", BBox),
        ("crs", str),
        ("width", int),
        ("height", int),
        ("dpi", int | None),
        ("format", str),
    ]
    field_defaults = [
        ("dpi", None),
        ("format", "image/png"),
    ]
    dataclass_to_test = QslJobParameterRender

    def test_instantiation(self):
        """Check that we can instantiate with some values"""
        job_param = QslJobParameterRender(
            layers=[
                QslJobLayer(
                    id="ididid",
                    name="testlayer",
                    source="1.1.1.1",
                    remote=True,
                    folder_name="data",
                    driver="dbio",
                )
            ],
            bbox=BBox(1.0, 2.0, 1.0, 2.0),
            crs="EPSG:4620",
            width=100,
            height=100,
        )

        assert isinstance(job_param.layers, list)
        assert isinstance(job_param.layers[0], QslJobLayer)
        assert isinstance(job_param.bbox, BBox)
        assert job_param.crs == "EPSG:4620"
        assert job_param.width == 100
        assert job_param.height == 100

    def test_get_dataset_by_name(self):
        job_param = QslJobParameterRender(
            layers=[
                QslJobLayer(
                    id="ididid",
                    name="testlayer",
                    source="1.1.1.1",
                    remote=True,
                    folder_name="data",
                    driver="dbio",
                )
            ],
            bbox=BBox(1.0, 2.0, 1.0, 2.0),
            crs="EPSG:4620",
            width=100,
            height=100,
        )
        assert isinstance(job_param.get_layer_by_name("testlayer"), QslJobLayer)

    def test_get_dataset_by_name_raises(self):
        job_param = QslJobParameterRender(
            layers=[],
            bbox=BBox(1.0, 2.0, 1.0, 2.0),
            crs="EPSG:4620",
            width=100,
            height=100,
        )
        with pytest.raises(LookupError):
            job_param.get_layer_by_name("testlayer")


class TestQslJobInfoRender(DataclassTest):
    field_defs = [
        ("job", QslJobParameterRender),
    ]
    dataclass_to_test = QslJobInfoRender

    def test_instantiation(self):
        job_info = QslJobInfoRender(
            id="lsadjlajs",
            type=QslJobInfoRender.__name__,
            job=QslJobParameterRender(
                layers=[
                    QslJobLayer(
                        id="ididid",
                        name="testlayer",
                        source="1.1.1.1",
                        remote=True,
                        folder_name="data",
                        driver="dbio",
                    )
                ],
                bbox=BBox(1.0, 2.0, 1.0, 2.0),
                crs="EPSG:4620",
                width=100,
                height=100,
            ),
        )
        assert isinstance(job_info.job, QslJobParameterRender)

    def test_super(self):
        assert issubclass(QslJobInfoRender, QslJobInfoParameter)
