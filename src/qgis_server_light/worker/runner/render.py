import logging
from typing import Dict, Optional, Tuple

from fpng_py import CompressionFlags, fpng_encode_image_to_memory
from PyQt5.QtCore import QBuffer, QByteArray, QEventLoop, QIODevice
from PyQt5.QtGui import QImage
from qgis.core import QgsApplication, QgsMapRendererParallelJob
from qgis.server import QgsFeatureFilter, QgsFeatureFilterProviderGroup

from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.render.input import QslJobInfoRender
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class RenderRunner(MapRunner):
    """Responsible for rendering a QslRenderJob to an image."""

    job_info_class = QslJobInfoRender

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoRender,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        super().__init__(qgis, context, job_info, layer_cache)

    @classmethod
    def image_formats(cls):
        return {"image/png": cls._encode_png, "image/jpeg": cls._encode_jpg}

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
        filter_providers = QgsFeatureFilterProviderGroup()
        filter_providers.addProvider(feature_filter)
        renderer = QgsMapRendererParallelJob(map_settings)
        renderer.setFeatureFilterProvider(filter_providers)
        event_loop = QEventLoop(self.qgis)
        renderer.finished.connect(event_loop.quit)
        renderer.start()
        event_loop.exec_()
        img = renderer.renderedImage()
        img.setDotsPerMeterX(int(map_settings.outputDpi() * 39.37))
        img.setDotsPerMeterY(int(map_settings.outputDpi() * 39.37))
        content_type, image_data = self._encode_image(img, self.job_info.job.format)
        return JobResult(
            id=self.job_info.id, data=image_data, content_type=content_type
        )

    def _encode_image(self, image: QImage, fmt: str) -> Tuple[str, bytearray]:
        """Encodes an image in a specific mime type
        Args:
            image (QImage): The image to encode
            fmt (str): The mime type of the format
        Returns:
            A tuple with mime type and bytes-like object of an encoded image in the desired format
        """
        try:
            fmt = fmt.lower()
            encoding_method = self.image_formats()[fmt]
            return fmt, encoding_method(image)
        except KeyError:
            raise RuntimeError(
                f"Requested mimtype '{fmt}' was found in {list(self.image_formats.keys())}."
            )

    @staticmethod
    def _encode_png(image: QImage):
        image.convertTo(QImage.Format_RGBA8888)
        image_data = fpng_encode_image_to_memory(
            image.constBits().asstring(image.sizeInBytes()),
            image.width(),
            image.height(),
            0,
            CompressionFlags.NONE,
        )
        return image_data

    @staticmethod
    def _encode_jpg(image: QImage):
        image_data = QByteArray()
        buf = QBuffer(image_data)
        buf.open(QIODevice.WriteOnly)
        image.save(buf, "JPG")
        return image_data
