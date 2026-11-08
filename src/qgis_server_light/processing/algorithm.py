"""This module translates QGIS processing definitions into the `Algorithm` of the
QGIS-Server-Light interface. It is replaced by `processing.description` once Georama reads
the process registry."""

import logging
import sys

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingOutputBoolean,
    QgsProcessingOutputDefinition,
    QgsProcessingOutputFile,
    QgsProcessingOutputHtml,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputNumber,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVectorLayer,
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
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
)

from qgis_server_light.interface.exporter.extract import (
    Algorithm,
    Output,
    Parameter,
    ProcessingParameterType,
    ProcessingParameterTypeAnyLayer,
    ProcessingParameterTypeBand,
    ProcessingParameterTypeBoolean,
    ProcessingParameterTypeCrs,
    ProcessingParameterTypeEnum,
    ProcessingParameterTypeExpression,
    ProcessingParameterTypeExtent,
    ProcessingParameterTypeField,
    ProcessingParameterTypeFile,
    ProcessingParameterTypeFloat,
    ProcessingParameterTypeInt,
    ProcessingParameterTypeLayout,
    ProcessingParameterTypeMapLayer,
    ProcessingParameterTypeMapTheme,
    ProcessingParameterTypeRasterLayer,
    ProcessingParameterTypeString,
    ProcessingParameterTypeVectorLayer,
)


def parameter_type_from_qgs_definition(
    param: QgsProcessingParameterDefinition,
) -> ProcessingParameterType:
    if isinstance(param, QgsProcessingParameterFeatureSource):
        return ProcessingParameterTypeVectorLayer()
    if isinstance(param, QgsProcessingParameterVectorLayer):
        return ProcessingParameterTypeVectorLayer()
    if isinstance(param, QgsProcessingParameterRasterLayer):
        return ProcessingParameterTypeRasterLayer()
    if isinstance(param, QgsProcessingParameterFile):
        return ProcessingParameterTypeFile()
    if isinstance(param, QgsProcessingParameterFeatureSink):
        return ProcessingParameterTypeVectorLayer()
    if isinstance(param, QgsProcessingParameterVectorDestination):
        return ProcessingParameterTypeVectorLayer()
    if isinstance(param, QgsProcessingParameterRasterDestination):
        return ProcessingParameterTypeRasterLayer()
    if isinstance(param, QgsProcessingParameterMultipleLayers):
        minimum = param.minimumNumberInputs()
        match param.layerType():
            case Qgis.ProcessingSourceType.MapLayer:
                layer_type = ProcessingParameterTypeMapLayer()
            case Qgis.ProcessingSourceType.Raster:
                layer_type = ProcessingParameterTypeRasterLayer()
            case (
                Qgis.ProcessingSourceType.Vector
                | Qgis.ProcessingSourceType.VectorAnyGeometry
                | Qgis.ProcessingSourceType.VectorPoint
                | Qgis.ProcessingSourceType.VectorLine
                | Qgis.ProcessingSourceType.VectorPolygon
            ):
                layer_type = ProcessingParameterTypeVectorLayer()
            case unsupported:
                raise ValueError(f"unsupported ProcessingSourceType: {unsupported}")
        return ProcessingParameterTypeAnyLayer(
            layer_type=layer_type,
            minimum=minimum,
        )
    if isinstance(param, QgsProcessingParameterBand):
        return ProcessingParameterTypeBand(allow_multiple=param.allowMultiple())
    if isinstance(param, QgsProcessingParameterNumber):
        if (maximum := param.maximum()) >= sys.float_info.max:
            maximum = None
        if (minimum := param.minimum()) <= -sys.float_info.max:
            minimum = None
        match param.dataType():
            case Qgis.ProcessingNumberParameterType.Double:
                return ProcessingParameterTypeFloat(minimum=minimum, maximum=maximum)
            case Qgis.ProcessingNumberParameterType.Integer:
                minimum = None if minimum is None else int(minimum)
                maximum = None if maximum is None else int(maximum)
                return ProcessingParameterTypeInt(minimum=minimum, maximum=maximum)
    if isinstance(param, QgsProcessingParameterString):
        return ProcessingParameterTypeString()
    if isinstance(param, QgsProcessingParameterExpression):
        return ProcessingParameterTypeExpression()
    if isinstance(param, QgsProcessingParameterCrs):
        return ProcessingParameterTypeCrs()
    if isinstance(param, QgsProcessingParameterLayout):
        return ProcessingParameterTypeLayout()
    if isinstance(param, QgsProcessingParameterField):
        return ProcessingParameterTypeField(allow_multiple=param.allowMultiple())
    if isinstance(param, QgsProcessingParameterEnum):
        return ProcessingParameterTypeEnum(
            options=param.options(), allow_multiple=param.allowMultiple()
        )
    if isinstance(param, QgsProcessingParameterBoolean):
        return ProcessingParameterTypeBoolean()
    if isinstance(param, QgsProcessingParameterExtent):
        return ProcessingParameterTypeExtent()
    if isinstance(param, QgsProcessingParameterMapTheme):
        return ProcessingParameterTypeMapTheme()
    else:
        logging.error(f"invalid parameter: {param.name()}, {param.type()}, {param}")
        raise ValueError(f"parameter: {param}")


def parameter_from_qgs_definition(param: QgsProcessingParameterDefinition) -> Parameter:
    return Parameter(
        name=param.name(),
        type=parameter_type_from_qgs_definition(param),
        description=param.description(),
        optional=bool(param.flags() & Qgis.ProcessingParameterFlag.Optional),
        default=param.defaultValue(),
        is_destination=param.isDestination(),
    )


def output_type_from_qgs_definition(output: QgsProcessingOutputDefinition) -> Output:
    if isinstance(output, QgsProcessingOutputMapLayer):
        return ProcessingParameterTypeMapLayer()
    elif isinstance(output, QgsProcessingOutputRasterLayer):
        return ProcessingParameterTypeRasterLayer()
    elif isinstance(output, QgsProcessingOutputVectorLayer):
        return ProcessingParameterTypeVectorLayer()
    elif isinstance(output, QgsProcessingOutputFile):
        return ProcessingParameterTypeFile()
    elif isinstance(output, QgsProcessingOutputHtml):
        return ProcessingParameterTypeString()
    elif isinstance(output, QgsProcessingOutputNumber):
        return ProcessingParameterTypeFloat()
    elif isinstance(output, QgsProcessingOutputString):
        return ProcessingParameterTypeString()
    elif isinstance(output, QgsProcessingOutputBoolean):
        return ProcessingParameterTypeBoolean()
    else:
        logging.error(f"invalid output: {output.name()}, {output.type()}, {output}")
        raise ValueError(f"output: {output}")


def output_from_qgs_definition(output: QgsProcessingOutputDefinition) -> Output:
    return Output(
        name=output.name(),
        description=output.description(),
        type=output_type_from_qgs_definition(output),
    )


def algorithm_from_qgs_definition(alg: QgsProcessingAlgorithm) -> Algorithm:
    algorithm = Algorithm(
        id=alg.id(),
        name=alg.name(),
        display_name=alg.displayName(),
        short_help_string=alg.shortHelpString(),
        short_description=alg.shortDescription(),
    )
    for param in alg.parameterDefinitions():
        algorithm.parameters.append(parameter_from_qgs_definition(param))
    for output in alg.outputDefinitions():
        algorithm.outputs.append(output_from_qgs_definition(output))
    return algorithm
