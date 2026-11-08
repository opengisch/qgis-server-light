import json
import logging
import uuid
import zlib
from base64 import urlsafe_b64encode

import pytest

from qgis_server_light.interface.common import Style
from qgis_server_light.interface.exporter.extract import GdalSource, OgrSource
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.worker.qgis import Qgis


@pytest.fixture
def data_path():
    yield "./tests/resources"


@pytest.fixture(scope="session")
def svg_paths():
    yield ["./tests/resources/svg"]


@pytest.fixture(scope="session")
def qgis_app(svg_paths):
    # one QgsApplication per process, QGIS does not support re-creating it and
    # the credentials helper has to stay alive as long as the application
    yield Qgis(svg_paths, logging.DEBUG)


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
