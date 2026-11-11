"""This module contains the description of the processes a process-worker serves. It is
shaped along the process description of OGC API - Processes - Part 1: Core
(https://schemas.opengis.net/ogcapi/processes/part1/1.0/openapi/schemas/process.yaml),
so a consumer can expose its elements as they are and only adds what belongs to
the API around (links, job control options, conformance, ...).

Optional values default to `None`. Serialized with
`xsdata.formats.dataclass.serializers.dict.DictFactory.FILTER_NONE` they are left out,
which gives a plain JSON Schema for each `Schema`.
"""

from dataclasses import dataclass, field
from enum import Enum

from qgis_server_light.interface.common import BaseInterface

QSL_LAYER_FORMAT = "qsl-layer"


class QslLayerKind(Enum):
    VECTOR = "vector"
    RASTER = "raster"


@dataclass(repr=False)
class QslLayerMarker(BaseInterface):
    """Marks a schema whose value is a layer (`QslJobLayer`) instead of a literal. A
    consumer replaces the marked schema with the layers it offers which match the marker.

    Attributes:
        kind: The kind of layer which is accepted.
        geometry_types: The geometry types of a vector layer which are accepted, named as
            `qgis.core.Qgis.GeometryType` (`Point`, `Line`, `Polygon`, `Null`). Matches
            `Vector.geometry_type_simple` of the exported project. Empty for raster layers.
        source: The class name of the QGIS parameter or output the marker was derived from.
    """

    kind: QslLayerKind = field(metadata={"type": "Element"})
    geometry_types: list[str] = field(default_factory=list, metadata={"type": "Element"})
    source: str | None = field(default=None, metadata={"type": "Element"})


@dataclass(repr=False, kw_only=True)
class Schema(BaseInterface):
    """The subset of JSON Schema which is used to describe the values of inputs and
    outputs.

    Attributes:
        type: The JSON Schema type (`string`, `number`, `integer`, `boolean`, ...).
        format: The format of the value. Layer values carry `QSL_LAYER_FORMAT`.
        title: Human readable name, used on the entries of `one_of`.
        minimum: The inclusive minimum of a numeric value.
        maximum: The inclusive maximum of a numeric value.
        const: The only valid value, used on the entries of `one_of`.
        default: The value used when none is passed.
        one_of: The valid values, each as schema with `const` and `title`. For a file
            output the formats it is offered in, each as schema with
            `content_media_type`, the first one is the default.
        content_media_type: The media type of a value which is a file.
        x_qsl_layer: The marker of a layer value.
    """

    type: str | None = field(default=None, metadata={"type": "Element"})
    format: str | None = field(default=None, metadata={"type": "Element"})
    title: str | None = field(default=None, metadata={"type": "Element"})
    minimum: int | float | None = field(default=None, metadata={"type": "Element"})
    maximum: int | float | None = field(default=None, metadata={"type": "Element"})
    const: bool | int | float | str | None = field(default=None, metadata={"type": "Element"})
    default: bool | int | float | str | None = field(default=None, metadata={"type": "Element"})
    one_of: list["Schema"] | None = field(
        default=None, metadata={"type": "Element", "name": "oneOf"}
    )
    content_media_type: str | None = field(
        default=None, metadata={"type": "Element", "name": "contentMediaType"}
    )
    x_qsl_layer: QslLayerMarker | None = field(
        default=None, metadata={"type": "Element", "name": "x-qsl-layer"}
    )


@dataclass(repr=False, kw_only=True)
class InputDescription(BaseInterface):
    """The description of one input of a process.

    OGC API - Processes holds the inputs as map by id. xsdata can't bind a map of
    dataclasses, therefore the id is part of the description and the inputs are a list.

    Attributes:
        id: The identifier of the input, the QGIS parameter name.
        title: Human readable name.
        description: Human readable help text.
        schema: The schema of one value.
        min_occurs: The minimal number of values.
        max_occurs: The maximal number of values, `unbounded` for any.
    """

    id: str = field(metadata={"type": "Element"})
    title: str = field(metadata={"type": "Element"})
    description: str | None = field(default=None, metadata={"type": "Element"})
    schema: Schema = field(metadata={"type": "Element"})
    min_occurs: int = field(default=1, metadata={"type": "Element", "name": "minOccurs"})
    max_occurs: int | str = field(default=1, metadata={"type": "Element", "name": "maxOccurs"})

    @property
    def shortened_fields(self) -> set:
        return {"description"}


@dataclass(repr=False, kw_only=True)
class OutputDescription(BaseInterface):
    """The description of one output of a process. The id is part of the description,
    see `InputDescription`.

    Attributes:
        id: The identifier of the output, the QGIS output name.
        title: Human readable name.
        schema: The schema of the value.
    """

    id: str = field(metadata={"type": "Element"})
    title: str = field(metadata={"type": "Element"})
    schema: Schema = field(metadata={"type": "Element"})


@dataclass(repr=False, kw_only=True)
class ProcessDescription(BaseInterface):
    """The description of one process.

    Attributes:
        id: The identifier of the process, the QGIS algorithm id.
        title: Human readable name.
        description: Human readable help text.
        inputs: The inputs which are passed by the client. Destinations are not part of
            it, they are set by the worker.
        outputs: The outputs the process produces.
    """

    id: str = field(metadata={"type": "Element"})
    title: str = field(metadata={"type": "Element"})
    description: str | None = field(default=None, metadata={"type": "Element"})
    inputs: list[InputDescription] = field(default_factory=list, metadata={"type": "Element"})
    outputs: list[OutputDescription] = field(default_factory=list, metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"description"}


@dataclass(repr=False)
class ProcessDescriptions(BaseInterface):
    """The processes the process-workers serve. This is the content of the process
    registry (see `RedisProtocol.process_registry_key`).

    Attributes:
        processes: The description per process.
    """

    processes: list[ProcessDescription] = field(default_factory=list, metadata={"type": "Element"})

    def process_by_id(self, process_id: str) -> ProcessDescription:
        """
        Args:
            process_id: The identifier of the process.

        Raises:
            LookupError: If no process with this id is described.
        """
        for process in self.processes:
            if process.id == process_id:
                return process
        raise LookupError(f"Process `{process_id}` is not described")
