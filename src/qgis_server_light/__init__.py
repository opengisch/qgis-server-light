# -*- coding: utf-8 -*-
import os
import logging
import yaml
from pyramid.config import Configurator
from pyramid_mako import add_mako_renderer

from qgis.core import QgsApplication

__version__ = 'v1.0.0'

log = logging.getLogger('qgis_server_light')


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """
    settings.update(
        {
            'themes_dir': os.environ['OGIS_SERVER_LIGHT_THEMES_DIR']
        }
    )
    config = Configurator(
        settings=settings
    )
    config.include('qgis_server_light')
    return config.make_wsgi_app()


def includeme(config):  # pragma: no cover
    """
    This is the place where you should push all the initial stuff for the plugin

    Args:
        config (pyramid.config.Configurator): The configurator object from the including pyramid module.

    """
    # If you need access to the settings in this part, you can get them via
    # settings = config.get_settings()

    # set log lever through env variable
    log.setLevel(os.environ['OGIS_SERVER_LIGHT_LOG_LEVEL'])

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    QgsApplication.setPrefixPath("/usr/lib/qgis", False)
    qgs = QgsApplication([], False)
    QgsApplication.initQgis()

    try:
        # Bind the mako renderer to other file extensions
        add_mako_renderer(config, ".xml")

        config.include('pyramid_tm')
        config.include('pyramid_mako')
        config.include('.routes')


        config.scan()

        log.info('Starting qgis_server_light {0}'.format(__version__))

        # Create method to return application settings
        def get_settings(request):
            return config.get_settings()

        def get_qgis_app(request):
            return qgs

        # Add method to request
        config.add_request_method(get_settings, name='get_settings', reify=True)
        config.add_request_method(get_qgis_app, name='get_qgis_app', reify=True)


        config.include('qgis_server_light.routes')

    except Exception as e:
        log.exception(e)
