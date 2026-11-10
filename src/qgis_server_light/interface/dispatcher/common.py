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
    id: str
    last_seen: datetime
