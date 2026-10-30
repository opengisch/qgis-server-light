import json
import os
import shutil
import uuid
import zlib
from base64 import urlsafe_b64encode

import pytest
from qgis.core import QgsVectorLayer
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.common import BBox, Style
from qgis_server_light.interface.exporter.extract import GdalSource, OgrSource
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.feature.input import (
    FeatureQuery,
    QslJobInfoFeature,
    QslJobParameterFeature,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)
from qgis_server_light.worker.runner.common import JobContext
from qgis_server_light.worker.runner.feature import GetFeatureRunner
from qgis_server_light.worker.runner.render import RenderRunner


def delete(path: str):
    os.remove(path)


def truncate(path: str):
    open(path, "wb").close()


def overwrite_header(path: str):
    with open(path, "r+b") as f:
        f.write(b"\0" * 8192)


@pytest.fixture
def layer_cache():
    yield {}


@pytest.fixture
def base_path(tmp_path, data_path):
    """A copy of the test data which can be broken without harming the resources."""
    shutil.copytree(os.path.join(data_path, "data"), tmp_path / "data")
    yield tmp_path


@pytest.fixture
def placenames_layer():
    yield QslJobLayer(
        id=str(uuid.uuid4()),
        name="test-local-gpkg",
        source=json.dumps(
            OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
        ),
        remote=False,
        folder_name="data",
        driver="ogr",
    )


@pytest.fixture
def geotiff_layer():
    yield QslJobLayer(
        id=str(uuid.uuid4()),
        name="test-local-geotiff",
        source=json.dumps(GdalSource(path="bui20220630.tif").to_qgis_decoded_uri),
        remote=False,
        folder_name="data",
        driver="gdal",
        style=Style(
            name="default", definition=urlsafe_b64encode(zlib.compress(b"<qgis/>")).decode()
        ),
    )


@pytest.fixture
def feature_job_info(placenames_layer):
    yield QslJobInfoFeature(
        id=str(uuid.uuid4()),
        type=QslJobInfoFeature.__name__,
        job=QslJobParameterFeature(queries=[FeatureQuery(layers=[placenames_layer])]),
    )


@pytest.fixture
def render_job_info(geotiff_layer):
    yield QslJobInfoRender(
        id=str(uuid.uuid4()),
        type=QslJobInfoRender.__name__,
        job=QslJobParameterRender(
            layers=[geotiff_layer],
            bbox=BBox(2485675.21, 2833675.21, 1075128.16, 1295628.16),
            crs="EPSG:2056",
            width=100,
            height=100,
            dpi=75,
            format="image/png",
        ),
    )


