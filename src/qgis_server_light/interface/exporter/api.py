from dataclasses import dataclass
from dataclasses import field

from qgis_server_light.interface.common import BaseInterface
from qgis_server_light.interface.common import PgServiceConf


@dataclass(repr=False)
class ExportParameters(BaseInterface):
    """
    The serializable request parameters which are accepted by the exporter service.
    """

    mandant: str = field(metadata={"type": "Element"})
    project: str = field(metadata={"type": "Element"})
    unify_layer_names_by_group: bool = field(
        metadata={"type": "Element"}, default=False
    )
    output_format: str = field(metadata={"type": "Element"}, default="json")
    pg_service_configs: list[PgServiceConf] = field(
        metadata={"type": "Element"}, default_factory=list
    )

    @property
    def pg_service_configs_dict(self) -> dict:
        configurations = {}
        for config in self.pg_service_configs:
            configurations[config.name] = {
                "host": config.host,
                "port": config.port,
                "user": config.user,
                "dbname": config.dbname,
                "password": config.password,
                "sslmode": config.sslmode,
                "application_name": config.application_name,
                "client_encoding": config.client_encoding,
                "service": config.service,
            }
        return configurations


@dataclass(repr=False)
class ExportResult(BaseInterface):
    """
    The serializable response which is provided by the exporter service.
    """

    successful: bool = field(metadata={"type": "Element"})
