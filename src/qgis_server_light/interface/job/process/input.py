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


@dataclass(kw_only=True)
class QslJobParameterExecuteProcess(QslJobParameter):
    """A runner to execute a process"""

    process_id: str = field(metadata={"type": "Element"})
    parameters: list[ParameterInput] = field(metadata={"type": "Element"})


@dataclass
class QslJobInfoExecuteProcess(QslJobInfoParameter):
    job: QslJobParameterExecuteProcess = field(
        metadata={"type": "Element", "required": True}
    )
