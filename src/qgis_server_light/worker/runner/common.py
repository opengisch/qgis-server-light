import json
import logging
import os
import uuid
import zlib
from abc import ABC
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from pathlib import Path

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
    job_info_class: type[QslJobInfoParameter]

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoParameter,
        layer_cache: dict | None,
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

    map_layers: list[QgsMapLayer]
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
        layer_cache: dict | None = None,
    ) -> None:
        self.qgis = qgis
        self.context = context
        self.job_info = job_info
        self.map_layers = list()
        self.layer_cache = layer_cache
        self._custom_prop_original_filter = "qsl.original_filter"
        self._custom_prop_source_modified = "qsl.source_modified"
        # clients only know the job layer id, the cache name is internal
        self._job_layer_ids: dict[str, str] = {}

    def _get_map_settings(self, layers: list[QgsMapLayer]) -> QgsMapSettings:
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
        settings.setOutputSize(QSize(int(self.job_info.job.width), int(self.job_info.job.height)))
        if self.job_info.job.dpi:
            settings.setOutputDpi(self.job_info.job.dpi)

        crs = self.job_info.job.crs
        destination_crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(crs)
        minx, miny, maxx, maxy = self.job_info.job.bbox.to_2d_list()
        bbox = QgsRectangle(float(minx), float(miny), float(maxx), float(maxy))
        if destination_crs.hasAxisInverted():  # lat-lon, instead of lon-lat e.g. epsg:4326
            bbox.invert()
        settings.setExtent(bbox)
        settings.setLayers(layers)
        settings.setBackgroundColor(QColor(Qt.transparent))

        settings.setDestinationCrs(destination_crs)
        return settings

    def _load_style(self, qgs_layer: QgsMapLayer, job_layer_definition: QslJobLayer):
        logging.info(f"Preparing job_layer_definition Style: {job_layer_definition.style.name}")

        # the custom attributes on layers are stored in the style in fact, so
        # we first have to secure the custom property before applying the filter
        logging.debug("Preserving subset string")
        original_filter = qgs_layer.customProperty(self._custom_prop_original_filter, None)
        source_modified = qgs_layer.customProperty(self._custom_prop_source_modified, None)
        style_doc = QDomDocument()
        style_xml = zlib.decompress(urlsafe_b64decode(job_layer_definition.style.definition))
        style_doc.setContent(style_xml)
        success, _ = qgs_layer.importNamedStyle(style_doc)

        # we are apply the secured custom property since it was potentially wiped
        # by applying the style
        logging.debug("Re-apply subset string")
        qgs_layer.setCustomProperty(self._custom_prop_original_filter, original_filter)
        qgs_layer.setCustomProperty(self._custom_prop_source_modified, source_modified)
        logging.info(f" ✓ Style loaded: {success}")

    def _apply_filter(self, qgs_layer: QgsVectorLayer, job_layer_definition: QslJobLayer):
        if job_layer_definition.filter:
            logging.debug("Job definition has a filter")
            if isinstance(job_layer_definition.filter, OgcFilter110):
                # TODO: This is potentially bad: We always get all features from
                #  datasource. However, QGIS
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
                original_filter = qgs_layer.customProperty(self._custom_prop_original_filter, None)
                if original_filter:
                    # Combining with AND the originally defined expression always takes precedence
                    expression = f"({original_filter}) AND ({filter_expression.expression()})"
                    logging.debug(f"Layer filter existed AND combined with passed: {expression}")
                else:
                    expression = filter_expression.expression()
                    logging.debug(f"No filter existed will be just the passed one: {expression}")
                qgs_layer.setSubsetString(expression)
        else:
            logging.debug("Job definition has no filter")
            # reset filter to original filter (provided from project) or to empty filter
            original_filter = qgs_layer.customProperty(self._custom_prop_original_filter, None)
            if original_filter is None:
                logging.debug("No original Filter, resetting to empty substring ''")
                qgs_layer.setSubsetString("")
            else:
                logging.debug(f"Original Filter, resetting to {original_filter}")
                qgs_layer.setSubsetString(original_filter)

    def get_cache_name(self, job_layer_definition: QslJobLayer) -> str:
        """Central method to decide which name is used in the cache to
        identify a layer.
        """
        return (
            f"{job_layer_definition.id}"
            f"{job_layer_definition.name}"
            f"{job_layer_definition.source}"
            f"{job_layer_definition.remote}"
            f"{job_layer_definition.folder_name}"
            f"{job_layer_definition.driver}"
        )

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
        self._job_layer_ids[cache_name] = job_layer_definition.id
        if self.layer_cache is not None and cache_name in self.layer_cache:
            logging.debug(
                f"Using cached job_layer_definition {job_layer_definition.name} "
                f"(identifier: {self._job_layer_ids[cache_name]})"
            )
            qgs_layer = self.layer_cache[cache_name]
            # retrying is up to the client, the next job initializes the layer again
            if outdated_reason := self._outdated_reason(qgs_layer, job_layer_definition):
                self._raise_on_layer_errors({cache_name: outdated_reason})
        else:
            qgs_layer = self._decide_drivers(job_layer_definition)
            # the cache name is the central identifier, errors reported by QGIS
            # carry the layer id and therefore point directly into the cache
            qgs_layer.setId(cache_name)
            qgs_layer.setCustomProperty(
                self._custom_prop_source_modified, self._source_modified(job_layer_definition)
            )
            qgs_layer.setTitle(job_layer_definition.name)
            if qgs_layer.isValid():
                logging.debug(
                    f"Newly initialized layer {job_layer_definition.name} "
                    f"is valid: {qgs_layer.isValid()}"
                )
                if self.layer_cache is not None:
                    self.layer_cache[cache_name] = qgs_layer
            else:
                logging.error(qgs_layer.error().message())
                logging.error(qgs_layer.dataProvider().error().message())
                raise RuntimeError(
                    f"Newly initialized layer {job_layer_definition.name} "
                    f"is not valid. JobLayerDefinition: {job_layer_definition}"
                )
        return qgs_layer

    def _throw_out_layer(self, cache_name: str) -> None:
        """Throws a layer out of the cache, so the next job initializes it again."""
        if self.layer_cache is not None:
            self.layer_cache.pop(cache_name, None)
            logging.warning(
                f"Evicted layer from cache (identifier: {self._job_layer_ids[cache_name]})"
            )

    def _outdated_reason(
        self, qgs_layer: QgsMapLayer, job_layer_definition: QslJobLayer
    ) -> str | None:
        """Evaluates if a cached layer became invalid or its local data source
        changed since it was cached.

        OGR does not report read errors of opened datasets (missing or corrupted
        files result in empty feature iterators), that is why local sources are
        checked by a fingerprint of their file.

        Returns:
            The reason why the layer is outdated, None if it is still usable.
        """
        if not (qgs_layer.isValid() and qgs_layer.dataProvider().isValid()):
            return "Cached layer became invalid"
        source_modified = qgs_layer.customProperty(self._custom_prop_source_modified, None)
        if source_modified != self._source_modified(job_layer_definition):
            return "Data source changed since caching"
        return None

    def _source_modified(self, job_layer_definition: QslJobLayer) -> str | None:
        """Fingerprint of a local data source file to detect replaced, changed or
        deleted files. Sidecar files are not considered, changes reach the main
        file eventually (e.g. on a GeoPackage WAL checkpoint).

        Returns:
            Modification time, size and inode of the file, None for remote or
            missing sources.
        """
        if job_layer_definition.remote:
            return None
        path = self._handle_datasource_definition(job_layer_definition)["path"]
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            return None
        return f"{stat.st_mtime_ns}:{stat.st_size}:{stat.st_ino}"

    def _raise_on_layer_errors(self, layer_errors: dict[str, str]) -> None:
        """Evicts all layers which failed during the job and lets the job fail.

        Args:
            layer_errors: Error messages by layer id (which is the cache name).
        Raises:
            RuntimeError: When at least one layer failed, the message names the
                job layer ids.
        """
        if layer_errors:
            for cache_name in layer_errors:
                self._throw_out_layer(cache_name)
            failed_job_layers = {
                self._job_layer_ids[cache_name]: message
                for cache_name, message in layer_errors.items()
            }
            raise RuntimeError(f"Layers failed: {failed_job_layers}")

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
        # this has to be before applying the filter!
        self._load_style(qgs_layer, job_layer_definition)
        if isinstance(qgs_layer, QgsVectorLayer):
            self._apply_filter(qgs_layer, job_layer_definition)
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

    def _decoded_layer_source_to_connection_string(self, driver: str, layer_source: dict) -> str:
        return QgsProviderRegistry.instance().encodeUri(driver, layer_source)

    def _prepare_vector_layer(self, job_layer_definition: QslJobLayer) -> QgsVectorLayer:
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
        logging.debug(f"Preserving predefined layer subset: {qgs_layer.subsetString()}")
        qgs_layer.setCustomProperty(self._custom_prop_original_filter, qgs_layer.subsetString())
        return qgs_layer

    def _prepare_custom_layer(self, job_layer_definition: QslJobLayer) -> QgsVectorTileLayer:
        """Initializes a custom job_layer_definition"""
        layer_source = self._handle_datasource_definition(job_layer_definition)
        layer_source_path = self._decoded_layer_source_to_connection_string(
            job_layer_definition.driver, layer_source
        )
        qgs_layer = QgsVectorTileLayer(layer_source_path, job_layer_definition.name)
        return qgs_layer

    def _prepare_raster_layer(self, job_layer_definition: QslJobLayer) -> QgsRasterLayer:
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
