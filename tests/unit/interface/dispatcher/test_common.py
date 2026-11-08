import pytest

from qgis_server_light.interface.dispatcher.common import JobState, Status
from qgis_server_light.interface.job.common.output import JobResult
from tests.base.dataclass_test import DataclassTest
from tests.base.enum_test import EnumTest


class TestStatus(EnumTest):
    enum_names = {
        "SUCCESS",
        "FAILURE",
        "RUNNING",
        "QUEUED",
    }
    enum_values = {
        "succeed",
        "failed",
        "running",
        "queued",
    }
    enum_class_to_test = Status


class TestJobState(DataclassTest):
    field_defs = [
        ("id", str),
        ("status", Status),
        ("last_update", str | None),
        ("result", JobResult | None),
        ("message", str | None),
    ]
    field_defaults = [
        ("last_update", None),
        ("result", None),
        ("message", None),
    ]
    dataclass_to_test = JobState

    def test_instantiation(self):
        job_state = JobState(
            id="ididid",
            status=Status.FAILURE,
            last_update="2026-11-08T13:00:00",
            message="Algorithm `native:centroids` failed",
        )
        assert job_state.id == "ididid"
        assert job_state.status == Status.FAILURE
        assert job_state.last_update == "2026-11-08T13:00:00"
        assert job_state.result is None
        assert job_state.message == "Algorithm `native:centroids` failed"

    @pytest.mark.parametrize(
        "status,expected",
        [
            (Status.QUEUED, False),
            (Status.RUNNING, False),
            (Status.SUCCESS, True),
            (Status.FAILURE, True),
        ],
    )
    def test_finished(self, status, expected):
        assert JobState(id="ididid", status=status).finished is expected
