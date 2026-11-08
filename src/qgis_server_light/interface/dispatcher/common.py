from dataclasses import dataclass, field
from enum import Enum

from qgis_server_light.interface.job.common.output import JobResult


class Status(Enum):
    SUCCESS = "succeed"
    FAILURE = "failed"
    RUNNING = "running"
    QUEUED = "queued"


@dataclass
class JobState:
    id: str = field(metadata={"type": "Element"})
    status: Status = field(metadata={"type": "Element"})
    last_update: str | None = field(default=None, metadata={"type": "Element"})
    result: JobResult | None = field(default=None, metadata={"type": "Element"})
    message: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def finished(self) -> bool:
        return self.status in (Status.SUCCESS, Status.FAILURE)
