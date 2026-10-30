import json
import uuid

import pytest
from qgis.core import QgsGeometry
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.common import Crs
from qgis_server_light.interface.exporter.extract import OgrSource
from qgis_server_light.interface.job.common.input import ExecutionMode, OgcFilterFES20, QslJobLayer
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
                    OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
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
            execution_mode=ExecutionMode.SYNC,
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
        assert feature_collection.name == job_layer.id
        assert len(feature_collection.features) > 0
        feature = feature_collection.features[0]
        assert isinstance(feature, Feature)
        assert feature.geometry is not None

    @pytest.mark.parametrize(
        "crs",
        [
            Crs(auth_id="EPSG:4326"),
            Crs(ogc_urn="urn:ogc:def:crs:EPSG::4326"),
            Crs(ogc_uri="http://www.opengis.net/def/crs/EPSG/0/4326"),
        ],
        ids=["auth_id", "ogc_urn", "ogc_uri"],
    )
    def test_features_transformed_to_query_crs(self, qgis_app, data_path, crs):
        job_layer = QslJobLayer(
            id=str(uuid.uuid4()),
            name="test-local-gpkg",
            source=json.dumps(
                OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
            ),
            remote=False,
            folder_name="data",
            driver="ogr",
        )
        job_info = QslJobInfoFeature(
            id=str(uuid.uuid4()),
            type=QslJobInfoFeature.__name__,
            job=QslJobParameterFeature(
                queries=[FeatureQuery(layers=[job_layer], crs=crs)],
            ),
            execution_mode=ExecutionMode.SYNC,
        )

        result = GetFeatureRunner(qgis_app, JobContext(base_path=data_path), job_info, {}).run()

        data = JsonParser().from_bytes(result.data)
        geometry = QgsGeometry()
        geometry.fromWkb(data.feature_collections[0].features[0].geometry.value)
        point = geometry.asPoint()
        # placenames are in switzerland, layer crs is EPSG:2056
        assert 5 < point.x() < 11
        assert 45 < point.y() < 48

    def test_features_invalid_query_crs(self, qgis_app, data_path):
        job_layer = QslJobLayer(
            id=str(uuid.uuid4()),
            name="test-local-gpkg",
            source=json.dumps(
                OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
            ),
            remote=False,
            folder_name="data",
            driver="ogr",
        )
        job_info = QslJobInfoFeature(
            id=str(uuid.uuid4()),
            type=QslJobInfoFeature.__name__,
            job=QslJobParameterFeature(
                queries=[FeatureQuery(layers=[job_layer], crs=Crs(auth_id="EPSG:999999"))],
            ),
            execution_mode=ExecutionMode.SYNC,
        )

        with pytest.raises(RuntimeError):
            GetFeatureRunner(qgis_app, JobContext(base_path=data_path), job_info, {}).run()

    @pytest.mark.parametrize(
        "srs_name, lower_corner, upper_corner",
        [
            ("EPSG:4326", "5 45", "11 48"),
            ("urn:ogc:def:crs:EPSG::4326", "45 5", "48 11"),
        ],
    )
    def test_filter_geometry_in_other_crs_than_layer(
        self, qgis_app, data_path, srs_name, lower_corner, upper_corner
    ):
        job_layer = QslJobLayer(
            id=str(uuid.uuid4()),
            name="test-local-gpkg",
            source=json.dumps(
                OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
            ),
            remote=False,
            folder_name="data",
            driver="ogr",
        )
        # envelope around switzerland in EPSG:4326, layer crs is EPSG:2056, same
        # namespace mapping as georama renders the filter
        definition = (
            '<Filter xmlns="http://www.opengis.net/fes/2.0" '
            'xmlns:gml="http://www.opengis.net/gml/3.2">'
            "<BBOX><ValueReference>geom</ValueReference>"
            f'<gml:Envelope srsName="{srs_name}">'
            f"<gml:lowerCorner>{lower_corner}</gml:lowerCorner>"
            f"<gml:upperCorner>{upper_corner}</gml:upperCorner>"
            "</gml:Envelope></BBOX></Filter>"
        )
        job_info = QslJobInfoFeature(
            id=str(uuid.uuid4()),
            type=QslJobInfoFeature.__name__,
            job=QslJobParameterFeature(
                queries=[
                    FeatureQuery(layers=[job_layer], filter=OgcFilterFES20(definition=definition))
                ],
            ),
            execution_mode=ExecutionMode.SYNC,
        )

        result = GetFeatureRunner(qgis_app, JobContext(base_path=data_path), job_info, {}).run()

        data = JsonParser().from_bytes(result.data)
        assert data.numbers_matched == 93
