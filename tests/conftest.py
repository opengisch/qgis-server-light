import logging

import pytest

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
