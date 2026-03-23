"""This part defines the structure how a running QSL worker exposes its
capabilities."""

from dataclasses import dataclass, field
from enum import Enum

from qgis_server_light.interface.common import BaseInterface


class Status(str, Enum):
    STARTING = "starting"
    CRASHED = "crashed"
    WAITING = "waiting"
    PROCESSING = "processing"


@dataclass
class Render:
    formats: list[str] = field(metadata={"type": "Element"})


@dataclass
class Features:
    pass


@dataclass
class FeatureInfo:
    pass


@dataclass
class Legend:
    pass


@dataclass
class Parameter(BaseInterface):
    name: str = field(metadata={"type": "Element"})
    type: str = field(metadata={"type": "Element"})
    description: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"description"}


@dataclass
class Output(BaseInterface):
    name: str = field(metadata={"type": "Element"})
    type: str = field(metadata={"type": "Element"})
    description: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"description"}


@dataclass
class Algorithm:
    id: str = field(metadata={"type": "Element"})
    name: str = field(metadata={"type": "Element"})
    display_name: str = field(metadata={"type": "Element"})
    help_string: str | None = field(default=None, metadata={"type": "Element"})
    parameters: list[Parameter] = field(
        default_factory=list, metadata={"type": "Element"}
    )
    outputs: list[Output] = field(default_factory=list, metadata={"type": "Element"})


@dataclass
class Process:
    # uniqueness is not assured here!
    algorithms: list[Algorithm] = field(
        default_factory=list, metadata={"type": "Element"}
    )


@dataclass
class QgisInfo:
    version: str = field(metadata={"type": "Element"})
    path: str = field(metadata={"type": "Element"})
    providers: list[str] = field(metadata={"type": "Element"})


@dataclass
class EngineInfo:
    id: str = field(metadata={"type": "Element"})
    qgis_info: QgisInfo = field(metadata={"type": "Element"})
    status: Status = field(metadata={"type": "Element"})
    started: float = field(metadata={"type": "Element"})
    # TODO: Add version once we know how
    # version: str = field(metadata={"type": "Element"})
    runner_infos: list[Render | FeatureInfo | Features | Process | Legend] = field(
        default_factory=list, metadata={"type": "Element"}
    )
