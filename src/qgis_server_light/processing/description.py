"""This module translates QGIS processing algorithms into the process descriptions of the
QGIS-Server-Light interface (`interface.job.process.description`), shaped along
OGC API - Processes."""

import sys
from abc import ABC, abstractmethod

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingOutputBoolean,
    QgsProcessingOutputDefinition,
    QgsProcessingOutputHtml,
    QgsProcessingOutputNumber,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterDistance,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
)

from qgis_server_light.interface.job.process.description import (
    QSL_LAYER_FORMAT,
    InputDescription,
    OutputDescription,
    ProcessDescription,
    QslLayerKind,
    QslLayerMarker,
    Schema,
)


class SchemaStrategy[D: QgsProcessingParameterDefinition | QgsProcessingOutputDefinition](ABC):
    """Maps one kind of QGIS parameter or output definition onto the schema of its value.
    `D` is the QGIS definition class the strategy handles."""

    @abstractmethod
    def map_schema(self, definition: D) -> Schema:
        raise NotImplementedError

    def occurs(self, definition: D, optional: bool) -> tuple[int, int | str]:
        """The minimal and maximal number of values of an input.

        Args:
            definition: The QGIS parameter definition.
            optional: If the parameter is optional.
        """
        return (0 if optional else 1), 1


class LiteralSchemaStrategy(SchemaStrategy[QgsProcessingParameterDefinition]):
    """A parameter with a plain JSON Schema type and the QGIS default as default."""

    def __init__(self, json_type: str):
        self.json_type = json_type

    def map_schema(self, definition: QgsProcessingParameterDefinition) -> Schema:
        return Schema(type=self.json_type, default=definition.defaultValue())


class LiteralOutputSchemaStrategy(SchemaStrategy[QgsProcessingOutputDefinition]):
    """An output with a plain JSON Schema type."""

    def __init__(self, json_type: str):
        self.json_type = json_type

    def map_schema(self, definition: QgsProcessingOutputDefinition) -> Schema:
        return Schema(type=self.json_type)


class NumberSchemaStrategy(SchemaStrategy[QgsProcessingParameterNumber]):
    def bounds(self, definition: QgsProcessingParameterNumber) -> tuple[float | None, float | None]:
        """The bounds of the number, `None` where QGIS sets no bound."""
        if (minimum := definition.minimum()) <= -sys.float_info.max:
            minimum = None
        if (maximum := definition.maximum()) >= sys.float_info.max:
            maximum = None
        return minimum, maximum

    def map_schema(self, definition: QgsProcessingParameterNumber) -> Schema:
        """
        Raises:
            ValueError: If the number type is not supported.
        """
        minimum, maximum = self.bounds(definition)
        match definition.dataType():
            case Qgis.ProcessingNumberParameterType.Double:
                return Schema(
                    type="number",
                    minimum=minimum,
                    maximum=maximum,
                    default=definition.defaultValue(),
                )
            case Qgis.ProcessingNumberParameterType.Integer:
                return Schema(
                    type="integer",
                    minimum=None if minimum is None else int(minimum),
                    maximum=None if maximum is None else int(maximum),
                    default=definition.defaultValue(),
                )
            case unsupported:
                raise ValueError(f"unsupported ProcessingNumberParameterType: {unsupported}")


class EnumSchemaStrategy(SchemaStrategy[QgsProcessingParameterEnum]):
    """The options as `one_of`. The value is the option itself when the parameter uses
    static strings, otherwise the index of the option, as QGIS expects it."""

    def map_schema(self, definition: QgsProcessingParameterEnum) -> Schema:
        """
        Raises:
            ValueError: If the parameter allows multiple options.
        """
        if definition.allowMultiple():
            raise ValueError(f"unsupported enum with multiple options: {definition.name()}")
        options = definition.options()
        if definition.usesStaticStrings():
            value_type, values = "string", options
        else:
            value_type, values = "integer", list(range(len(options)))
        return Schema(
            type=value_type,
            default=definition.defaultValue(),
            one_of=[
                Schema(const=value, title=option)
                for value, option in zip(values, options, strict=True)
            ],
        )


