from qgis_server_light.interface.job.legend.input import QslJobInfoLegend
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class GetLegendRunner(MapRunner):
    def __init__(self, qgis, context: JobContext, job_info: QslJobInfoLegend) -> None:
        super().__init__(qgis, context, job_info)

    def run(self):
        # TODO Implement ....
        raise NotImplementedError()
