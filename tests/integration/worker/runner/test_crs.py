import uuid

import pytest
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.common import Crs
from qgis_server_light.interface.job.common.input import ExecutionMode
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.crs.input import QslJobInfoCrs, QslJobParameterCrs
from qgis_server_light.interface.job.crs.output import CrsCollection
from qgis_server_light.worker.runner.common import JobContext
from qgis_server_light.worker.runner.crs import CrsRunner


def create_job_info(identifiers: list[str]) -> QslJobInfoCrs:
    return QslJobInfoCrs(
        id=str(uuid.uuid4()),
        type=QslJobInfoCrs.__name__,
        job=QslJobParameterCrs(identifiers=identifiers),
        execution_mode=ExecutionMode.SYNC,
    )


class TestCrsRunnerIntegration:
    def test_crs_resolved_in_order(self, qgis_app, data_path):
        job_info = create_job_info(
            [
                "EPSG:3857",
                "urn:ogc:def:crs:EPSG::4326",
                "http://www.opengis.net/def/crs/EPSG/0/2056",
            ]
        )

        result = CrsRunner(qgis_app, JobContext(base_path=data_path), job_info).run()

        assert isinstance(result, JobResult)
        assert result.id == job_info.id
        crs_collection = JsonParser().from_bytes(result.data, CrsCollection)
        assert crs_collection.crs == [
            Crs(
                auth_id="EPSG:3857",
                postgis_srid=3857,
                ogc_uri="http://www.opengis.net/def/crs/EPSG/0/3857",
                ogc_urn="urn:ogc:def:crs:EPSG::3857",
                axis_inverted=False,
            ),
            Crs(
                auth_id="EPSG:4326",
                postgis_srid=4326,
                ogc_uri="http://www.opengis.net/def/crs/EPSG/0/4326",
                ogc_urn="urn:ogc:def:crs:EPSG::4326",
                axis_inverted=True,
            ),
            Crs(
                auth_id="EPSG:2056",
                postgis_srid=2056,
                ogc_uri="http://www.opengis.net/def/crs/EPSG/0/2056",
                ogc_urn="urn:ogc:def:crs:EPSG::2056",
                axis_inverted=False,
            ),
        ]

    @pytest.mark.parametrize("identifier", ["EPSG:999999", "no-crs"])
    def test_invalid_crs(self, qgis_app, data_path, identifier):
        job_info = create_job_info(["EPSG:4326", identifier])

        with pytest.raises(RuntimeError, match=identifier):
            CrsRunner(qgis_app, JobContext(base_path=data_path), job_info).run()
