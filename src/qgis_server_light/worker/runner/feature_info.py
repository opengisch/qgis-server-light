import json
from typing import Dict, Optional, OrderedDict

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsFeatureRequest,
    QgsMapLayerType,
    QgsPointXY,
    QgsRectangle,
    QgsRenderContext,
)
from qgis.PyQt.QtCore import NULL

from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.feature_info.input import QslJobInfoFeatureInfo
from qgis_server_light.interface.worker.info import FeatureInfo
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class GetFeatureInfoRunner(MapRunner):
    job_info_class = QslJobInfoFeatureInfo

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoFeatureInfo,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        super().__init__(qgis, context, job_info, layer_cache)

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
        for job_layer_definition in self.job_info.job.layers:
            self._provide_layer(job_layer_definition)
        map_settings = self._get_map_settings(self.map_layers)
        # Estimate queryable bbox (2mm)
        map_to_pixel = map_settings.mapToPixel()
        map_point = map_to_pixel.toMapCoordinates(
            self.job_info.job.x, self.job_info.job.y
        )
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
            id=self.job_info.id,
            data=json.dumps(featurecollection).encode("utf-8"),
            content_type="application/json",
        )

    @classmethod
    def info(cls, qgis: Qgis) -> FeatureInfo:
        return FeatureInfo()
