from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface


@dataclass
class ParameterOutput:
    """A single output of a process, the counterpart of `ParameterInput`.

    Attributes:
        name: The name of the output as the QGIS algorithm defines it.
        value: The literal value of the output.
    """

    name: str = field(metadata={"type": "Element"})
    value: str | int | float | bool = field(metadata={"type": "Element"})


@dataclass(repr=False)
class ProcessResult(BaseInterface):
    """The result of a process. A worker ships it as xsdata JSON in the data of
    the `JobResult`, so the dispatcher can parse it back without knowing
    anything about QGIS.

    Attributes:
        outputs: The outputs of the process. Only literal values are supported
            for now.
        log: The log the QGIS algorithm wrote while it was running.
    """

    outputs: list[ParameterOutput] = field(default_factory=list, metadata={"type": "Element"})
    log: str = field(default="", metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"log"}