class LayerSchemaStrategy[D: QgsProcessingParameterDefinition | QgsProcessingOutputDefinition](
    SchemaStrategy[D], ABC
):
    """A layer value (`QslJobLayer`), marked with a `QslLayerMarker`. The marker is derived
    from the `Qgis.ProcessingSourceType` values the definition accepts."""

    layer_kind_by_source_type: dict[Qgis.ProcessingSourceType, QslLayerKind] = {
        Qgis.ProcessingSourceType.Vector: QslLayerKind.VECTOR,
        Qgis.ProcessingSourceType.VectorAnyGeometry: QslLayerKind.VECTOR,
        Qgis.ProcessingSourceType.VectorPoint: QslLayerKind.VECTOR,
        Qgis.ProcessingSourceType.VectorLine: QslLayerKind.VECTOR,
        Qgis.ProcessingSourceType.VectorPolygon: QslLayerKind.VECTOR,
        Qgis.ProcessingSourceType.Raster: QslLayerKind.RASTER,
    }
    # the geometry types a layer of the source type may have, see
    # `QgsProcessingUtils::canUseLayer` in QGIS `src/core/processing/qgsprocessingutils.cpp`.
    # The PyQGIS stubs lack `name` on the `Qgis.GeometryType` members although they are
    # python enums at runtime, hence the ignored attribute checks.
    geometry_types_by_source_type: dict[Qgis.ProcessingSourceType, list[str]] = {
        Qgis.ProcessingSourceType.Vector: [
            Qgis.GeometryType.Point.name,  # type: ignore[attr-defined]
            Qgis.GeometryType.Line.name,  # type: ignore[attr-defined]
            Qgis.GeometryType.Polygon.name,  # type: ignore[attr-defined]
            Qgis.GeometryType.Null.name,  # type: ignore[attr-defined]
        ],
        Qgis.ProcessingSourceType.VectorAnyGeometry: [
            Qgis.GeometryType.Point.name,  # type: ignore[attr-defined]
            Qgis.GeometryType.Line.name,  # type: ignore[attr-defined]
            Qgis.GeometryType.Polygon.name,  # type: ignore[attr-defined]
        ],
        Qgis.ProcessingSourceType.VectorPoint: [Qgis.GeometryType.Point.name],  # type: ignore[attr-defined]
        Qgis.ProcessingSourceType.VectorLine: [Qgis.GeometryType.Line.name],  # type: ignore[attr-defined]
        Qgis.ProcessingSourceType.VectorPolygon: [Qgis.GeometryType.Polygon.name],  # type: ignore[attr-defined]
        Qgis.ProcessingSourceType.Raster: [],
    }

    @abstractmethod
    def source_types(self, definition: D) -> list[int]:
        raise NotImplementedError

    def map_schema(self, definition: D) -> Schema:
        """
        Raises:
            ValueError: If a source type is not supported or the source types mix layer
                kinds.
        """
        # QGIS accepts any vector layer when no source type is set, see
        # `QgsProcessingUtils::canUseLayer`
        source_types = self.source_types(definition) or [Qgis.ProcessingSourceType.Vector]
        kinds = []
        geometry_types = []
        for source_type in map(Qgis.ProcessingSourceType, source_types):
            if source_type not in self.layer_kind_by_source_type:
                raise ValueError(f"unsupported ProcessingSourceType: {source_type}")
            if (kind := self.layer_kind_by_source_type[source_type]) not in kinds:
                kinds.append(kind)
            for geometry_type in self.geometry_types_by_source_type[source_type]:
                if geometry_type not in geometry_types:
                    geometry_types.append(geometry_type)
        if len(kinds) != 1:
            raise ValueError(f"mixed layer kinds: {kinds}")
        return Schema(
            type="string",
            format=QSL_LAYER_FORMAT,
            x_qsl_layer=QslLayerMarker(
                kind=kinds[0],
                geometry_types=geometry_types,
                source=type(definition).__name__,
            ),
        )


class FeatureSourceSchemaStrategy(
    LayerSchemaStrategy[QgsProcessingParameterFeatureSource | QgsProcessingParameterVectorLayer]
):
    def source_types(
        self, definition: QgsProcessingParameterFeatureSource | QgsProcessingParameterVectorLayer
    ) -> list[int]:
        return definition.dataTypes()


class RasterLayerSchemaStrategy(LayerSchemaStrategy[QgsProcessingParameterRasterLayer]):
    def source_types(self, definition: QgsProcessingParameterRasterLayer) -> list[int]:
        return [Qgis.ProcessingSourceType.Raster]


