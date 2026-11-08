from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.worker.info import EngineInfo


class Status(Enum):
    SUCCESS = "succeed"
    FAILURE = "failed"
    RUNNING = "running"
    QUEUED = "queued"


@dataclass
class Worker:
    """A worker the dispatcher has seen alive on the queue. It carries what a
    consumer needs to tell whether jobs can be served and what the worker is doing
    right now.

    Attributes:
        id: The unique identifier of the worker.
        last_seen: The time of the last heartbeat of the worker, always timezone aware.
        info: The info the worker published with its last heartbeat (status, QGIS
            version, start time).
    """

    id: str
    last_seen: datetime
    info: EngineInfo


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
