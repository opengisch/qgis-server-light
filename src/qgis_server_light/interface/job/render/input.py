from dataclasses import dataclass, field

from qgis_server_light.interface.common import BBox
from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
)


@dataclass(kw_only=True)
class QslJobParameterRender(QslJobParameter):
    """A runner to be rendered as an image"""

    layers: list[QslJobLayer] = field(metadata={"type": "Element"})
    bbox: BBox = field(metadata={"type": "Element"})
    crs: str = field(metadata={"type": "Element"})
    width: int = field(metadata={"type": "Element"})
    height: int = field(metadata={"type": "Element"})
    dpi: int | None = field(default=None, metadata={"type": "Element"})
    format: str = field(default="image/png", metadata={"type": "Element"})

    def get_layer_by_name(self, name: str) -> QslJobLayer:
        for layer in self.layers:
            if layer.name == name:
                return layer
        raise LookupError(f'No layer with name "{name} was found."')


@dataclass
class QslJobInfoRender(QslJobInfoParameter):
    job: QslJobParameterRender = field(metadata={"type": "Element", "required": True})
