from dataclasses import dataclass, field

from qgis_server_light.interface.job.common.input import (
    QslJobInfoParameter,
    QslJobParameter,
)


@dataclass
class QslJobParameterCrs(QslJobParameter):
    """Resolves crs identifiers into the full crs information as QGIS knows it. This way
    consuming applications get all identifiers and the axis order without own crs
    knowledge.

    Attributes:
        identifiers: The crs identifiers to resolve, e.g. `EPSG:4326`, URN or URI notation.
    """

    identifiers: list[str] = field(metadata={"type": "Element"})


@dataclass
class QslJobInfoCrs(QslJobInfoParameter):
    job: QslJobParameterCrs = field(metadata={"type": "Element"})
