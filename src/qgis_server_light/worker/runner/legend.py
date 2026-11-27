import logging
from collections.abc import MutableMapping

from qgis.core import (
    QgsApplication,
    QgsLayerTree,
    QgsLayerTreeModel,
    QgsLegendRenderer,
    QgsLegendSettings,
    QgsLegendStyle,
    QgsRenderContext,
)
from qgis.PyQt.QtCore import QJsonDocument, Qt
from qgis.PyQt.QtGui import QImage, QPainter

from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.legend.input import QslJobInfoLegend
from qgis_server_light.worker.runner.common import ImageRunner, JobContext


class GetLegendRunner(ImageRunner):
    job_info_class = QslJobInfoLegend

    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoLegend,
        layer_cache: MutableMapping | None = None,
    ) -> None:
        super().__init__(qgis, context, job_info, layer_cache)

    @classmethod
    def json_formats(cls):
        return ["application/json", "json"]

    def run(self):
        logging.info(f"Executing job: {self.job_info}")
        for job_layer_definition in self.job_info.job.layers:
            self._provide_layer(job_layer_definition)

        if not self.map_layers:
            raise RuntimeError("No legend entries available for requested layers")

        root = QgsLayerTree()
        for layer in self.map_layers:
            root.addLayer(layer)

        model = QgsLayerTreeModel(root)
        settings = QgsLegendSettings()
        # Wait for external legend requests to finish before rendering
        settings.setSynchronousLegendRequests(True)

        if (scale := self.job_info.job.scale) is not None:
            settings.setMapScale(scale)

        if not self.job_info.job.layer_title:
            style = QgsLegendStyle()
            style.setMargin(QgsLegendStyle.Bottom, 0)
            settings.setStyle(QgsLegendStyle.Title, style)
            for layer_node in root.children():
                QgsLegendRenderer.setNodeLegendStyle(layer_node, QgsLegendStyle.Hidden)

        renderer = QgsLegendRenderer(model, settings)

        if self.job_info.job.format.lower() in self.json_formats():
            return JobResult(
                id=self.job_info.id,
                data=self._export_json(renderer),
                content_type="application/json",
            )

        dpi = self.job_info.job.dpi
        px_per_mm = dpi / 25.4
        width = self.job_info.job.width
        height = self.job_info.job.height
        legend_size_mm = renderer.minimumSize()
        default_legend_width_px = int(legend_size_mm.width() * px_per_mm)
        default_legend_height_px = int(legend_size_mm.height() * px_per_mm)

        if width is None and height is None:
            # Default legend looks a bit too big, we scale it down by a bit
            width = int(0.75 * default_legend_width_px)
            height = int(0.75 * default_legend_height_px)
            painter_scale = 0.75
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
        image.fill(Qt.transparent)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.scale(painter_scale, painter_scale)

        renderer.drawLegend(painter)
        painter.end()

        content_type, image_data = self._encode_image(image, self.job_info.job.format)

        return JobResult(
            id=self.job_info.id,
            data=image_data,
            content_type=content_type,
        )

    @staticmethod
    def _export_json(renderer: QgsLegendRenderer) -> bytes:
        # same as QGIS Server does it, a default render context is enough here
        legend = renderer.exportLegendToJson(QgsRenderContext())
        return bytes(QJsonDocument(legend).toJson(QJsonDocument.JsonFormat.Compact))
