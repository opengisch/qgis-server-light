import logging
import sys
from typing import Optional

from qgis.analysis import QgsNativeAlgorithms
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingDestinationParameter,
    QgsProcessingFeedback,
    QgsProcessingOutputBoolean,
    QgsProcessingOutputDefinition,
    QgsProcessingOutputFile,
    QgsProcessingOutputHtml,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputNumber,
    QgsProcessingOutputPointCloudLayer,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVectorLayer,
    QgsProcessingOutputVectorTileLayer,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterCrs,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExpression,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterLayout,
    QgsProcessingParameterMapTheme,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
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
        classname = "QgsProcessingParameterFeatureSource"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterVectorLayer):
        classname = "QgsProcessingParameterVectorLayer"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterRasterLayer):
        classname = "QgsProcessingParameterRasterLayer"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterFile):
        classname = "QgsProcessingParameterFile"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingDestinationParameter):
        classname = "QgsProcessingDestinationParameter"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterFeatureSink):
        classname = "QgsProcessingParameterFeatureSink"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterMultipleLayers):
        classname = "QgsProcessingParameterMultipleLayers"
        schema = {"type": "array", "items": {"type": "string"}}
        if (min_items := param.minimumNumberInputs()) >= 1:
            schema["minItems"] = min_items
    elif isinstance(param, QgsProcessingParameterBand):
        classname = "QgsProcessingParameterBand"
        schema = {"type": "integer", "minimum": 1}
        if param.allowMultiple():
            schema = {"type": "array", "minItems": 1, "items": schema}
    elif isinstance(param, QgsProcessingParameterNumber):
        classname = "QgsProcessingParameterNumber"
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
        classname = "QgsProcessingParameterString"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterExpression):
        classname = "QgsProcessingParameterExpression"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterCrs):
        classname = "QgsProcessingParameterCrs"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterLayout):
        classname = "QgsProcessingParameterLayout"
        schema = {"type": "string"}
    elif isinstance(param, QgsProcessingParameterField):
        classname = "QgsProcessingParameterField"
        schema = {"type": "string"}
        if param.allowMultiple():
            schema = {"type": "array", "minItems": 1, "items": schema}
    elif isinstance(param, QgsProcessingParameterEnum):
        classname = "QgsProcessingParameterEnum"
        schema = {"type": "string", "enum": param.options()}
    elif isinstance(param, QgsProcessingParameterBoolean):
        classname = "QgsProcessingParameterBoolean"
        schema = {"type": "boolean"}
    elif isinstance(param, QgsProcessingParameterExtent):
        classname = "QgsProcessingParameterExtent"
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
        classname = "QgsProcessingParameterMapTheme"
        schema = {"type": "string"}
    else:
        logging.error(f"invalid parameter: {param.name()}, {param.type()}, {param}")
        raise ValueError(f"parameter: {param}")

    return Parameter(
        name=param.name(),
        type=param.type(),
        description=param.description(),
        classname=classname,
        schema=schema,
        optional=bool(param.flags() & Qgis.ProcessingParameterFlag.Optional),
        default=param.defaultValue(),
    )


def output_from_qgs_definition(output: QgsProcessingOutputDefinition) -> Output:
    if isinstance(output, QgsProcessingOutputMapLayer):
        classname = "QgsProcessingOutputMapLayer"
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputPointCloudLayer):
        classname = "QgsProcessingOutputPointCloudLayer"
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputRasterLayer):
        classname = "QgsProcessingOutputRasterLayer"
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputVectorLayer):
        classname = "QgsProcessingOutputVectorLayer"
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputVectorTileLayer):
        classname = "QgsProcessingOutputVectorTileLayer"
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputFile):
        classname = "QgsProcessingOutputFile"
        schema = {"type": "number"}
    elif isinstance(output, QgsProcessingOutputHtml):
        classname = "QgsProcessingOutputHtml"
        schema = {"type": "number"}
    elif isinstance(output, QgsProcessingOutputNumber):
        classname = "QgsProcessingOutputNumber"
        schema = {"type": "number"}
    elif isinstance(output, QgsProcessingOutputString):
        classname = "QgsProcessingOutputString"
        schema = {"type": "string"}
    elif isinstance(output, QgsProcessingOutputBoolean):
        classname = "QgsProcessingOutputBoolean"
        schema = {"type": "boolean"}
    else:
        logging.error(f"invalid output: {output.name()}, {output.type()}, {output}")
        raise ValueError(f"output: {output}")
    return Output(
        name=output.name(),
        type=output.type(),
        description=output.description(),
        schema=schema,
        classname=classname,
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

        return JobResult(
            id=self.job_info.id,
            data={"result": result, "ok": ok, "log": feedback.textLog()},
            content_type="application/json",
        )
