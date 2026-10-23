import logging

from qgis.core import QgsApplication, QgsCoordinateReferenceSystem
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.crs import create_qsl_crs
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.crs.input import QslJobInfoCrs
from qgis_server_light.interface.job.crs.output import CrsCollection
from qgis_server_light.worker.runner.common import JobContext, Runner


class CrsRunner(Runner):
    """Resolves crs identifiers, it needs neither a map nor layers."""

    job_info_class = QslJobInfoCrs

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoCrs,
        layer_cache: dict | None = None,
    ) -> None:
        self.qgis = qgis
        self.context = context
        self.job_info = job_info

    def run(self):
        crs_collection = CrsCollection()
        for identifier in self.job_info.job.identifiers:
            crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(identifier)
            if not crs.isValid():
                raise RuntimeError(f"Crs `{identifier}` is not valid")
            crs_collection.crs.append(create_qsl_crs(crs))
            logging.info(f" Resolved crs `{identifier}`")
        return JobResult(
            id=self.job_info.id,
            data=JsonSerializer().render(crs_collection).encode(),
            content_type="application/qgis-server-light.interface.qgis.CrsCollection",
        )
