# -*- coding: utf-8 -*-
import logging

from pyramid.renderers import render_to_response
from pyramid.response import Response

log = logging.getLogger('qgis_server_light')


class Service(object):

    def __init__(self, request):
        """
        Entry point for service. Everything comes in here.

        Args:
            request (pyramid.request.Request): The request instance.

        """
        self._request = request

    def welcome_desk(self):
        return Response(
            '<h1>Welcome to QGIS Server light</h1>',
            content_type='text/html; charset=UTF-8'
        )
