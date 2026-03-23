from dataclasses import dataclass, field

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobParameter,
)


@dataclass(kw_only=True)
class QslJobParameterLegend(QslJobParameter):
    """Render legend"""


@dataclass
class QslJobInfoLegend(QslJobInfoParameter):
    job: QslJobParameterLegend = field(metadata={"type": "Element", "required": True})
