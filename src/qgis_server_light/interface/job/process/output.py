"""This module contains the result of a process job. It is shaped along the results of
OGC API - Processes - Part 1: Core
(https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/results.yaml),
per output either the literal value or a reference to the file. The outputs are a list of
entries with their id instead of a map by id, see `ExecuteInput`.
"""

from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface


@dataclass
class Reference:
    """A file a process wrote into the process output dir of the worker.

    Attributes:
        href: The path of the file relative to the process output dir.
        type: The media type of the file.
    """

    href: str = field(metadata={"type": "Element"})
    type: str = field(metadata={"type": "Element"})


@dataclass
class ResultOutput:
    """A single output of a process, the counterpart of `ExecuteInput`.

    Attributes:
        id: The identifier of the output, the QGIS output name.
        value: The file the output was written to, or the literal value of the
            output.
    """

    id: str = field(metadata={"type": "Element"})
    value: Reference | str | int | float | bool = field(metadata={"type": "Element"})


@dataclass(repr=False)
class ProcessResult(BaseInterface):
    """The result of a process. A worker ships it as xsdata JSON in the data of
    the `JobResult`, so the dispatcher can parse it back without knowing
    anything about QGIS.

    Attributes:
        outputs: The outputs of the process.
        log: The log the QGIS algorithm wrote while it was running. It has no place in
            the results of OGC API - Processes and travels next to the outputs.
    """

    outputs: list[ResultOutput] = field(default_factory=list, metadata={"type": "Element"})
    log: str = field(default="", metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"log"}
