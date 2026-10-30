from dataclasses import dataclass, field

from qgis_server_light.interface.common import BaseInterface


@dataclass(repr=False)
class ExportParameters(BaseInterface):
    """
    The serializable request parameters which are accepted by the exporter service.
    """

    project_path: str = field(metadata={"type": "Element"})
    unify_layer_names_by_group: bool = field(metadata={"type": "Element"}, default=False)
    output_format: str = field(metadata={"type": "Element"}, default="json")


@dataclass(repr=False)
class ExportResult(BaseInterface):
    """
    The serializable response which is provided by the exporter service.
    """

    successful: bool = field(metadata={"type": "Element"})
    content: str = field(metadata={"type": "Element"})
