from dataclasses import dataclass, field

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobLayer,
    QslJobParameter,
)


@dataclass(kw_only=True)
class QslJobParameterLegend(QslJobParameter):
    """Render legend graphics for one or more layers."""

    layers: list[QslJobLayer] = field(metadata={"type": "Element"})
    format: str = field(default="image/png", metadata={"type": "Element"})
    width: int | None = field(default=None, metadata={"type": "Element"})
    height: int | None = field(default=None, metadata={"type": "Element"})
    dpi: int = field(default=91, metadata={"type": "Element"})
    scale: float | None = field(default=None, metadata={"type": "Element"})
    layer_title: bool = field(default=False, metadata={"type": "Element"})

    def get_layer_by_name(self, name: str) -> QslJobLayer:
        for layer in self.layers:
            if layer.name == name:
                return layer
        raise LookupError(f'No layer with name "{name}" was found.')


@dataclass
class QslJobInfoLegend(QslJobInfoParameter):
    job: QslJobParameterLegend = field(metadata={"type": "Element", "required": True})
