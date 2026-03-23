from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.job.common.input import (
    OgcFilterFES20,
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
)


@dataclass
class FeatureQuery(BaseInterface):
    """Represents definitions of a query to obtain features from a list of layers.
    Be aware, that filters are not applied to the QslJobLayer in this implementation
    since passed filters can contain inter-layer-references.

    Attributes:
        layers: A list layers which should only reference vector sources and be queried.
        aliases: An optional list of alias names. This has to be the same length as the list of datasets.
        filter: An optional filter which might reference all passed layers thats why layers
            has to be added
    """

    layers: list[QslJobLayer] = field(metadata={"type": "Element"})
    aliases: list[str] = field(default_factory=list, metadata={"type": "Element"})
    filter: OgcFilterFES20 = field(default=None, metadata={"type": "Element"})


@dataclass
class QslJobParameterFeature(QslJobParameter):
    """As defined in WFS 2.0 specs, a request can be subdivided in a list of queries.
    This class is representing that.

    Attributes:
        queries: A list of queries which features should be extracted for.
        start_index: The offset for paging reason.
        count: The number of results to return.
    """

    queries: list[FeatureQuery] = field(metadata={"type": "Element"})
    start_index: int = field(
        default=0,
        metadata={
            "type": "Element",
        },
    )
    count: int | None = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )


@dataclass
class QslJobInfoFeature(QslJobInfoParameter):
    job: QslJobParameterFeature = field(metadata={"type": "Element"})
