import io
import json
import re
import uuid
import zlib
from base64 import urlsafe_b64encode

import pytest
from PIL import Image

from qgis_server_light.interface.common import Style
from qgis_server_light.interface.exporter.extract import GdalSource, OgrSource
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.legend.input import (
    QslJobInfoLegend,
    QslJobParameterLegend,
)
from qgis_server_light.worker.runner.common import JobContext
from qgis_server_light.worker.runner.legend import GetLegendRunner


@pytest.fixture
def default_style():
    # an empty style keeps the renderer QGIS gives the layer on load
    yield Style(
        name="default",
        definition=urlsafe_b64encode(zlib.compress(b"<qgis/>")).decode(),
    )


@pytest.fixture
def placenames_layer(default_style):
    yield QslJobLayer(
        id=str(uuid.uuid4()),
        name="test-local-gpkg",
        source=json.dumps(
            OgrSource(path="placenames.gpkg", layer_name="placenames").to_qgis_decoded_uri
        ),
        remote=False,
        folder_name="data",
        driver="ogr",
        style=default_style,
    )


@pytest.fixture
def geotiff_layer(default_style):
    yield QslJobLayer(
        id=str(uuid.uuid4()),
        name="test-local-geotiff",
        source=json.dumps(GdalSource(path="bui20220630.tif").to_qgis_decoded_uri),
        remote=False,
        folder_name="data",
        driver="gdal",
        style=default_style,
    )


class TestGetLegendRunnerIntegration:
    @pytest.mark.parametrize("legend_format", ["application/json", "json", "JSON"])
    def test_json_legend_lists_the_requested_layers(
        self, qgis_app, data_path, placenames_layer, geotiff_layer, legend_format
    ):
        job_info = QslJobInfoLegend(
            id=str(uuid.uuid4()),
            type=QslJobInfoLegend.__name__,
            job=QslJobParameterLegend(
                layers=[placenames_layer, geotiff_layer],
                format=legend_format,
            ),
        )
        result = GetLegendRunner(qgis_app, JobContext(base_path=data_path), job_info).run()

        # whatever spelling QGIS Server accepts, the answer is always plain json
        assert result.id == job_info.id
        assert result.content_type == "application/json"
        legend = json.loads(result.data)

        # we expect one node per requested layer, in the requested order
        assert [node["type"] for node in legend["nodes"]] == ["layer", "layer"]

        # the placenames have a single symbol, QGIS puts its icon directly on the node
        placenames_node = legend["nodes"][0]
        assert placenames_node["title"] == "test-local-gpkg"
        assert placenames_node["icon"]

        # the geotiff has a color ramp, QGIS lists its entries as symbols
        geotiff_node = legend["nodes"][1]
        assert len(geotiff_node["symbols"]) == 2

    @pytest.mark.parametrize(
        "layer_title,expected_title",
        [
            # without layer title the layer node stays unnamed
            (False, ""),
            (True, "test-local-geotiff"),
        ],
    )
    def test_json_legend_shows_layer_title_only_when_requested(
        self, qgis_app, data_path, geotiff_layer, layer_title, expected_title
    ):
        job_info = QslJobInfoLegend(
            id=str(uuid.uuid4()),
            type=QslJobInfoLegend.__name__,
            job=QslJobParameterLegend(
                layers=[geotiff_layer],
                format="application/json",
                layer_title=layer_title,
            ),
        )
        result = GetLegendRunner(qgis_app, JobContext(base_path=data_path), job_info).run()

        # the geotiff node has several symbols, so its title is the layer title
        legend = json.loads(result.data)
        assert legend["nodes"][0]["title"] == expected_title

    @pytest.mark.parametrize(
        "legend_format,expected_content_type,expected_image_format",
        [
            ("image/png", "image/png", "PNG"),
            ("IMAGE/JPEG", "image/jpeg", "JPEG"),
        ],
    )
    def test_image_legend_is_encoded_in_the_requested_format(
        self,
        qgis_app,
        data_path,
        placenames_layer,
        legend_format,
        expected_content_type,
        expected_image_format,
    ):
        job_info = QslJobInfoLegend(
            id=str(uuid.uuid4()),
            type=QslJobInfoLegend.__name__,
            job=QslJobParameterLegend(
                layers=[placenames_layer],
                format=legend_format,
                width=200,
            ),
        )
        result = GetLegendRunner(qgis_app, JobContext(base_path=data_path), job_info).run()

        # the content type is the lower case mime type, also when asked in capitals
        assert result.content_type == expected_content_type

        # we expect a real image of the format, scaled to the requested width
        image = Image.open(io.BytesIO(result.data))
        assert image.format == expected_image_format
        assert image.width == 200

    def test_unknown_format_is_refused(self, qgis_app, data_path, placenames_layer):
        job_info = QslJobInfoLegend(
            id=str(uuid.uuid4()),
            type=QslJobInfoLegend.__name__,
            job=QslJobParameterLegend(layers=[placenames_layer], format="image/gif"),
        )
        runner = GetLegendRunner(qgis_app, JobContext(base_path=data_path), job_info)

        # the worker gets an error which names the formats it could have delivered
        with pytest.raises(
            RuntimeError,
            match=re.escape(
                "Requested mime type 'image/gif' was not found in ['image/png', 'image/jpeg']."
            ),
        ):
            runner.run()
