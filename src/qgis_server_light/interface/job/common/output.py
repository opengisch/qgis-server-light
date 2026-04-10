from dataclasses import dataclass, field
from typing import Any

from qgis_server_light.interface.common import BaseInterface


@dataclass
class JobResult(BaseInterface):
    id: str = field(metadata={"type": "Element"})
    data: Any = field(metadata={"type": "Element"})
    content_type: str = field(metadata={"type": "Element"})
    worker_id: str | None = field(default=None, metadata={"type": "Element"})
    worker_host_name: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"data"}
