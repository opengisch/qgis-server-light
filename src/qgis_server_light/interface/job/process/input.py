"""This module contains the execute request of a process job. It is shaped along the
execute request of OGC API - Processes - Part 1: Core
(https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/execute.yaml),
carrying its `inputs` and `outputs`. OGC API - Processes holds them as maps by id, xsdata
can't bind a map of dataclasses, therefore the id is part of each entry and they are lists
(see `InputDescription`).
"""

from dataclasses import dataclass, field

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
)


@dataclass
class ExecuteInput:
    """The value of one input of a process.

    Attributes:
        id: The identifier of the input, the QGIS parameter name.
        value: The values of the input, one entry for an input taking a single value. A
            layer value is substituted in place by its `QslJobLayer`.
    """

    id: str = field(metadata={"type": "Element"})
    value: list[QslJobLayer | str | int | float | bool] = field(
        default_factory=list, metadata={"type": "Element"}
    )


@dataclass
class Format:
    """The format of a file output.

    Attributes:
        media_type: One of the media types the description offers for the output.
    """

    media_type: str = field(metadata={"type": "Element", "name": "mediaType"})


@dataclass
class ExecuteOutput:
    """The format a client wants a file output in.

    Attributes:
        id: The identifier of the output, the QGIS output name.
        format: The format the output is written in.
    """

    id: str = field(metadata={"type": "Element"})
    format: Format = field(metadata={"type": "Element"})


@dataclass(kw_only=True)
class QslJobParameterExecuteProcess(QslJobParameter):
    """A runner to execute a process"""

    process_id: str = field(metadata={"type": "Element"})
    inputs: list[ExecuteInput] = field(default_factory=list, metadata={"type": "Element"})
    outputs: list[ExecuteOutput] = field(default_factory=list, metadata={"type": "Element"})


@dataclass
class QslJobInfoExecuteProcess(QslJobInfoParameter):
    job: QslJobParameterExecuteProcess = field(metadata={"type": "Element", "required": True})
