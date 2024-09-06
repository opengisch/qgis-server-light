import inspect
import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import List

from qgis_server_light.interface.qgis import Custom
from qgis_server_light.interface.qgis import Raster
from qgis_server_light.interface.qgis import Vector

log = logging.getLogger(__name__)


@dataclass
class AbstractWmsParams:
    BBOX: str = field(metadata={"type": "Element", "required": True})
    CRS: str = field(metadata={"type": "Element", "required": True})
    WIDTH: str = field(metadata={"type": "Element", "required": True})
    HEIGHT: str = field(metadata={"type": "Element", "required": True})
    # optional parameters
    DPI: str = field(default=None, metadata={"type": "Element", "required": False})
    FORMAT_OPTIONS: str = field(
        default=None, metadata={"type": "Element", "required": False}
    )
    STYLES: str = field(
        default_factory=list, metadata={"type": "Element", "required": False}
    )

    @property
    def dpi(self) -> int | None:
        if self.DPI is not None:
            return int(self.DPI)
        elif self.FORMAT_OPTIONS is not None:
            return int(self.FORMAT_OPTIONS.split(":")[-1])
        else:
            return None

    @property
    def bbox(self) -> List[str]:
        return self.BBOX.split(",")

    @classmethod
    def from_overloaded_dict(cls, params: dict):
        return cls(
            **{
                k: v
                for k, v in params.items()
                if k in inspect.signature(cls).parameters
            }
        )


@dataclass(kw_only=True)
class WmsGetMapParams(AbstractWmsParams):
    """Represents query parameters from the original WMS request"""

    LAYERS: str = field(metadata={"type": "Element", "required": True})

    # mime type of the requested image
    FORMAT: str = field(
        default="image/png", metadata={"type": "Element", "required": True}
    )

    @property
    def layers(self) -> List[str]:
        return self.LAYERS.split(",")


class WmsGetFeatureInfoParams(AbstractWmsParams):
    X: str = field(default=None, metadata={"type": "Element", "required": True})
    Y: str = field(default=None, metadata={"type": "Element", "required": True})
    I: str = field(default=None, metadata={"type": "Element", "required": True})
    J: str = field(default=None, metadata={"type": "Element", "required": True})
    INFO_FORMAT: str = field(metadata={"type": "Element", "required": True})

    # mime type, only application/json supported
    QUERY_LAYERS: str = field(metadata={"type": "Element", "required": True})

    def __post_init__(self):
        x = int(self.I or self.X)
        y = int(self.J or self.Y)
        if x is None or y is None:
            raise KeyError(
                "Parameter `I` or `X` and `J` or `Y`  are mandatory for GetFeatureInfo"
            )
        if self.QUERY_LAYERS is None:
            raise KeyError("QUERY_LAYERS is mandatory in this request")

    @property
    def x(self) -> int:
        return int(self.I or self.X)

    @property
    def y(self) -> int:
        return int(self.J or self.Y)

    @property
    def query_layers(self):
        return self.QUERY_LAYERS.split(",")


class QslAbstractJob:
    svg_paths: List[str] = field(metadata={"type": "Element", "required": True})


@dataclass
class QslGetMapJob(QslAbstractJob):
    """A job to be rendered as an image"""

    service_params: WmsGetMapParams = field(
        metadata={"type": "Element", "required": True}
    )

    raster_layers: List[Raster] = field(metadata={"type": "Element", "required": True})

    vector_layers: List[Vector] = field(metadata={"type": "Element", "required": True})

    custom_layers: List[Custom] = field(metadata={"type": "Element", "required": True})

    def get_layer_by_name(self, name: str) -> Raster | Vector | Custom:
        name = name.lower()
        for layer in self.raster_layers + self.vector_layers + self.custom_layers:
            if layer.name == name:
                return layer
        raise AttributeError(f'No layer with name "{name} was found."')


@dataclass
class QslGetFeatureInfoJob(QslAbstractJob):
    """A job to extract feature info"""

    service_params: WmsGetFeatureInfoParams = field(
        metadata={"type": "Element", "required": True}
    )


@dataclass
class QslLegendJob(QslAbstractJob):
    """Render legend"""


@dataclass
class JobResult:
    data: Any = field(metadata={"type": "Element", "required": True})
    content_type: str = field(metadata={"type": "Element", "required": True})


@dataclass
class AbstractJobRunnerInfo:
    id: str = field(metadata={"type": "Element", "required": True})
    type: str = field(metadata={"type": "Element", "required": True})


@dataclass
class JobRunnerInfoQslGetMapJob(AbstractJobRunnerInfo):
    job: QslGetMapJob = field(metadata={"type": "Element", "required": True})


@dataclass
class JobRunnerInfoQslGetFeatureInfoJob(AbstractJobRunnerInfo):
    job: QslGetFeatureInfoJob = field(metadata={"type": "Element", "required": True})


@dataclass
class JobRunnerInfoQslLegendJob(AbstractJobRunnerInfo):
    job: QslLegendJob = field(metadata={"type": "Element", "required": True})
