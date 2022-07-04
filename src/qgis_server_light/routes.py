# -*- coding: utf-8 -*-
from qgis_server_light.views.index import Service
from qgis_server_light.views.ogc import WebMapService


def includeme(config):
    """
    The place to configure all route/url matching in the application

    Args:
        config (pyramid.config.Configurator): The application's configuration object.

    """
    config.add_route('welcome', '/')
    config.add_view(
        Service,
        attr='welcome_desk',
        route_name='welcome',
        request_method='GET'
    )

    config.add_route('ogc', '/{theme}')
    config.add_view(
        WebMapService,
        attr='entry_point',
        route_name='ogc',
        request_method='GET'
    )
