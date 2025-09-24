from dataclasses import dataclass
from dataclasses import field


@dataclass
class ExportParameters:
    mandant: str = field(metadata={"type": "Element"})
    project: str = field(metadata={"type": "Element"})
    unify_layer_names_by_group: bool = field(
        metadata={"type": "Element"}, default=False
    )
    output_format: str = field(metadata={"type": "Element"}, default="json")


@dataclass
class ExportResult:
    successful: bool = field(metadata={"type": "Element"})
