from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.job.common.input import (
    OgcFilterFES20,
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
)
from qgis_server_light.interface.job.feature.input import (
    FeatureQuery,
    QslJobInfoFeature,
    QslJobParameterFeature,
)
from tests.base.dataclass_test import DataclassTest


class TestFeatureQuery(DataclassTest):
    field_defs = [
        ("layers", list[QslJobLayer]),
        ("aliases", list[str]),
        ("filter", OgcFilterFES20),
    ]
    field_defaults = [
        ("filter", None),
    ]
    field_default_factories = [
        ("aliases", list),
    ]
    dataclass_to_test = FeatureQuery

    def test_instantiation(self):
        feature_query = FeatureQuery(
            layers=[
                QslJobLayer(
                    id="adkjfoiewjd",
                    name="test",
                    source="x.y.z",
                    remote=False,
                    folder_name="data",
                    driver="ogr",
                )
            ],
            aliases=["aliased-layer-name"],
            filter=OgcFilterFES20(definition="djfiewjföljdafjaie"),
        )
        assert isinstance(feature_query.layers, list)
        assert isinstance(feature_query.layers[0], QslJobLayer)
        assert isinstance(feature_query.aliases, list)
        assert isinstance(feature_query.aliases[0], str)
        assert isinstance(feature_query.filter, OgcFilterFES20)

    def test_super(self):
        assert issubclass(FeatureQuery, BaseInterface)


class TestQslJobParameterFeature(DataclassTest):
    field_defs = [
        ("queries", list[FeatureQuery]),
        ("start_index", int),
        ("count", int | None),
    ]
    field_defaults = [("start_index", 0), ("count", None)]
    dataclass_to_test = QslJobParameterFeature

    def test_instantiation(self):
        job_param = QslJobParameterFeature(
            queries=[
                FeatureQuery(
                    layers=[
                        QslJobLayer(
                            id="adkjfoiewjd",
                            name="test",
                            source="x.y.z",
                            remote=False,
                            folder_name="data",
                            driver="ogr",
                        )
                    ],
                    aliases=["aliased-layer-name"],
                    filter=OgcFilterFES20(definition="djfiewjföljdafjaie"),
                )
            ]
        )
        assert isinstance(job_param.queries, list)
        assert isinstance(job_param.queries[0], FeatureQuery)
        assert job_param.start_index == 0
        assert job_param.count is None

    def test_super(self):
        assert issubclass(QslJobParameterFeature, QslJobParameter)


class TestQslJobInfoRender(DataclassTest):
    field_defs = [
        ("job", QslJobParameterFeature),
    ]
    dataclass_to_test = QslJobInfoFeature

    def test_instantiation(self):
        job_info = QslJobInfoFeature(
            id="lsadjlajs",
            type=QslJobInfoFeature.__name__,
            job=QslJobParameterFeature(
                queries=[
                    FeatureQuery(
                        layers=[
                            QslJobLayer(
                                id="adkjfoiewjd",
                                name="test",
                                source="x.y.z",
                                remote=False,
                                folder_name="data",
                                driver="ogr",
                            )
                        ],
                        aliases=["aliased-layer-name"],
                        filter=OgcFilterFES20(definition="djfiewjföljdafjaie"),
                    )
                ]
            ),
        )
        assert isinstance(job_info.job, QslJobParameterFeature)

    def test_super(self):
        assert issubclass(QslJobInfoFeature, QslJobInfoParameter)
