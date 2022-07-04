import logging
import os
import json

from mako.lookup import TemplateLookup
from pyramid.renderers import render_to_response
from pyramid.response import Response
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound
from pyramid.path import AssetResolver
from pyramid.config import ConfigurationError

from qgis.server import QgsServerFilter
from qgis.core import QgsMapSettings, QgsMapRendererParallelJob, QgsVectorLayer, QgsMessageLog, Qgis, \
    QgsReadWriteContext, QgsRectangle, QgsRasterLayer

from PyQt5.QtCore import QSize, QByteArray, QBuffer, QIODevice, QEventLoop, Qt, QFile
from PyQt5.QtGui import QColor
from PyQt5.QtXml import QDomDocument


log = logging.getLogger('qgis_server_light')



class WebMapService(object):

    def __init__(self, request):
        """
        Entry point for service. Everything comes in here.

        Args:
            request (pyramid.request.Request): The request instance.

        """
        self._request = request
        self.params = {}
        for key in request.params:
            self.params[key.upper()] = request.params[key]
        if request.matchdict['theme'] == "favicon.ico":
            raise HTTPNotFound()
        self.theme_name = request.matchdict['theme']
        self.theme_config = json.loads(
            open(
                os.path.join(self._request.get_settings['themes_dir'], self.theme_name, 'config.json')
            ).read()
        )
        self.themes_path = os.path.join(self._request.get_settings['themes_dir'], self.theme_name)
        self.theme_config.update({'theme_name': self.theme_name})
        self.theme_config.update({'request_parameters': self.params})
        log.debug('Queried theme was {}'.format(self.theme_name))
        if not self.params.get('SERVICE'):
            raise HTTPBadRequest('Parameter SERVICE is mandatory')
        if not self.params.get('REQUEST'):
            raise HTTPBadRequest('Parameter REQUEST is mandatory')
        self.resolver = AssetResolver('qgis_server_light')

    def entry_point(self):
        if self.params['SERVICE'].upper() == 'WMS' and self.params['REQUEST'].upper() == "GETCAPABILITIES":
            return self.wms_capabilities()
        if self.params['SERVICE'].upper() == 'WMS' and self.params['REQUEST'].upper() == "GETMAP":
            return self.wms_getmap()
        else:
            raise  HTTPNotFound()

    def wms_capabilities(self):
        if self.params.get('VERSION') == '1.1.1' or not self.params.get('VERSION'):
            resolver = self.resolver.resolve('templates/capabilities/version_111')
            templates = TemplateLookup(
                directories=[resolver.abspath()],
                output_encoding='utf-8',
                input_encoding='utf-8'
            )
            template = templates.get_template('capabilities.xml')
            self.theme_config.update({'request': self._request})
            content = template.render(**self.theme_config)
            return Response(content, content_type='text/xml')

    def wms_getmap(self):
        if self.params.get('LAYERS'):
            layer_names = self.params['LAYERS'].split(',')
            layers_on_map = []
            for layer_name in layer_names:
                self._collect_layers(self.theme_config['layers'], layer_name, layers_on_map)
            settings = QgsMapSettings()
            settings.setOutputSize(QSize(int(self.params['WIDTH']), int(self.params['HEIGHT'])))
            dpi = int(self.params.get('DPI', 96))
            settings.setOutputDpi(dpi)
            minx, miny, maxx, maxy = self.params.get('BBOX').split(',')
            bbox = QgsRectangle(float(minx), float(miny), float(maxx), float(maxy))
            settings.setExtent(bbox)
            settings.setLayers(layers_on_map)
            settings.setBackgroundColor(QColor(Qt.transparent))
            renderer = QgsMapRendererParallelJob(settings)
            event_loop = QEventLoop(self._request.get_qgis_app)
            renderer.finished.connect(event_loop.quit)
            renderer.start()
            event_loop.exec_()
            img = renderer.renderedImage()
            img.setDotsPerMeterX(dpi * 39.37)
            img.setDotsPerMeterY(dpi * 39.37)
            image_data = QByteArray()
            buf = QBuffer(image_data)
            buf.open(QIODevice.WriteOnly)
            img.save(buf, 'PNG')
            return Response(image_data, content_type='image/png')
        else:
            raise HTTPBadRequest('Parameter LAYERS is mandatory for GetMap')

    def _collect_layers(self, layer_config, layer_name, layers_on_map):
        if layer_config[layer_name]['type'] == 'group':
            for child in layer_config[layer_name]['childs']:
                self._collect_layers(layer_config, child, layers_on_map)
        else:
            layer = None
            if layer_config[layer_name]['type'] == 'vector-file':
                layers_on_map.append(self._prepare_vector_file_layer(layer_config[layer_name], layer_name))
            elif layer_config[layer_name]['type'] == 'raster-file':
                layers_on_map.append(self._prepare_raster_file_layer(layer_config[layer_name], layer_name))
            else:
                raise ConfigurationError('Type not implemented: {}'.format(layer_config[layer_name]['type']))


    def _prepare_vector_file_layer(self, config, layer_name):
        layer_source_path = os.path.join(self.themes_path, 'data', config['path'])
        style_source_path = os.path.join(self.themes_path, 'styles', config['style'])
        layer = QgsVectorLayer(layer_source_path, layer_name, config['driver'])
        layer.loadNamedStyle(style_source_path)
        return layer

    def _prepare_raster_file_layer(self, config, layer_name):
        layer_source_path = os.path.join(self.themes_path, 'data', config['path'])
        style_source_path = os.path.join(self.themes_path, 'styles', config['style'])
        layer = QgsRasterLayer(layer_source_path, layer_name, config['driver'])
        layer.loadNamedStyle(style_source_path)
        return layer
