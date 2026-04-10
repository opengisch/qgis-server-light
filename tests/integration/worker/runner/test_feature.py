import json
import uuid

import pytest
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.exporter.extract import OgrSource
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.feature.input import (
    FeatureQuery,
    QslJobInfoFeature,
    QslJobParameterFeature,
)
from qgis_server_light.interface.job.feature.output import (
    Feature,
    FeatureCollection,
    QueryCollection,
)
from qgis_server_light.worker.runner.common import JobContext
from qgis_server_light.worker.runner.feature import GetFeatureRunner


class TestFeatureRunnerIntegration:
    @pytest.mark.parametrize(
        "job_layer",
        [
            QslJobLayer(
                id=str(uuid.uuid4()),
                name="test-local-gpkg",
                source=json.dumps(
                    OgrSource(
                        path="placenames.gpkg", layer_name="placenames"
                    ).to_qgis_decoded_uri
                ),
                remote=False,
                folder_name="data",
                driver="ogr",
            ),
        ],
    )
    def test_features_from_local_source(self, qgis_app, data_path, job_layer):
        job_info = QslJobInfoFeature(
            id=str(uuid.uuid4()),
            type=QslJobInfoFeature.__name__,
            job=QslJobParameterFeature(
                queries=[FeatureQuery(layers=[job_layer])],
            ),
        )

        runner = GetFeatureRunner(
            qgis_app,
            JobContext(base_path=data_path),
            job_info,
            {},
        )
        result = runner.run()
        assert isinstance(result, JobResult)
        assert isinstance(result.data, bytes)
        assert result.id == job_info.id

        data = JsonParser().from_bytes(result.data)
        assert isinstance(data, QueryCollection)
        assert data.numbers_matched == 93
        assert len(data.feature_collections) == 1
        feature_collection = data.feature_collections[0]
        assert isinstance(feature_collection, FeatureCollection)
        assert feature_collection.name == job_layer.name
        assert len(feature_collection.features) > 0
        feature = feature_collection.features[0]
        assert isinstance(feature, Feature)
        assert feature.geometry is not None
