import logging
from typing import Dict, Optional, Tuple

from fpng_py import CompressionFlags, fpng_encode_image_to_memory
from qgis.core import (
    QgsApplication,
    QgsLayerTree,
    QgsLayerTreeModel,
    QgsLegendRenderer,
    QgsLegendSettings,
    QgsLegendStyle,
)
from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, Qt
from qgis.PyQt.QtGui import QImage, QPainter

from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.legend.input import QslJobInfoLegend
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class GetLegendRunner(MapRunner):
    job_info_class = QslJobInfoLegend

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoLegend,
        layer_cache: Optional[Dict] = None,
    ) -> None:
        super().__init__(qgis, context, job_info, layer_cache)

    @classmethod
    def image_formats(cls):
        return {"image/png": cls._encode_png, "image/jpeg": cls._encode_jpg}

    def run(self):
        logging.info(f"Executing job: {self.job_info}")
        for job_layer_definition in self.job_info.job.layers:
            self._provide_layer(job_layer_definition)

        if not self.map_layers:
            raise RuntimeError("No legend entries available for requested layers")

        root = QgsLayerTree()
        for layer in self.map_layers:
            root.addLayer(layer)

        dpi = self.job_info.job.dpi
        px_per_mm = dpi / 25.4

        model = QgsLayerTreeModel(root)
        settings = QgsLegendSettings()

        if (scale := self.job_info.job.scale) is not None:
            settings.setMapScale(scale)

        if not self.job_info.job.layer_title:
            style = QgsLegendStyle()
            style.setMargin(QgsLegendStyle.Bottom, 0)
            settings.setStyle(QgsLegendStyle.Title, style)
            for layer_node in root.children():
                QgsLegendRenderer.setNodeLegendStyle(layer_node, QgsLegendStyle.Hidden)

        renderer = QgsLegendRenderer(model, settings)

        width = self.job_info.job.width
        height = self.job_info.job.height
        legend_size_mm = renderer.minimumSize()
        default_legend_width_px = int(legend_size_mm.width() * px_per_mm)
        default_legend_height_px = int(legend_size_mm.height() * px_per_mm)

        if width is None and height is None:
            width = default_legend_width_px
            height = default_legend_height_px
            painter_scale = 1.0
        elif width is None:
            painter_scale = height / default_legend_height_px
            width = int(default_legend_width_px * painter_scale)
        elif height is None:
            painter_scale = width / default_legend_width_px
            height = int(default_legend_height_px * painter_scale)
        else:
            x_scale = width / (legend_size_mm.width() * px_per_mm)
            y_scale = height / (legend_size_mm.height() * px_per_mm)
            painter_scale = min(x_scale, y_scale)

        image = QImage(width, height, QImage.Format_ARGB32)
        image.setDotsPerMeterX(int(dpi * 39.37))
        image.setDotsPerMeterY(int(dpi * 39.37))
        image.fill(Qt.white)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.scale(painter_scale, painter_scale)

        renderer.drawLegend(painter)
        painter.end()

        content_type, image_data = self._encode_image(
            image, self.job_info.job.format.lower()
        )

        return JobResult(
            id=self.job_info.id,
            data=image_data,
            content_type=content_type,
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
                f"Requested mimtype '{fmt}' was found in {list(self.image_formats())}."
            )

    @staticmethod
    def _encode_png(image: QImage):
        image = image.convertToFormat(QImage.Format_RGBA8888)
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
