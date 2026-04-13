import logging
import sys
from typing import Optional

from qgis.analysis import QgsNativeAlgorithms
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputBoolean,
    QgsProcessingOutputDefinition,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputNumber,
    QgsProcessingOutputPointCloudLayer,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVectorLayer,
    QgsProcessingOutputVectorTileLayer,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterMapTheme,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
)

from qgis_server_light.interface.exporter.extract import (
    Algorithm,
    Output,
    Parameter,
    Process,
)
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.input import (
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.worker.runner.common import JobContext, MapRunner


def parameter_from_qgs_definition(param: QgsProcessingParameterDefinition) -> Parameter:
    if isinstance(param, QgsProcessingParameterFeatureSource):
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterRasterLayer):
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterFeatureSink):
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterMultipleLayers):
        schema = {"type": "array", "items": {"type": "string"}}
        if (min_items := param.minimumNumberInputs()) >= 1:
            schema["minItems"] = min_items
    elif isinstance(param, QgsProcessingParameterRasterDestination):
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterBand):
        schema = {"type": "integer", "minimum": 1}
        if param.allowMultiple():
            schema = {"type": "array", "minItems": 1, "items": schema}
    elif isinstance(param, QgsProcessingParameterNumber):
        match param.dataType():
            case Qgis.ProcessingNumberParameterType.Double:
                schema = {"type": "number"}
            case Qgis.ProcessingNumberParameterType.Integer:
                schema = {"type": "integer"}
        if (maximum := param.maximum()) < sys.float_info.max:
            schema["maximum"] = maximum
        if (minimum := param.minimum()) > sys.float_info.min:
            schema["minimum"] = minimum
    elif isinstance(param, QgsProcessingParameterString):
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterField):
        schema = {"type": "string"}
        if param.allowMultiple():
            schema = {"type": "array", "minItems": 1, "items": schema}
    elif isinstance(param, QgsProcessingParameterEnum):
        schema = {"type": "string", "enum": param.options()}
    elif isinstance(param, QgsProcessingParameterBoolean):
        schema = {"type": "boolean"}
    elif isinstance(param, QgsProcessingParameterExtent):
        schema = {
            "oneOf": [
                {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 6,
                    "maxItems": 6,
                },
            ]
        }
    elif isinstance(param, QgsProcessingParameterMapTheme):
        schema = {"type": "string"}
    else:
        print(f"parameter: {param}")
        raise NotImplementedError(f"parameter: {param}")

    return Parameter(
        name=param.name(),
        type=param.type(),
        description=param.description(),
        schema=schema,
        optional=bool(param.flags() & Qgis.ProcessingParameterFlag.Optional),
        default=param.defaultValue(),
    )


def output_from_qgs_definition(output: QgsProcessingOutputDefinition) -> Output:
    if isinstance(
        output,
        (
            QgsProcessingOutputMapLayer,
            QgsProcessingOutputPointCloudLayer,
            QgsProcessingOutputRasterLayer,
            QgsProcessingOutputVectorLayer,
            QgsProcessingOutputVectorTileLayer,
        ),
    ):
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputNumber):
        schema = {"type": "number"}
    elif isinstance(output, QgsProcessingOutputString):
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputBoolean):
        schema = {"type": "boolean"}
    else:
        print(f"output: {output}")
        raise NotImplementedError(f"output: {output}")
    return Output(
        name=output.name(),
        type=output.type(),
        description=output.description(),
        schema=schema,
    )


def algorithm_from_qgs_definition(alg: QgsProcessingAlgorithm) -> Algorithm:
    algorithm = Algorithm(
        id=alg.id(),
        name=alg.name(),
        display_name=alg.displayName(),
        help_string=alg.helpString(),
    )
    for param in alg.parameterDefinitions():
        algorithm.parameters.append(parameter_from_qgs_definition(param))
    for output in alg.outputDefinitions():
        algorithm.outputs.append(output_from_qgs_definition(output))
    return algorithm


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
        for foo in result.items():
            logging.info(foo)

        # for output in algorithm.outputDefinitions():
        #     if isinstance(
        #         output,
        #         (QgsProcessingOutputRasterLayer, QgsProcessingOutputVectorLayer),
        #     ):
        #         output_path = Path(self.context.base_path) / self.job_info.id
        #         output_path.mkdir(parents=True, exist_ok=True)
        #         layer_name = result[output.name()]

        #         suffix = (
        #             ".tif"
        #             if isinstance(output, QgsProcessingOutputRasterLayer)
        #             else ".gpkg"
        #         )
        #         output_filename = Path(layer_name).with_suffix(suffix)
        #         target_path = output_path / output_filename

        #         layer = context.getMapLayer(layer_name)
        #         logging.info(layer)

        #         result[output.name()] = str(target_path)

        return JobResult(
            id=self.job_info.id,
            data={"result": result, "ok": ok, "log": feedback.textLog()},
            content_type="application/json",
        )
