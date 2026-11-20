from dataclasses import dataclass, field

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
)


@dataclass
class ParameterInput:
    name: str = field(metadata={"type": "Element"})
    value: QslJobLayer | str | int | float | bool = field(metadata={"type": "Element"})


@dataclass
class OutputFormat:
    """The format a client wants a file output in.

    Attributes:
        name: The name of the output as the QGIS algorithm defines it.
        media_type: One of the media types the description offers for the output.
    """

    name: str = field(metadata={"type": "Element"})
    media_type: str = field(metadata={"type": "Element"})


@dataclass(kw_only=True)
class QslJobParameterExecuteProcess(QslJobParameter):
    """A runner to execute a process"""

    process_id: str = field(metadata={"type": "Element"})
    parameters: list[ParameterInput] = field(metadata={"type": "Element"})
    output_formats: list[OutputFormat] = field(default_factory=list, metadata={"type": "Element"})


@dataclass
class QslJobInfoExecuteProcess(QslJobInfoParameter):
    job: QslJobParameterExecuteProcess = field(metadata={"type": "Element", "required": True})
