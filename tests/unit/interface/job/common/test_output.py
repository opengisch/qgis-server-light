from typing import Any

from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.job.common.output import JobResult
from tests.base.dataclass_test import DataclassTest


class TestJobResult(DataclassTest):
    field_defs = [
        ("id", str),
        ("data", Any),
        ("content_type", str),
    ]
    dataclass_to_test = JobResult

    def test_instantiation(self):
        job_result = JobResult(
            id="dididid",
            data="101010102002021010",
            content_type="application/pdf",
        )
        assert job_result.data == "101010102002021010"
        assert job_result.content_type == "application/pdf"

    def test_super(self):
        assert issubclass(JobResult, BaseInterface)

    def test_configured_shortened_fields(self):
        job_result = JobResult(
            id="idididi",
            data="101010102002021010",
            content_type="application/pdf",
        )
        assert job_result.shortened_fields == {"data"}
