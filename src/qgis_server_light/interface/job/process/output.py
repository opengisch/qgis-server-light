from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface


@dataclass
class ParameterOutput:
    name: str = field(metadata={"type": "Element"})
    value: str | int | float | bool = field(metadata={"type": "Element"})


@dataclass(repr=False)
class ProcessResult(BaseInterface):
    outputs: list[ParameterOutput] = field(default_factory=list, metadata={"type": "Element"})
    log: str = field(default="", metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"log"}
