import json
import logging
import os
import uuid
import zlib
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import OrderedDict

from PyQt5.QtCore import QEventLoop
from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtXml import QDomDocument
from qgis._core import QgsExpressionContext
from qgis._core import QgsExpressionContextScope
from qgis._core import QgsOgcUtils
from qgis._core import QgsVectorTileLayer
from qgis.core import NULL
from qgis.core import QgsApplication
from qgis.core import QgsCoordinateReferenceSystem
from qgis.core import QgsFeatureRequest
from qgis.core import QgsMapLayer
from qgis.core import QgsMapLayerType
from qgis.core import QgsMapRendererParallelJob
from qgis.core import QgsMapSettings
from qgis.core import QgsPointXY
from qgis.core import QgsRasterLayer
from qgis.core import QgsRectangle
from qgis.core import QgsRenderContext
from qgis.core import QgsVectorLayer
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.job import JobResult
from qgis_server_light.interface.job import QslGetFeatureInfoJob
from qgis_server_light.interface.job import QslGetFeatureJob
from qgis_server_light.interface.job import QslGetMapJob
from qgis_server_light.interface.job import QslLegendJob
from qgis_server_light.interface.qgis import Attribute
from qgis_server_light.interface.qgis import Custom
from qgis_server_light.interface.qgis import DataSet
from qgis_server_light.interface.qgis import Feature
from qgis_server_light.interface.qgis import FeatureCollection
from qgis_server_light.interface.qgis import QueryCollection
from qgis_server_light.interface.qgis import Raster
from qgis_server_light.interface.qgis import Vector
from qgis_server_light.worker.image_utils import _encode_image


@dataclass
class RunnerContext:
    base_path: str | Path


