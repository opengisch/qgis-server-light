from dataclasses import dataclass, field

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobParameter,
)


@dataclass(kw_only=True)
class QslJobParameterFeatureInfo(QslJobParameter):
    """A runner to extract feature info"""

    # mime type, only application/json supported
    INFO_FORMAT: str = field(metadata={"type": "Element"})
    QUERY_LAYERS: str = field(metadata={"type": "Element"})
    X: str | None = field(default=None, metadata={"type": "Element"})
    Y: str | None = field(default=None, metadata={"type": "Element"})
    I: str | None = field(default=None, metadata={"type": "Element"})  # noqa: E741
    J: str | None = field(default=None, metadata={"type": "Element"})

    def __post_init__(self):
        x = int(self.I or self.X)
        y = int(self.J or self.Y)
        if x is None or y is None:
            raise KeyError("Parameter `I` or `X` and `J` or `Y`  are mandatory for GetFeatureInfo")
        if self.QUERY_LAYERS is None:
            raise KeyError("QUERY_LAYERS is mandatory in this request")

    @property
    def decide_x(self) -> int:
        return int(self.I or self.X)

    @property
    def decide_y(self) -> int:
        return int(self.J or self.Y)

    @property
    def query_layers_list(self):
        return self.QUERY_LAYERS.split(",")


@dataclass
class QslJobInfoFeatureInfo(QslJobInfoParameter):
    job: QslJobParameterFeatureInfo = field(metadata={"type": "Element", "required": True})
