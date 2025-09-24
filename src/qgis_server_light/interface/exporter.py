
from dataclasses import dataclass, field
from typing import Optional



@dataclass
class ExportParameters:
    mandant: str = field(metadata={"type": "Element"})
    project: str = field(metadata={"type": "Element"})
    unify_layer_names_by_group: bool = field(metadata={"type": "Element"}, default=False)
    output_format: str = field(metadata={"type": "Element"}, default="json")

@dataclass
class ExportResult:
    pass