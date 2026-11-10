from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Status(Enum):
    SUCCESS = "succeed"
    FAILURE = "failed"
    RUNNING = "running"
    QUEUED = "queued"


@dataclass
class Worker:
    """A worker the dispatcher has seen alive on the queue. It carries only what a
    consumer needs to tell whether jobs can be served at all, nothing about the
    QGIS behind it.

    Attributes:
        id: The unique identifier of the worker.
        last_seen: The time of the last heartbeat of the worker, always timezone aware.
    """

    id: str
    last_seen: datetime
