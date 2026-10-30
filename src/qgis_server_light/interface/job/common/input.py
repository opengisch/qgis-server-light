from abc import ABC
from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface, Style


@dataclass
class QslJobParameter(ABC):  # noqa: B024
    """The minimal interface of a job parameter interface. In the domain
    specific refinement it holds the relevant information about a job.
    """

    pass


@dataclass
class QslJobInfoParameter(ABC):  # noqa: B024
    """The common minimal interface of a job which is
    shipped around. Each job for QSL has to implement at least this
    interface.

    Attributes:
        id: The unique identifier which is used to recognize the job
            all over its lifecycle.
        type: A string based identifier of the job, this is used to quickly
            determine its nature serialized state.
        job: The actual job parameters. This is a domain specific dataclass
            depending on the nature of the actual job.
    """

    id: str = field(metadata={"type": "Element"})
    type: str = field(metadata={"type": "Element"})
    job: QslJobParameter = field(metadata={"type": "Element"})


@dataclass
class QslJobParameterMapRelated(QslJobParameter):
    """The minimal interface of a job parameter interface for jobs rendering things in the end.

    Attributes:
        svg_paths: A list of paths to svg's (folders) which are necessary for
            the job to render nicely.
    """

    svg_paths: list[str] = field(default_factory=list, metadata={"type": "Element"})


@dataclass(repr=False)
class AbstractFilter(BaseInterface):
    definition: str = field(metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"definition"}


@dataclass(repr=False)
class OgcFilter110(AbstractFilter):
    """
    A filter which definition conforms to
    https://schemas.opengis.net/filter/1.1.0/filter.xsd
    and which is consumable by `qgis.core.QgsOgcUtils.expressionFromOgcFilter`.
    """


@dataclass(repr=False)
class OgcFilterFES20(AbstractFilter):
    """
    A filter which definition conforms to https://www.opengis.net/fes/2.0
    and which is consumable by `qgis.core.QgsOgcUtils.expressionFromOgcFilter`.
    """


@dataclass(repr=False)
class QslJobLayer(BaseInterface):
    id: str = field(metadata={"type": "Element"})
    name: str = field(metadata={"type": "Element"})
    source: str = field(metadata={"type": "Element"})
    remote: bool = field(metadata={"type": "Element"})
    folder_name: str = field(metadata={"type": "Element"})
    driver: str = field(metadata={"type": "Element"})
    style: Style | None = field(default=None, metadata={"type": "Element"})
    filter: OgcFilter110 | OgcFilterFES20 | None = field(default=None, metadata={"type": "Element"})

    @property
    def redacted_fields(self) -> set:
        return {"source"}
