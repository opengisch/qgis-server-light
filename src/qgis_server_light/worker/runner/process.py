from collections.abc import MutableMapping
from qgis.core import (
    QgsApplication,
    QgsProcessingContext,
    QgsProcessingFeedback,
)

from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.description import ProcessDescriptions
from qgis_server_light.interface.job.process.input import (
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.processing.description import ProcessDescriptionMapper
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class ProcessRunner(MapRunner):
    job_info_class = QslJobInfoExecuteProcess

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoExecuteProcess,
        layer_cache: MutableMapping | None = None,
    ):
        super().__init__(qgis, context, job_info, layer_cache)
        self.registry = self.qgis.processingRegistry()

    @classmethod
    def info(cls, qgis: QgsApplication, process_allowlist: list[str]) -> ProcessDescriptions:
        """The descriptions of the processes the worker serves.

        Args:
            qgis: The QGIS application holding the processing registry.
            process_allowlist: The ids of the QGIS algorithms the worker serves.

        Raises:
            LookupError: If an algorithm of the allowlist is not in the processing registry.
        """
        registry = qgis.processingRegistry()
        mapper = ProcessDescriptionMapper()
        process_descriptions = ProcessDescriptions()
        for process_id in process_allowlist:
            algorithm = registry.algorithmById(process_id)
            if algorithm is None:
                raise LookupError(f"Algorithm `{process_id}` of the allowlist not found")
            process_descriptions.processes.append(mapper.process_description(algorithm))
        return process_descriptions

    def run(self):
        job: QslJobParameterExecuteProcess = self.job_info.job
        if job.process_id not in self.context.process_allowlist:
            raise RuntimeError(f"Algorithm `{job.process_id}` is not served by this worker")
        algorithm = self.registry.algorithmById(job.process_id)
        if algorithm is None:
            raise RuntimeError(f"Algorithm `{job.process_id}` not found")

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
        if not ok:
            raise RuntimeError(f"Algorithm `{job.process_id}` failed: {feedback.textLog()}")

        return JobResult(
            id=self.job_info.id,
            data={"result": result, "ok": ok, "log": feedback.textLog()},
            content_type="application/json",
        )
