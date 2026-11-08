from collections.abc import MutableMapping
import shutil
from pathlib import Path
from qgis.core import (
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
)
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.description import ProcessDescriptions
from qgis_server_light.interface.job.process.input import (
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.process.output import (
    FileOutput,
    ParameterOutput,
    ProcessResult,
)
from qgis_server_light.processing.description import ProcessDescriptionMapper
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class ProcessRunner(MapRunner):
    job_info_class = QslJobInfoExecuteProcess
    media_type_by_extension = {
        "gpkg": "application/geopackage+sqlite3",
        "geojson": "application/geo+json",
        "tif": "image/tiff; application=geotiff",
        "csv": "text/csv",
        "html": "text/html",
    }

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
        if self.context.process_output_dir is None:
            raise RuntimeError("No process output dir configured")

        parameters = self._parameters(algorithm, job)
        job_output_dir = Path(self.context.process_output_dir, self.job_info.id)
        destinations = self._destinations(algorithm, job_output_dir)
        parameters.update({name: str(path) for name, path in destinations.items()})

        job_output_dir.mkdir(parents=True)
        try:
            process_result = self._run_algorithm(algorithm, parameters, destinations)
        except Exception:
            # only successful jobs leave files behind (we avoid half created corpse)
            shutil.rmtree(job_output_dir, ignore_errors=True)
            raise

        return JobResult(
            id=self.job_info.id,
            data=JsonSerializer().render(process_result).encode(),
            content_type="application/qgis-server-light.interface.job.process.ProcessResult",
        )

    def _parameters(
        self, algorithm: QgsProcessingAlgorithm, job: QslJobParameterExecuteProcess
    ) -> dict:
        """The parameters the client sent, mapped to what the algorithm expects.
        Destinations are left out, the worker sets them on its own.

        Raises:
            ValueError: If the client sent a destination or a value of an
                unexpected type.
        """
        parameters = {}
        for param in job.parameters:
            definition = algorithm.parameterDefinition(param.name)
            if definition is not None and definition.isDestination():
                raise ValueError(f"Destination `{param.name}` is set by the worker")
            if isinstance(param.value, QslJobLayer):
                parameters[param.name] = self._handle_layer_cache(param.value)
            elif isinstance(param.value, (str, int, float, bool)):
                parameters[param.name] = param.value
            else:
                raise ValueError(f"Unexpected value: {param.value}")
        return parameters

    def _destinations(
        self, algorithm: QgsProcessingAlgorithm, job_output_dir: Path
    ) -> dict[str, Path]:
        """The files the destinations of the algorithm are written to, by
        destination name. The worker sets them, so concurrent jobs never collide.

        Raises:
            ValueError: If there is no media type for the file extension of a
                destination.
        """
        destinations = {}
        for definition in algorithm.destinationParameterDefinitions():
            extension = definition.defaultFileExtension()
            if extension not in self.media_type_by_extension:
                raise ValueError(
                    f"No media type for extension `{extension}` of destination "
                    f"`{definition.name()}`"
                )
            destinations[definition.name()] = job_output_dir / f"{definition.name()}.{extension}"
        return destinations

    def _file_output(self, destination: Path) -> FileOutput:
        """The destination as the client sees it, relative to the process output
        dir, so the worker does not leak its own file system layout."""
        return FileOutput(
            path=destination.relative_to(self.context.process_output_dir).as_posix(),
            media_type=self.media_type_by_extension[destination.suffix.removeprefix(".")],
        )

    def _run_algorithm(
        self,
        algorithm: QgsProcessingAlgorithm,
        parameters: dict,
        destinations: dict[str, Path],
    ) -> ProcessResult:
        """Runs the algorithm and collects its outputs. Outputs written to a
        file are referenced, all others are returned inline.

        Raises:
            RuntimeError: If the algorithm failed.
            ValueError: If an output is neither a file nor a literal value.
        """
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()
        result, ok = algorithm.run(parameters, context, feedback)
        if not ok:
            raise RuntimeError(f"Algorithm `{algorithm.id()}` failed: {feedback.textLog()}")

        process_result = ProcessResult(log=feedback.textLog())
        for name, value in result.items():
            if name in destinations:
                process_result.outputs.append(
                    ParameterOutput(name, self._file_output(destinations[name]))
                )
            elif isinstance(value, (str, int, float, bool)):
                process_result.outputs.append(ParameterOutput(name, value))
            else:
                raise ValueError(f"Unexpected output value: {value}")
        return process_result
