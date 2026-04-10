"""This part defines the structure how a running QSL worker exposes its
capabilities."""

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    STARTING = "starting"
    CRASHED = "crashed"
    WAITING = "waiting"
    PROCESSING = "processing"


@dataclass
class QgisInfo:
    """
    Information container to ship minimal knowledge of the underlying
    QGIS.

    Attributes:
        version: The integer representation of the QGIS version e.g. 34400
        version_name: The string representation which also includes the codename e.g.
            "QGIS Version 4.0.0-Norrköping"

    """

    version: int = field(metadata={"type": "Element"})
    version_name: str = field(metadata={"type": "Element"})
    path: str = field(metadata={"type": "Element"})


@dataclass
class EngineInfo:
    id: str = field(metadata={"type": "Element"})
    qgis_info: QgisInfo = field(metadata={"type": "Element"})
    status: Status = field(metadata={"type": "Element"})
    started: float = field(metadata={"type": "Element"})
