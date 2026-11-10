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
    OutputFormat,
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
    """Responsible for executing a QGIS processing algorithm as a process.

    The runner decides on its own where the outputs go, the client only sends
    the inputs. This way concurrent jobs never write into the same file and a
    client can't make the worker write anywhere on its file system.

    The format of a file output is chosen by the client among the media types
    the process description offers for it, without a choice the first offered
    one is used. Vector layers default to GeoJSON, because it takes any data:
    a GeoPackage takes an input attribute `fid` as its feature id and fails if
    the values are not unique, FlatGeobuf refuses features without geometry
    because of its spatial index.

    Attributes:
        extension_by_media_type: The file extension a destination gets for the
            media type of its output.
        media_type_by_extension: The media type of a destination file, by its
            extension.
    """

    job_info_class = QslJobInfoExecuteProcess
    extension_by_media_type = {
        "application/geo+json": "geojson",
        "application/geopackage+sqlite3": "gpkg",
        "application/flatgeobuf": "fgb",
        "image/tiff; application=geotiff": "tif",
        "text/html": "html",
    }
    media_type_by_extension = {
        "geojson": "application/geo+json",
        "gpkg": "application/geopackage+sqlite3",
        "fgb": "application/flatgeobuf",
        "tif": "image/tiff; application=geotiff",
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
        """Run this runner.

        Every job writes into its own dir `{process_output_dir}/{job_id}`. If the
        job fails, the dir is removed again, so only successful jobs leave files
        behind.

        Returns:
            A JobResult with the ProcessResult as JSON.

        Raises:
            RuntimeError: If the algorithm is not served by this worker, is not
                found or no process output dir is configured.
        """
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
        destinations = self._destinations(algorithm, job_output_dir, job.output_formats)
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

        Args:
            algorithm: The algorithm the parameters are meant for.
            job: The job holding the parameters of the client.

        Returns:
            The parameters by name, ready to be passed to the algorithm.

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
        self,
        algorithm: QgsProcessingAlgorithm,
        job_output_dir: Path,
        output_formats: list[OutputFormat],
    ) -> dict[str, Path]:
        """The files the destinations of the algorithm are written to, by
        destination name. The worker sets them, so concurrent jobs never collide.
        The format is checked here, before the algorithm runs, so a job doesn't
        do all the work only to fail on an output nobody asked for.

        Args:
            algorithm: The algorithm whose destinations are set.
            job_output_dir: The dir of the job, the destination files go into.
            output_formats: The formats the client chose for the outputs.

        Returns:
            The absolute destination files by destination name.

        Raises:
            ValueError: If the client chose a format for an output which is no
                destination or a format the description does not offer.
        """
        media_type_by_name = {
            output_format.name: output_format.media_type for output_format in output_formats
        }
        destination_names = [
            definition.name() for definition in algorithm.destinationParameterDefinitions()
        ]
        if unknown_names := set(media_type_by_name) - set(destination_names):
            raise ValueError(f"Format chosen for unknown outputs: {sorted(unknown_names)}")

        mapper = ProcessDescriptionMapper()
        destinations = {}
        for name in destination_names:
            output_description = mapper.output_description(algorithm.outputDefinition(name))
            offered = [schema.content_media_type for schema in output_description.schema.one_of]
            media_type = media_type_by_name.get(name, offered[0])
            if media_type not in offered:
                raise ValueError(f"Format `{media_type}` is not offered for output `{name}`")
            destinations[name] = (
                job_output_dir / f"{name}.{self.extension_by_media_type[media_type]}"
            )
        return destinations

    def _file_output(self, destination: Path) -> FileOutput:
        """The destination as the client sees it, relative to the process output
        dir, so the worker does not leak its own file system layout.

        Args:
            destination: The absolute destination file as set by `_destinations`.

        Returns:
            The relative path and the media type of the file.
        """
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
        file are referenced, all others are returned inline. For files the
        destination the worker set counts, not the path QGIS returns.

        Args:
            algorithm: The algorithm to run.
            parameters: The parameters by name, destinations included.
            destinations: The destination files by destination name.

        Returns:
            The outputs and the log of the algorithm.

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
