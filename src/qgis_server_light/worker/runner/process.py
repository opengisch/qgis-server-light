from typing import Optional

from qgis.analysis import QgsNativeAlgorithms
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessingContext,
    QgsProcessingFeedback,
)

from qgis_server_light.exporter.extract import algorithm_from_qgs_definition
from qgis_server_light.interface.exporter.extract import (
    Process,
)
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.input import (
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class ProcessRunner(MapRunner):
    job_info_class = QslJobInfoExecuteProcess

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoExecuteProcess,
        layer_cache: Optional[dict],
    ):
        super().__init__(qgis, context, job_info, layer_cache)
        self.registry = self.qgis.processingRegistry()
        self.registry.addProvider(QgsNativeAlgorithms())

    @classmethod
    def info(cls, qgis: Qgis) -> Process:
        registry = qgis.processingRegistry()
        algorithms = registry.algorithms()
        process = Process()
        for alg in algorithms:
            algorithm = algorithm_from_qgs_definition(alg)
            process.algorithms.append(algorithm)
        return process

    def run(self):
        job: QslJobParameterExecuteProcess = self.job_info.job
        algorithm = self.registry.algorithmById(job.process_id)
        if algorithm is None:
            return JobResult(
                id=self.job_info.id,
                data={"result": {}, "ok": False, "log": "Algorithm not found"},
                content_type="application/json",
            )

        parameters = {}
        for param in job.parameters:
            if isinstance(param.value, QslJobLayer):
                parameters[param.name] = self._handle_layer_cache(param.value)
            elif isinstance(param.value, (str, int, float, bool)):
                parameters[param.name] = param.value
            else:
                raise ValueError(f"Unexpected value: {param.value}")

        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()
        result, ok = algorithm.run(parameters, context, feedback)

        return JobResult(
            id=self.job_info.id,
            data={"result": result, "ok": ok, "log": feedback.textLog()},
            content_type="application/json",
        )