class MultipleLayersSchemaStrategy(LayerSchemaStrategy[QgsProcessingParameterMultipleLayers]):
    """Multiple layers are multiple values of the input, each one layer."""

    def source_types(self, definition: QgsProcessingParameterMultipleLayers) -> list[int]:
        return [definition.layerType()]

    def occurs(
        self, definition: QgsProcessingParameterMultipleLayers, optional: bool
    ) -> tuple[int, int | str]:
        if optional:
            return 0, "unbounded"
        return max(1, definition.minimumNumberInputs()), "unbounded"


class FileOutputSchemaStrategy(SchemaStrategy[QgsProcessingOutputDefinition]):
    """An output the worker writes to a file, offered in each of the given media types.
    The first one is the default."""

    def __init__(self, media_types: list[str]):
        self.media_types = media_types

    def map_schema(self, definition: QgsProcessingOutputDefinition) -> Schema:
        return Schema(
            one_of=[
                Schema(type="string", content_media_type=media_type)
                for media_type in self.media_types
            ]
        )


class ProcessDescriptionMapper:
    """Maps a QGIS processing algorithm onto its process description. The schema of each
    parameter and output is mapped by the strategy registered for its exact QGIS class,
    definitions without a strategy are not supported."""

    def __init__(self) -> None:
        self._parameter_strategies: dict[type, SchemaStrategy] = {
            QgsProcessingParameterFeatureSource: FeatureSourceSchemaStrategy(),
            QgsProcessingParameterVectorLayer: FeatureSourceSchemaStrategy(),
            QgsProcessingParameterRasterLayer: RasterLayerSchemaStrategy(),
            QgsProcessingParameterMultipleLayers: MultipleLayersSchemaStrategy(),
            QgsProcessingParameterNumber: NumberSchemaStrategy(),
            QgsProcessingParameterDistance: NumberSchemaStrategy(),
            QgsProcessingParameterBoolean: LiteralSchemaStrategy("boolean"),
            QgsProcessingParameterString: LiteralSchemaStrategy("string"),
            QgsProcessingParameterEnum: EnumSchemaStrategy(),
        }
        self._output_strategies: dict[type, SchemaStrategy] = {
            QgsProcessingOutputVectorLayer: FileOutputSchemaStrategy(
                [
                    "application/geo+json",
                    "application/geopackage+sqlite3",
                    "application/flatgeobuf",
                ]
            ),
            QgsProcessingOutputRasterLayer: FileOutputSchemaStrategy(
                ["image/tiff; application=geotiff"]
            ),
            QgsProcessingOutputHtml: FileOutputSchemaStrategy(["text/html"]),
            QgsProcessingOutputNumber: LiteralOutputSchemaStrategy("number"),
            QgsProcessingOutputString: LiteralOutputSchemaStrategy("string"),
            QgsProcessingOutputBoolean: LiteralOutputSchemaStrategy("boolean"),
        }

    def process_description(self, algorithm: QgsProcessingAlgorithm) -> ProcessDescription:
        """The description of the algorithm as process. Destination parameters are no
        inputs, the worker sets them."""
        return ProcessDescription(
            id=algorithm.id(),
            title=algorithm.displayName(),
            description=algorithm.shortHelpString() or None,
            inputs=[
                self.input_description(param)
                for param in algorithm.parameterDefinitions()
                if not param.isDestination()
            ],
            outputs=[self.output_description(output) for output in algorithm.outputDefinitions()],
        )

    def input_description(self, param: QgsProcessingParameterDefinition) -> InputDescription:
        """
        Raises:
            ValueError: If the parameter type is not supported.
        """
        strategy = self._parameter_strategies.get(type(param))
        if strategy is None:
            raise ValueError(f"unsupported parameter: {param.name()}, {type(param).__name__}")
        optional = bool(param.flags() & Qgis.ProcessingParameterFlag.Optional)
        min_occurs, max_occurs = strategy.occurs(param, optional)
        return InputDescription(
            id=param.name(),
            title=param.description(),
            description=param.help() or None,
            schema=strategy.map_schema(param),
            min_occurs=min_occurs,
            max_occurs=max_occurs,
        )

    def output_description(self, output: QgsProcessingOutputDefinition) -> OutputDescription:
        """
        Raises:
            ValueError: If the output type is not supported.
        """
        strategy = self._output_strategies.get(type(output))
        if strategy is None:
            raise ValueError(f"unsupported output: {output.name()}, {type(output).__name__}")
        return OutputDescription(
            id=output.name(),
            title=output.description(),
            schema=strategy.map_schema(output),
        )
