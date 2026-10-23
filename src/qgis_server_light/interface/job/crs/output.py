from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface, Crs


@dataclass(repr=False)
class CrsCollection(BaseInterface):
    """Holds the resolved crs. The order in the list has to be not changed, so that
    consuming applications can map the response to the passed identifiers.

    Attributes:
        crs: The resolved crs in the order of the passed identifiers.
    """

    crs: list[Crs] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