class MapRunner:
    """Base class for any runner that interacts with a map.
    Not runnable by itself.
    """

    map_layers: List[QgsMapLayer]

    def __init__(
        self,
        qgis: QgsApplication,
        context: RunnerContext,
        job: QslGetMapJob | QslGetFeatureInfoJob | QslLegendJob | QslGetFeatureJob,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        self.qgis = qgis
        self.context = context
        self.job = job
        self.map_layers = list()
        self.layer_cache = layer_cache

    def _get_map_settings(self, layers: List[QgsMapLayer]) -> QgsMapSettings:
        """Produces a QgsMapSettings object from a set of layers"""
        expression_context_scope = QgsExpressionContextScope()
        expression_context_scope.setVariable("map_id", str(uuid.uuid4()))
        expression_context = QgsExpressionContext()
        expression_context.appendScope(expression_context_scope)
        settings = QgsMapSettings()
        settings.setExpressionContext(expression_context)

        def preprocessor(path):
            print(path)
            return path

        settings.pathResolver().setPathPreprocessor(preprocessor)
        settings.setOutputSize(
            QSize(
                int(self.job.service_params.WIDTH), int(self.job.service_params.HEIGHT)
            )
        )
        if self.job.service_params.dpi:
            settings.setOutputDpi(self.job.service_params.dpi)
        minx, miny, maxx, maxy = self.job.service_params.bbox
        bbox = QgsRectangle(float(minx), float(miny), float(maxx), float(maxy))
        settings.setExtent(bbox)
        settings.setExtentBuffer(self.job.extent_buffer)
        settings.setLayers(layers)
        settings.setBackgroundColor(QColor(Qt.transparent))
        crs = self.job.service_params.CRS
        destinationCrs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(crs)
        settings.setDestinationCrs(destinationCrs)
        return settings

    def _load_style(
        self, requested_style_name: str, qgs_layer: QgsMapLayer, dataset: DataSet
    ):
        logging.info(f"Preparing layer Style: {requested_style_name}")
        style_doc = QDomDocument()
        style_doc.setContent(
            zlib.decompress(
                urlsafe_b64decode(
                    dataset.get_style_by_name(requested_style_name).definition
                )
            )
        )
        style_loaded = qgs_layer.importNamedStyle(style_doc)
        qgs_layer.styleManager().setCurrentStyle(requested_style_name)
        logging.info(f" ✓ Style loaded: {style_loaded}")

    def _init_layers(self, dataset: Vector | Raster | Custom, style_name: str):
        """Initializes the map_layers list with all the specified layer_names, looking up style and other
        information in layer_registry
        Returns:
            None
        Parameters:
            layer_name: the layer or group to initialize. In case of a group, will recursively follow.
            style_name: The name of the style which is requested fo rendering.
        """

        if isinstance(dataset, Vector):
            qgs_layer = self._prepare_vector_layer(dataset)
        elif isinstance(dataset, Raster):
            qgs_layer = self._prepare_raster_layer(dataset)
        elif isinstance(dataset, Custom):
            qgs_layer = self._prepare_custom_layer(dataset)
        else:
            raise KeyError(f"Type not implemented: {dataset}")
        # applying the style to the layer
        self._load_style(style_name, qgs_layer, dataset)
        self.map_layers.append(qgs_layer)

    def _prepare_vector_layer(self, dataset: Vector) -> QgsVectorLayer:
        """Initializes a vector layer"""
        if dataset.source.ogr is not None:
            if dataset.source.ogr.remote:
                layer_source_path = dataset.path
            else:
                layer_source_path = os.path.join(self.context.base_path, dataset.path)
        elif (dataset.source.postgres or dataset.source.wfs) is not None:
            layer_source_path = dataset.path
        else:
            raise KeyError(f"Driver not implemented: {dataset.driver}")

        logging.debug(f"Loading layer source: {layer_source_path}")
        # TODO: make sure cached layers reload the style if changed
        if self.layer_cache is not None and dataset.name in self.layer_cache:
            logging.debug(f"Using cached layer {dataset.name}")
            qgs_layer = self.layer_cache[dataset.name]
        else:
            logging.debug(f"Load layer {layer_source_path}")
            options = QgsVectorLayer.LayerOptions(
                loadDefaultStyle=False, readExtentFromXml=False
            )
            options.skipCrValidation = True
            options.forceReadOnly = True
            qgs_layer = QgsVectorLayer(
                layer_source_path, dataset.name, dataset.driver, options
            )

            if not qgs_layer.isValid():
                raise RuntimeError(
                    f"Layer {dataset.name} is not valid.\n    Path: {layer_source_path}"
                )
            else:
                logging.info(f" ✓ Layer: {dataset.name}")
                if self.layer_cache is not None:
                    self.layer_cache[dataset.name] = qgs_layer
        return qgs_layer

    def _prepare_custom_layer(self, dataset: Custom) -> QgsVectorTileLayer:
        """Initializes a raster layer"""
        if dataset.source.vector_tile is not None:
            if dataset.source.vector_tile.remote:
                layer_source_path = dataset.path
                logging.debug(f"Loading layer source: {layer_source_path}")
            else:
                raise NotImplementedError(
                    "Currently only remote VectorTiles are supported"
                )
        else:
            raise KeyError(f"Driver not implemented: {dataset.driver}")
        # TODO: make sure cached layers reload the style if changed
        if self.layer_cache is not None and dataset.name in self.layer_cache:
            logging.debug(f"Using cached layer {dataset.name}")
            qgs_layer = self.layer_cache[dataset.name]
        else:
            qgs_layer = QgsVectorTileLayer(layer_source_path, dataset.name)
            if not qgs_layer.isValid():
                raise RuntimeError(f"Layer {dataset.name} is not valid")
            else:
                logging.info(f" ✓ Layer: {dataset.name}")
                if self.layer_cache is not None:
                    self.layer_cache[dataset.name] = qgs_layer
        return qgs_layer

    def _prepare_raster_layer(self, dataset: Raster) -> QgsRasterLayer:
        """Initializes a raster layer"""
        if dataset.source.gdal is not None:
            if dataset.source.gdal.remote:
                layer_source_path = dataset.path
            else:
                layer_source_path = os.path.join(self.context.base_path, dataset.path)
        elif dataset.source.wms is not None:
            layer_source_path = dataset.path
        else:
            raise KeyError(f"Driver not implemented: {dataset.driver}")
        logging.debug(f"Loading layer source: {layer_source_path}")
        # TODO: make sure cached layers reload the style if changed
        if self.layer_cache is not None and dataset.name in self.layer_cache:
            logging.debug(f"Using cached layer {dataset.name}")
            qgs_layer = self.layer_cache[dataset.name]
        else:
            qgs_layer = QgsRasterLayer(layer_source_path, dataset.name, dataset.driver)
            if not qgs_layer.isValid():
                raise RuntimeError(f"Layer {dataset.name} is not valid")
            else:
                logging.info(f" ✓ Layer: {dataset.name}")
                if self.layer_cache is not None:
                    self.layer_cache[dataset.name] = qgs_layer
        return qgs_layer

    def run(self):
        # This is an abstract base class which is not runnable itself
        raise NotImplementedError()


class RenderRunner(MapRunner):
    """Responsible for rendering a QslRenderJob to an image."""

    def __init__(
        self,
        qgis: QgsApplication,
        context: RunnerContext,
        job: QslGetMapJob,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        super().__init__(qgis, context, job, layer_cache)

    def run(self):
        """Run this runner.
        Returns:
            A JobResult with the content_type and image_data (bytes) of the rendered image.
        """
        for index, layer_name in enumerate(self.job.service_params.layers):
            # list of styles passed to QSL has to be always the same order and length as layers
            style_name = self.job.service_params.styles[index]
            self._init_layers(self.job.get_dataset_by_name(layer_name), style_name)
        map_settings = self._get_map_settings(self.map_layers)
        renderer = QgsMapRendererParallelJob(map_settings)
        event_loop = QEventLoop(self.qgis)
        renderer.finished.connect(event_loop.quit)
        renderer.start()
        event_loop.exec_()
        img = renderer.renderedImage()
        img.setDotsPerMeterX(int(map_settings.outputDpi() * 39.37))
        img.setDotsPerMeterY(int(map_settings.outputDpi() * 39.37))
        image_data, content_type = _encode_image(img, self.job.service_params.FORMAT)
        return JobResult(content_type, image_data)


class GetFeatureInfoRunner(MapRunner):
    def __init__(
        self,
        qgis: QgsApplication,
        context: RunnerContext,
        job: QslGetFeatureInfoJob,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        super().__init__(qgis, context, job, layer_cache)

    def _clean_attribute(self, attribute, idx, layer):
        if attribute == NULL:
            return None
        setup = layer.editorWidgetSetup(idx)
        fieldFormatter = QgsApplication.fieldFormatterRegistry().fieldFormatter(
            setup.type()
        )
        return fieldFormatter.representValue(
            layer, idx, setup.config(), None, attribute
        )

    def _clean_attributes(self, attributes, layer):
        return [
            self._clean_attribute(attr, idx, layer)
            for idx, attr in enumerate(attributes)
        ]

    def run(self):
        layer_registry = self.context.theme.config.get("layers")
        for dataset in self.job.query_layers:
            self._init_layers(layer_registry, dataset)
        map_settings = self._get_map_settings(self.map_layers)
        # Estimate queryable bbox (2mm)
        map_to_pixel = map_settings.mapToPixel()
        map_point = map_to_pixel.toMapCoordinates(self.job.x, self.job.y)
        # Create identifiable bbox in map coordinates, ±2mm
        tolerance = 0.002 * 39.37 * map_settings.outputDpi()
        tl = QgsPointXY(map_point.x() - tolerance, map_point.y() - tolerance)
        br = QgsPointXY(map_point.x() + tolerance, map_point.y() + tolerance)
        rect = QgsRectangle(tl, br)
        render_context = QgsRenderContext.fromMapSettings(map_settings)

        features = list()
        for layer in self.map_layers:
            renderer = layer.renderer().clone() if layer.renderer() else None
            if renderer:
                renderer.startRender(render_context, layer.fields())

            if layer.type() == QgsMapLayerType.VectorLayer:
                layer_rect = map_settings.mapToLayerCoordinates(layer, rect)
                request = (
                    QgsFeatureRequest()
                    .setFilterRect(layer_rect)
                    .setFlags(QgsFeatureRequest.ExactIntersect)
                )
                for feature in layer.getFeatures(request):
                    if renderer.willRenderFeature(feature, render_context):
                        properties = OrderedDict(
                            zip(
                                feature.fields().names(),
                                self._clean_attributes(feature.attributes(), layer),
                            )
                        )
                        features.append({"type": "Feature", "properties": properties})
            else:
                raise RuntimeError(
                    f"Layer type `{layer.type().name}` of layer `{layer.shortName()}` not supported by GetFeatureInfo"
                )
            if renderer:
                renderer.stopRender(render_context)

        featurecollection = {"features": features, "type": "FeatureCollection"}
        return JobResult(
            data=json.dumps(featurecollection).encode("utf-8"),
            content_type="application/json",
        )


class GetLegendRunner(MapRunner):
    def __init__(self, qgis, context: RunnerContext, job: QslLegendJob) -> None:
        super().__init__(qgis, context, job)
        self.job = job

    def run(self):
        # TODO Implement ....
        raise NotImplementedError()


class GetFeatureRunner(MapRunner):
    def __init__(
        self,
        qgis: QgsApplication,
        context: RunnerContext,
        job: QslGetFeatureJob,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        super().__init__(qgis, context, job, layer_cache)

    def _clean_attribute(self, attribute, idx, layer):
        if attribute == NULL:
            return None
        setup = layer.editorWidgetSetup(idx)
        fieldFormatter = QgsApplication.fieldFormatterRegistry().fieldFormatter(
            setup.type()
        )
        return fieldFormatter.representValue(
            layer, idx, setup.config(), None, attribute
        )

    def _clean_attributes(self, attributes, layer):
        return [
            self._clean_attribute(attr, idx, layer)
            for idx, attr in enumerate(attributes)
        ]

    def _load_style(
        self, requested_style_name: str, qgs_layer: QgsMapLayer, dataset: DataSet
    ):
        logging.info(f" ✓ Omit style loading on WFS layer operation.")

    def run(self):
        query_collection = QueryCollection()
        numbers_matched = 0
        for query in self.job.queries:
            # we need to reset this because we want always only the layers related to the current query
            self.map_layers = []
            wfs_filter_definition = query.filter
            for dataset in query.datasets:
                self._init_layers(dataset, "")

            for layer in self.map_layers:
                feature_collection = FeatureCollection(layer.name())
                query_collection.feature_collections.append(feature_collection)
                if isinstance(layer, QgsVectorLayer):
                    if wfs_filter_definition:
                        # TODO: This is potentially bad: We always get all features from datasource. However, QGIS
                        #   does not seem to support sliding window feature filter out of the box...
                        logging.info(" Layer is filtered by:")
                        logging.info(wfs_filter_definition)
                        filter_doc = QDomDocument()
                        filter_doc.setContent(wfs_filter_definition)
                        # This is not correct in the WFS 2.0 way. We apply a filter to a layer. But WFS 2.0
                        # allows filters on multiple layers.
                        expression = QgsOgcUtils.expressionFromOgcFilter(
                            filter_doc.documentElement(),
                            QgsOgcUtils.FilterVersion.FILTER_FES_2_0,
                            layer,
                        )
                        feature_request = QgsFeatureRequest(expression)
                    else:
                        feature_request = QgsFeatureRequest()
                    layer_features = list(layer.getFeatures(feature_request))
                    numbers_matched += len(layer_features)
                    if self.job.count:
                        layer_features = layer_features[
                            self.job.start_index : self.job.start_index + self.job.count
                        ]
                    for layer_feature in layer_features:
                        property_list = zip(
                            layer_feature.fields().names(),
                            self._clean_attributes(layer_feature.attributes(), layer),
                        )
                        feature = Feature(
                            geometry=Attribute(
                                name="geometry",
                                value=bytearray(layer_feature.geometry().asWkb()),
                            )
                        )
                        feature_collection.features.append(feature)
                        for name, value in property_list:
                            feature.attributes.append(Attribute(name=name, value=value))
                else:
                    raise RuntimeError(
                        f"Layer type `{layer.type().name}` of layer `{layer.shortName()}` not supported by GetFeatureInfo"
                    )
        if numbers_matched > 0:
            query_collection.numbers_matched = numbers_matched
        data = JsonSerializer().render(query_collection).encode()
        return JobResult(
            data=data,
            content_type="application/qgis-server-light.interface.qgis.QueryCollection",
        )