class TestLayerCacheIntegration:
    def test_layer_id_is_cache_name(
        self, qgis_app, base_path, layer_cache, placenames_layer, feature_job_info
    ):
        runner = GetFeatureRunner(
            qgis_app, JobContext(base_path=base_path), feature_job_info, layer_cache
        )
        runner.run()

        cache_name = runner.get_cache_name(placenames_layer)
        assert layer_cache[cache_name].id() == cache_name

    def test_unchanged_source_keeps_cached_layer(
        self, qgis_app, base_path, layer_cache, feature_job_info
    ):
        context = JobContext(base_path=base_path)
        GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()
        cached_layer = next(iter(layer_cache.values()))

        GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()

        assert next(iter(layer_cache.values())) is cached_layer

    def test_invalid_cached_layer_fails_job_and_is_thrown_out_of_cache(
        self, qgis_app, base_path, layer_cache, placenames_layer, feature_job_info
    ):
        context = JobContext(base_path=base_path)

        # creates a runner which has the test geopackage as layer to be executed on
        # (placenames)
        runner = GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache)
        # derrive a cachename directly from the layer instance, this matches the
        # name of the valid layer from the original job
        cache_name = runner.get_cache_name(placenames_layer)
        runner.run()
        # we expect the layer is still in cache since it was valid
        assert isinstance(layer_cache[cache_name], QgsVectorLayer)

        # now we go to break the layer
        invalid_layer = QgsVectorLayer("/nonexistent.gpkg", placenames_layer.name, "ogr")
        # we mimikri the former valid layer be stealing its cachename
        invalid_layer.setId(cache_name)
        # we replace the former valid layer
        layer_cache[cache_name] = invalid_layer

        # we run again and expect the run to fail
        with pytest.raises(RuntimeError, match=placenames_layer.id):
            runner.run()
        # we expect the cache to be empty since the invalid layer was thrown out
        assert layer_cache == {}

        GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()
        assert layer_cache[cache_name].isValid()

    @pytest.mark.parametrize("break_source", [delete, truncate, overwrite_header])
    def test_broken_gpkg_throws_out_layer_and_recovers(
        self, qgis_app, base_path, layer_cache, placenames_layer, feature_job_info, break_source
    ):
        context = JobContext(base_path=base_path)

        # pointer to the gpkg the layer in the feature_job_info is based on
        gpkg = os.path.join(base_path, "data", "placenames.gpkg")
        # a copy of this gpkg
        backup = os.path.join(base_path, "placenames.gpkg.backup")
        shutil.copy(gpkg, backup)

        # simulates the first incoming job
        first_runner = GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache)
        first_cache_name = first_runner.get_cache_name(placenames_layer)
        first_runner.run()

        # we lay aside the initial layer for later tests
        first_cached_layer = layer_cache[first_cache_name]

        # we break the datasource
        break_source(gpkg)
        # we expect the second job to fail since the datasource is broken
        with pytest.raises(RuntimeError, match=placenames_layer.id):
            # simulates the second incoming job
            second_runner = GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache)
            second_runner.run()
        # cache should be clean, since invalid layers are thrown out
        assert layer_cache == {}

        # we restore the datasource
        shutil.copy(backup, gpkg)

        # simulates the third request
        third_runner = GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache)
        # we expect it to run successfully
        result = third_runner.run()
        assert JsonParser().from_bytes(result.data).numbers_matched == 93
        third_cache_name = third_runner.get_cache_name(placenames_layer)
        # the layer in cache should be a different instance then the one from the first job
        assert layer_cache[third_cache_name] is not first_cached_layer

    @pytest.mark.parametrize("break_source", [delete, truncate, overwrite_header])
    def test_broken_geotiff_throws_out_layer_and_recovers(
        self, qgis_app, base_path, layer_cache, geotiff_layer, render_job_info, break_source
    ):
        context = JobContext(base_path=base_path)

        # pointer to the geotiff the layer in the feature_job_info is based on
        geotiff = os.path.join(base_path, "data", "bui20220630.tif")
        # a copy of this geotiff
        backup = os.path.join(base_path, "bui20220630.tif.backup")
        shutil.copy(geotiff, backup)

        first_runner = RenderRunner(qgis_app, context, render_job_info, layer_cache)
        first_cache_name = first_runner.get_cache_name(geotiff_layer)
        first_runner.run()

        first_cached_layer = layer_cache[first_cache_name]

        break_source(geotiff)
        with pytest.raises(RuntimeError, match=geotiff_layer.id):
            second_runner = RenderRunner(qgis_app, context, render_job_info, layer_cache)
            second_runner.run()
        assert layer_cache == {}

        shutil.copy(backup, geotiff)
        third_runner = RenderRunner(qgis_app, context, render_job_info, layer_cache)
        third_cache_name = third_runner.get_cache_name(geotiff_layer)
        third_runner.run()
        assert layer_cache[third_cache_name] is not first_cached_layer

    def test_render_errors_throws_out_layer_and_fail_job(
        self, qgis_app, base_path, layer_cache, geotiff_layer, render_job_info
    ):
        runner = RenderRunner(
            qgis_app, JobContext(base_path=base_path), render_job_info, layer_cache
        )
        runner.run()
        cache_name = runner.get_cache_name(geotiff_layer)

        with pytest.raises(RuntimeError, match=geotiff_layer.id):
            runner._raise_on_layer_errors({cache_name: "request failed"})

        assert cache_name not in layer_cache

    def test_replaced_gpkg_with_preserved_timestamp_throws_out_layer(
        self, qgis_app, base_path, layer_cache, placenames_layer, feature_job_info
    ):
        context = JobContext(base_path=base_path)
        gpkg = os.path.join(base_path, "data", "placenames.gpkg")
        GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()

        # replacing by rename like cp -p or rsync -a do it, same timestamp and size
        replacement = os.path.join(base_path, "placenames.gpkg.replacement")
        shutil.copy2(gpkg, replacement)
        os.replace(replacement, gpkg)
        with pytest.raises(RuntimeError, match=placenames_layer.id):
            GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()
        assert layer_cache == {}

    @pytest.mark.parametrize(
        "sidecar_name", ["placenames.gpkg-wal", "placenames.gpkg-shm", "placenames.gfs"]
    )
    def test_sidecar_files_keep_cached_layer(
        self, qgis_app, base_path, layer_cache, feature_job_info, sidecar_name
    ):
        context = JobContext(base_path=base_path)
        GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()
        cached_layer = next(iter(layer_cache.values()))

        # an empty WAL file is a valid one for sqlite, only its appearance matters
        open(os.path.join(base_path, "data", sidecar_name), "wb").close()
        GetFeatureRunner(qgis_app, context, feature_job_info, layer_cache).run()

        assert next(iter(layer_cache.values())) is cached_layer
