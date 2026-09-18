from qgis_server_light.interface.common import BaseInterface, Style
from qgis_server_light.interface.job.common.input import (
    AbstractFilter,
    OgcFilter110,
    OgcFilterFES20,
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
    QslJobParameterMapRelated,
)
from tests.base.dataclass_test import DataclassTest


class TestQslJobInfoParameter(DataclassTest):
    field_defs = [
        ("id", str),
        ("type", str),
        ("job", QslJobParameter),
    ]
    dataclass_to_test = QslJobInfoParameter

    def test_instantiation(
        self,
    ):
        QslJobInfoParameter.__abstractmethods__ = set()
        instance = QslJobInfoParameter(
            id="abc", type=QslJobInfoParameter.__name__, job=QslJobParameter()
        )
        assert instance.id == "abc"
        assert instance.type == "QslJobInfoParameter"
        assert isinstance(instance.job, QslJobParameter)


class TestQslJobParameterMapRelated(DataclassTest):
    field_defs = [
        ("svg_paths", list[str]),
    ]
    field_default_factories = [("svg_paths", list)]
    dataclass_to_test = QslJobParameterMapRelated

    def test_instantiation(self):
        job_param = QslJobParameterMapRelated(svg_paths=["test/tests/test"])
        assert job_param.svg_paths == ["test/tests/test"]


class TestAbstractFilter(DataclassTest):
    field_defs = [
        ("definition", str),
    ]
    dataclass_to_test = AbstractFilter

    def test_instantiation(self):
        abstract_filter = AbstractFilter(definition="test")
        assert abstract_filter.definition == "test"

    def test_super(self):
        assert issubclass(AbstractFilter, BaseInterface)

    def test_configured_shortened_fields(self):
        abstract_filter = AbstractFilter(definition="abcd")
        assert abstract_filter.shortened_fields == {"definition"}


class TestOgcFilter110:
    def test_super(self):
        assert issubclass(OgcFilter110, AbstractFilter)


class TestOgcFilterFES20:
    def test_super(self):
        assert issubclass(OgcFilterFES20, AbstractFilter)


class TestQslJobLayer(DataclassTest):
    field_defs = [
        ("id", str),
        ("name", str),
        ("source", str),
        ("remote", bool),
        ("folder_name", str),
        ("driver", str),
        ("style", Style | None),
        ("filter", OgcFilter110 | OgcFilterFES20 | None),
    ]
    field_defaults = [("style", None), ("filter", None)]
    dataclass_to_test = QslJobLayer

    def test_instantiation(self):
        job_layer = QslJobLayer(
            id="abcd",
            name="test",
            source="sourcestring",
            remote=False,
            folder_name="data",
            driver="ogr",
            style=Style(name="x", definition="xskdjaljl"),
            filter=OgcFilter110(definition="<xml>filterdefinition</xml>"),
        )
        assert job_layer.id == "abcd"
        assert job_layer.name == "test"
        assert job_layer.source == "sourcestring"
        assert not job_layer.remote
        assert job_layer.folder_name == "data"
        assert job_layer.driver == "ogr"
        assert isinstance(job_layer.style, Style)
        assert isinstance(job_layer.filter, OgcFilter110)

    def test_super(self):
        assert issubclass(QslJobLayer, BaseInterface)

    def test_configured_redacted_fields(self):
        job_layer = QslJobLayer(
            id="abcd",
            name="test",
            source="sourcestring",
            remote=False,
            folder_name="data",
            driver="ogr",
        )
        assert job_layer.redacted_fields == {"source"}
