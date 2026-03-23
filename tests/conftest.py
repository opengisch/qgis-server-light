import logging

import pytest

from qgis_server_light.worker.qgis import Qgis


@pytest.fixture
def data_path():
    yield "./tests/resources"


@pytest.fixture
def svg_paths():
    yield ["./tests/resources/svg"]


@pytest.fixture
def qgis_app(svg_paths):
    yield Qgis(svg_paths, logging.DEBUG)
