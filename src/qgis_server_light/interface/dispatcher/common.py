from dataclasses import dataclass
from datetime import datetime
from enum import Enum

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
