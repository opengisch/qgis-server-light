from dataclasses import dataclass
from enum import Enum

from qgis_server_light.interface.job.common.output import JobResult


class Status(Enum):
    SUCCESS = "succeed"
    FAILURE = "failed"
    RUNNING = "running"
    QUEUED = "queued"


@dataclass
class JobState:
    id: str
    status: Status
    last_update: str | None = None
    result: JobResult | None = None
    message: str | None = None

    @property
    def finished(self) -> bool:
        return self.status in (Status.SUCCESS, Status.FAILURE)
