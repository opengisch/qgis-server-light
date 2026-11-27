import logging
from collections.abc import MutableMapping

from PyQt5.QtCore import QEventLoop
from qgis.core import Qgis, QgsApplication, QgsMapRendererParallelJob
from qgis.server import QgsFeatureFilter, QgsFeatureFilterProviderGroup

from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.render.input import QslJobInfoRender
from qgis_server_light.worker.runner.common import ImageRunner, JobContext


class RenderRunner(ImageRunner):
    """Responsible for rendering a QslRenderJob to an image."""

    job_info_class = QslJobInfoRender

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoRender,
        layer_cache: MutableMapping | None = None,
    ) -> None:
        super().__init__(qgis, context, job_info, layer_cache)

    def run(self):
        """Run this runner.
        Returns:
            A JobResult with the content_type and image_data (bytes) of the rendered image.
        """
        logging.info(f"Executing job: {self.job_info}")
        feature_filter = QgsFeatureFilter()
        for job_layer_definition in self.job_info.job.layers:
            self._provide_layer(job_layer_definition)
        map_settings = self._get_map_settings(self.map_layers)
        # QGIS emits finished synchronously in start() on invalid settings (e.g.
        # an empty bbox), before the event loop runs, so it would wait forever
        if not map_settings.hasValidSettings():
            raise RuntimeError(
                f"Invalid map settings, bbox: {self.job_info.job.bbox}, "
                f"size: {self.job_info.job.width}x{self.job_info.job.height}"
            )
        # same as QGIS Server GetMap, enables the simplification on rendering
        # which is defined in the layer styles
        map_settings.setFlag(Qgis.MapSettingsFlag.UseRenderingOptimization)
        filter_providers = QgsFeatureFilterProviderGroup()
        filter_providers.addProvider(feature_filter)
        renderer = QgsMapRendererParallelJob(map_settings)
        renderer.setFeatureFilterProvider(filter_providers)
        event_loop = QEventLoop(self.qgis)
        renderer.finished.connect(event_loop.quit)
        renderer.start()
        event_loop.exec_()
        self._raise_on_layer_errors({error.layerID: error.message for error in renderer.errors()})
        img = renderer.renderedImage()
        img.setDotsPerMeterX(int(map_settings.outputDpi() * 39.37))
        img.setDotsPerMeterY(int(map_settings.outputDpi() * 39.37))
        content_type, image_data = self._encode_image(img, self.job_info.job.format)
        return JobResult(id=self.job_info.id, data=image_data, content_type=content_type)
