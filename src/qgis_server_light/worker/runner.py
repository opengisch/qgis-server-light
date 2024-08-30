import json
import logging
import os
from base64 import urlsafe_b64decode
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, OrderedDict

from PyQt5.QtCore import QEventLoop, QSize, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtXml import QDomDocument
from qgis.core import (
    NULL,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeatureRequest,
    QgsMapLayer,
    QgsMapLayerType,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsPointXY,
    QgsRasterLayer,
    QgsRectangle,
    QgsRenderContext,
    QgsVectorLayer,
)
from qgis_server_light.interface.job import (
    JobResult,
    QslGetFeatureInfoJob,
    QslLegendJob,
    QslGetMapJob,
)
from qgis_server_light.interface.qgis import Vector, Raster
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
        job: QslGetMapJob | QslGetFeatureInfoJob | QslLegendJob,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        self.qgis = qgis
        self.context = context
        self.job = job
        self.map_layers = list()
        self.layer_cache = layer_cache

    def _get_map_settings(self, layers: List[QgsMapLayer]) -> QgsMapSettings:
        """Produces a QgsMapSettings object from a set of layers"""
        settings = QgsMapSettings()
        settings.setOutputSize(
            QSize(
                int(self.job.service_params.WIDTH),
                int(self.job.service_params.HEIGHT)
            )
        )
        settings.setOutputDpi(self.job.service_params.dpi)
        minx, miny, maxx,  maxy = self.job.service_params.bbox
        bbox = QgsRectangle(float(minx), float(miny), float(maxx), float(maxy))
        settings.setExtent(bbox)
        settings.setLayers(layers)
        settings.setBackgroundColor(QColor(Qt.transparent))
        crs = self.job.service_params.CRS
        destinationCrs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(crs)
        settings.setDestinationCrs(destinationCrs)
        return settings

    def _init_layers(self, layer: Vector | Raster):
        """Initializes the map_layers list with all the specified layer_names, looking up style and other
        information in layer_registry
        Returns:
            None
        Parameters:
            layer_name: the layer or group to initialize. In case of a group, will recursively follow.
        """

        if isinstance(layer, Vector):
            self.map_layers.append(
                self._prepare_vector_layer(layer)
            )
        elif isinstance(layer, Raster):
            self.map_layers.append(
                self._prepare_raster_layer(layer)
            )
        else:
            raise KeyError(f"Type not implemented: {layer}")

    def _prepare_vector_layer(self, layer: Vector) -> QgsVectorLayer:
        """Initializes a vector layer"""
        if layer.source.ogr is not None:
            if layer.source.ogr.remote:
                layer_source_path = layer.path
            else:
                layer_source_path = os.path.join(
                    self.context.base_path, layer.path
                )
        elif (layer.source.postgres or layer.source.wfs) is not None:
            layer_source_path = layer.path
        else:
            raise KeyError(f"Driver not implemented: {layer.driver}")

        # TODO: make sure cached layers reload the style if changed
        if self.layer_cache is not None and layer.name in self.layer_cache:
            logging.debug(f"Using cached layer {layer.name}")
            qgs_layer = self.layer_cache[layer.name]
        else:
            logging.debug(f"Load layer {layer_source_path}")
            options = QgsVectorLayer.LayerOptions(
                loadDefaultStyle=False, readExtentFromXml=False
            )
            options.skipCrValidation = True
            options.forceReadOnly = True
            qgs_layer = QgsVectorLayer(
                layer_source_path, layer.name, layer.driver, options
            )

            if not qgs_layer.isValid():
                raise RuntimeError(
                    f"Layer {layer.name} is not valid.\n    Path: {layer_source_path}"
                )
            else:
                logging.info(f" ✓ Layer: {layer.name}")
                if self.layer_cache is not None:
                    self.layer_cache[layer.name] = qgs_layer
            if layer.style:
                style_doc = QDomDocument()
                style_doc.setContent(
                    urlsafe_b64decode(
                        layer.style
                    )
                )
                style_loaded = qgs_layer.importNamedStyle(style_doc)
                logging.info(f"Style loaded: {style_loaded}")
        return qgs_layer

    def _prepare_raster_layer(self, layer: Raster) -> QgsRasterLayer:
        """Initializes a raster layer"""
        if layer.source.gdal is not None:
            if layer.source.gdal.remote:
                layer_source_path = layer.path
            else:
                layer_source_path = os.path.join(
                    self.context.base_path, layer.path
                )
        elif layer.source.wms is not None:
            layer_source_path = layer.path
        else:
            raise KeyError(f"Driver not implemented: {layer.driver}")
        # TODO: make sure cached layers reload the style if changed
        if self.layer_cache is not None and layer.name in self.layer_cache:
            logging.debug(f"Using cached layer {layer.name}")
            qgs_layer = self.layer_cache[layer.name]
        else:
            qgs_layer = QgsRasterLayer(layer_source_path, layer.name, layer.driver)
            if not qgs_layer.isValid():
                raise RuntimeError(f"Layer {layer.name} is not valid")
            else:
                logging.info(f" ✓ Layer: {layer.name}")
                if self.layer_cache is not None:
                    self.layer_cache[layer.name] = qgs_layer
            if layer.style:
                style_doc = QDomDocument()
                style_doc.setContent(
                    urlsafe_b64decode(
                        layer.style
                    )
                )
                style_loaded = qgs_layer.importNamedStyle(style_doc)
                logging.info(f"Style loaded: {style_loaded}")
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
            layer_cache: Optional[Dict] = None
    ) -> None:
        super().__init__(qgis, context, job, layer_cache)

    def run(self):
        """Run this runner.
        Returns:
            A JobResult with the content_type and image_data (bytes) of the rendered image.
        """
        for layer_name in self.job.service_params.layers:
            self._init_layers(self.job.get_layer_by_name(layer_name))
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
            layer_cache: Optional[Dict] = None
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
        for layer in self.job.query_layers:
            self._init_layers(layer_registry, layer)
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
