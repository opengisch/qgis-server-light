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
    """The state of a job which keeps its state (see `RedisStateProtocol`) as
    it was read from the job hash. It gives the dispatcher one thing to hand
    over instead of the raw redis fields.

    Attributes:
        id: The unique identifier of the job.
        status: The current status of the job.
        last_update: ISO timestamp of the last status change.
        result: The result of a succeeded job.
        message: The error message of a failed job.
    """

    id: str = field(metadata={"type": "Element"})
    status: Status = field(metadata={"type": "Element"})
    last_update: str | None = field(default=None, metadata={"type": "Element"})
    result: JobResult | None = field(default=None, metadata={"type": "Element"})
    message: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def finished(self) -> bool:
        """If the job reached a final status, nothing changes on it anymore."""
        return self.status in (Status.SUCCESS, Status.FAILURE)
