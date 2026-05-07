import json
import logging
import os
import uuid
import zlib
from abc import ABC
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Type

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtXml import QDomDocument
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsExpressionContext,
    QgsExpressionContextScope,
    QgsMapLayer,
    QgsMapSettings,
    QgsOgcUtils,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
    QgsVectorTileLayer,
)
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.job.common.input import (
    OgcFilter110,
    QslJobInfoParameter,
    QslJobLayer,
)


@dataclass
class JobContext:
    base_path: str | Path


class Runner(ABC):
    job_info_class: Type[QslJobInfoParameter]

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoParameter,
        layer_cache: Optional[Dict],
    ):
        # This is an abstract base class which is not runnable itself
        raise NotImplementedError()

    def run(self):
        # This is an abstract base class which is not runnable itself
        raise NotImplementedError()

    @classmethod
    def deserialize_job_info(cls, job_info: bytes):
        return JsonParser().from_bytes(job_info, cls.job_info_class)


class MapRunner(Runner):
    """Base class for any runner that interacts with a map.
    Not runnable by itself.
    """

    map_layers: List[QgsMapLayer]
    vector_layer_drivers = [
        "ogr",
        "postgres",
        "spatialite",
        "mssql",
        "oracle",
        "wfs",
        "delimitedtext",
        "gpx",
        "arcgisfeatureserver",
    ]
    raster_layer_drivers = [
        "gdal",
        "wms",
        "xyz",
        "arcgismapserver",
        "wcs",
    ]
    custom_layer_drivers = ["xyzvectortiles", "mbtilesvectortiles"]
    default_style_name = "default"

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoParameter,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        self.qgis = qgis
        self.context = context
        self.job_info = job_info
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
            return path

        settings.pathResolver().setPathPreprocessor(preprocessor)
        settings.setOutputSize(
            QSize(int(self.job_info.job.width), int(self.job_info.job.height))
        )
        if self.job_info.job.dpi:
            settings.setOutputDpi(self.job_info.job.dpi)

        crs = self.job_info.job.crs
        destination_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(crs)
        minx, miny, maxx, maxy = self.job_info.job.bbox.to_2d_list()
        bbox = QgsRectangle(float(minx), float(miny), float(maxx), float(maxy))
        if (
            destination_crs.hasAxisInverted()
        ):  # lat-lon, instead of lon-lat e.g. epsg:4326
            bbox.invert()
        settings.setExtent(bbox)
        settings.setLayers(layers)
        settings.setBackgroundColor(QColor(Qt.transparent))

        settings.setDestinationCrs(destination_crs)
        return settings

    def _load_style(self, qgs_layer: QgsMapLayer, job_layer_definition: QslJobLayer):
        logging.info(
            f"Preparing job_layer_definition Style: {job_layer_definition.style.name}"
        )
        style_doc = QDomDocument()
        style_xml = zlib.decompress(
            urlsafe_b64decode(job_layer_definition.style.definition)
        )
        style_doc.setContent(style_xml)
        success, _ = qgs_layer.importNamedStyle(style_doc)

        logging.info(f" ✓ Style loaded: {success}")

    def get_cache_name(self, job_layer_definition: QslJobLayer) -> str:
        """Central method to decide which name is used in the cache to
        identify a layer.
        """
        return job_layer_definition.id

    def _decide_drivers(self, job_layer_definition: QslJobLayer) -> QgsMapLayer:
        """Decides which type of layer we are dealing with and delegates initialization
        to the right method.

        Args:
            job_layer_definition: The job_layer_definition containing all
                information to initialize a QgsMapLayer.
        Returns:
            The newly created layer.
        Raises:
            LookupError: When the driver is not in the expected ranges.
        """
        if job_layer_definition.driver in self.vector_layer_drivers:
            qgs_layer = self._prepare_vector_layer(job_layer_definition)
        elif job_layer_definition.driver in self.raster_layer_drivers:
            qgs_layer = self._prepare_raster_layer(job_layer_definition)
        elif job_layer_definition.driver in self.custom_layer_drivers:
            qgs_layer = self._prepare_custom_layer(job_layer_definition)
        else:
            raise LookupError(f"Type not implemented: {job_layer_definition}")
        return qgs_layer

    def _handle_layer_cache(self, job_layer_definition: QslJobLayer) -> QgsMapLayer:
        """Checks if layer can be fetched directly from the cache or initiates the
        creation of a new layer otherwise.

        Args:
            job_layer_definition: The job_layer_definition containing all
                information to initialize a QgsMapLayer.
        Returns:
            The layer (from cache or newly created).
        """
        cache_name = self.get_cache_name(job_layer_definition)
        if self.layer_cache is not None and cache_name in self.layer_cache:
            logging.debug(
                f"Using cached job_layer_definition {job_layer_definition.name} (identifier: {cache_name})"
            )
            qgs_layer = self.layer_cache[cache_name]
        else:
            qgs_layer = self._decide_drivers(job_layer_definition)
            if qgs_layer.isValid():
                logging.debug(
                    f"Newly initialized layer {job_layer_definition.name} is valid: {qgs_layer.isValid()}"
                )
                if self.layer_cache is not None:
                    self.layer_cache[cache_name] = qgs_layer
            else:
                logging.error(qgs_layer.error().message())
                logging.error(qgs_layer.dataProvider().error().message())
                raise RuntimeError(
                    f"Newly initialized layer {job_layer_definition.name} is not valid. JobLayerDefinition: {job_layer_definition}"
                )
        return qgs_layer

    def _provide_layer(self, job_layer_definition: QslJobLayer) -> None:
        """Fetches the QGIS layer relevant for the requested job layer.

        Args:
            job_layer_definition: The job_layer_definition containing all
                information to initialize a QgsMapLayer.
        Returns:
            None
        """
        qgs_layer = self._handle_layer_cache(job_layer_definition)
        # applying the style to the job_layer_definition
        self._load_style(qgs_layer, job_layer_definition)
        self.map_layers.append(qgs_layer)

    def _handle_datasource_definition(self, job_layer_definition: QslJobLayer) -> dict:
        layer_source = json.loads(job_layer_definition.source)
        if not job_layer_definition.remote:
            # we make the relative path an absolute one with the configured base path
            layer_source["path"] = os.path.join(
                self.context.base_path,
                job_layer_definition.folder_name,
                layer_source["path"],
            )
        return layer_source

    def _decoded_layer_source_to_connection_string(
        self, driver: str, layer_source: dict
    ) -> str:
        return QgsProviderRegistry.instance().encodeUri(driver, layer_source)

    def _prepare_vector_layer(
        self, job_layer_definition: QslJobLayer
    ) -> QgsVectorLayer:
        """
        Initializes a QgsVectorLayer from a job_layer_definition.
        Args:
            job_layer_definition: The job_layer_definition definition as
                received from the runner.

        Returns:
            The QgsVectorLayer instance in case initialization went correctly.
        Raises:
            RuntimeError: In case the initialized job_layer_definition was not
                valid from QGIS point of view (mostly related to not available
                data sources).
        """

        layer_source = self._handle_datasource_definition(job_layer_definition)
        layer_source_path = self._decoded_layer_source_to_connection_string(
            job_layer_definition.driver, layer_source
        )

        # removed loadDefaultStyle=False because it seems to have no effect anymore
        options = QgsVectorLayer.LayerOptions(readExtentFromXml=False)
        options.skipCrValidation = True
        options.forceReadOnly = True

        qgs_layer = QgsVectorLayer(
            layer_source_path,
            job_layer_definition.name,
            job_layer_definition.driver,
            options,
        )
        if job_layer_definition.filter:
            if isinstance(job_layer_definition.filter, OgcFilter110):
                # TODO: This is potentially bad: We always get all features from datasource. However, QGIS
                #   does not seem to support sliding window feature filter out of the box...
                logging.info(" QslJobLayer is filtered by:")
                logging.info(job_layer_definition.filter.definition)
                filter_doc = QDomDocument()
                filter_doc.setContent(job_layer_definition.filter.definition)
                filter_expression = QgsOgcUtils.expressionFromOgcFilter(
                    filter_doc.documentElement(),
                    QgsOgcUtils.FilterVersion.FILTER_OGC_1_1,
                    qgs_layer,
                )
                existing_expression = qgs_layer.subsetString()
                if existing_expression:
                    # Combining with AND the originally defined expression always takes precedence
                    expression = f"({existing_expression}) AND ({filter_expression.expression()})"
                else:
                    expression = filter_expression.expression()
                qgs_layer.setSubsetString(expression)
        return qgs_layer

    def _prepare_custom_layer(
        self, job_layer_definition: QslJobLayer
    ) -> QgsVectorTileLayer:
        """Initializes a custom job_layer_definition"""
        layer_source = self._handle_datasource_definition(job_layer_definition)
        layer_source_path = self._decoded_layer_source_to_connection_string(
            job_layer_definition.driver, layer_source
        )
        qgs_layer = QgsVectorTileLayer(layer_source_path, job_layer_definition.name)
        return qgs_layer

    def _prepare_raster_layer(
        self, job_layer_definition: QslJobLayer
    ) -> QgsRasterLayer:
        """Initializes a raster job_layer_definition"""
        layer_source = self._handle_datasource_definition(job_layer_definition)
        layer_source_path = self._decoded_layer_source_to_connection_string(
            job_layer_definition.driver, layer_source
        )
        qgs_layer = QgsRasterLayer(
            layer_source_path,
            job_layer_definition.name,
            job_layer_definition.driver,
        )
        return qgs_layer
