import logging
from typing import Any

from PyQt5.QtXml import QDomDocument
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeatureRequest,
    QgsMapLayer,
    QgsOgcUtils,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import NULL
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.common import Crs
from qgis_server_light.interface.job.common.input import QslJobLayer
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.feature.input import QslJobInfoFeature
from qgis_server_light.interface.job.feature.output import (
    Attribute,
    Feature,
    FeatureCollection,
    Geometry,
    QueryCollection,
)
from qgis_server_light.worker.qgis_type_serializer import register_converters_at_runtime
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class GetFeatureRunner(MapRunner):
    job_info_class = QslJobInfoFeature

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoFeature,
        layer_cache: dict | None = None,
        layer_style_cache: set | None = None,
    ) -> None:
        super().__init__(qgis, context, job_info, layer_cache)

    def _clean_attribute(self, attribute_value: Any, idx: int, layer: QgsVectorLayer):
        if attribute_value == NULL:
            return None
        return attribute_value

    def _clean_attributes(self, attributes, layer):
        return [self._clean_attribute(attr, idx, layer) for idx, attr in enumerate(attributes)]

    def _load_style(self, qgs_layer: QgsMapLayer, job_layer_definition: QslJobLayer):
        logging.info(" ✓ Omit style loading on WFS layer operation.")

    @staticmethod
    def _destination_crs(crs: Crs | None) -> QgsCoordinateReferenceSystem | None:
        if crs is None:
            return None
        # the identifiers are equivalent, the first one present is taken
        identifier = crs.ogc_urn or crs.ogc_uri or crs.auth_id
        destination_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(identifier or "")
        if not destination_crs.isValid():
            raise RuntimeError(f"Crs `{crs}` of the query is not valid")
        return destination_crs

    def run(self):
        query_collection = QueryCollection()
        numbers_matched = 0
        for query in self.job_info.job.queries:
            # we need to reset this because we want always only the layers related to
            # the current query
            self.map_layers = []
            wfs_filter = query.filter
            destination_crs = self._destination_crs(query.crs)
            for job_layer_definition in query.layers:
                self._provide_layer(job_layer_definition)

            for job_layer_definition, layer in zip(query.layers, self.map_layers, strict=True):
                feature_collection = FeatureCollection(job_layer_definition.id)
                query_collection.feature_collections.append(feature_collection)
                if isinstance(layer, QgsVectorLayer):
                    if wfs_filter is not None and wfs_filter.definition is not None:
                        # TODO: This is potentially bad: We always get all features from
                        #  datasource. However, QGIS
                        #   does not seem to support sliding window feature filter out of the box...
                        logging.info(" QslJobLayer is filtered by:")
                        logging.info(f" {wfs_filter.definition}")
                        filter_doc = QDomDocument()
                        filter_doc.setContent(wfs_filter.definition)
                        # This is not correct in the WFS 2.0 way. We apply a filter
                        # to a job_layer_definition. But WFS 2.0
                        # allows filters on multiple layers.
                        # The layer is used to type literals by the field types.
                        expression = QgsOgcUtils.expressionFromOgcFilter(
                            filter_doc.documentElement(),
                            QgsOgcUtils.FilterVersion.FILTER_FES_2_0,
                            layer,
                        )
                        logging.info(
                            f" This was transformed to the QGIS expression "
                            f"(valid: {expression.isValid()})"
                        )
                        logging.info(f" '{expression.dump()}'")
                        feature_request = QgsFeatureRequest(expression)
                        # geom_from_gml takes the layer out of the expression context to
                        # transform geometry literals with srsName into the layer crs
                        feature_request.setExpressionContext(
                            QgsExpressionContext(
                                QgsExpressionContextUtils.globalProjectLayerScopes(layer)
                            )
                        )
                    else:
                        feature_request = QgsFeatureRequest()
                    if destination_crs is not None:
                        # filter expressions are still evaluated in the layer crs, only
                        # the returned geometries are transformed
                        feature_request.setDestinationCrs(destination_crs, layer.transformContext())
                    layer_features = list(layer.getFeatures(feature_request))
                    numbers_matched += len(layer_features)
                    logging.info(f" Found {len(layer_features)} features")
                    if self.job_info.job.count:
                        layer_features = layer_features[
                            self.job_info.job.start_index : self.job_info.job.start_index
                            + self.job_info.job.count
                        ]
                    for layer_feature in layer_features:
                        property_list = zip(
                            layer_feature.fields().names(),
                            self._clean_attributes(layer_feature.attributes(), layer),
                            strict=True,
                        )
                        feature = Feature(
                            geometry=Geometry(
                                value=bytes(layer_feature.geometry().asWkb()),
                            )
                        )
                        feature_collection.features.append(feature)
                        for name, value in property_list:
                            feature.attributes.append(Attribute(name=name, value=value))
                else:
                    raise RuntimeError(
                        f"QslJobLayer type `{layer.type().name}` of layer "
                        f"`{layer.shortName()}` not supported by GetFeatureInfo"
                    )
        if numbers_matched > 0:
            query_collection.numbers_matched = numbers_matched
        with register_converters_at_runtime():
            data = JsonSerializer().render(query_collection).encode()
            return JobResult(
                id=self.job_info.id,
                data=data,
                content_type="application/qgis-server-light.interface.qgis.QueryCollection",
            )
