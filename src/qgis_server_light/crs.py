"""This module contains the crs handling shared by the exporter and the worker. It is the
only place where QGIS crs information is translated into the QGIS-Server-Light interface."""

from qgis.core import QgsCoordinateReferenceSystem

from qgis_server_light.interface.common import Crs


def create_qsl_crs(crs: QgsCoordinateReferenceSystem) -> Crs:
    """
    Translates a QGIS crs into an instance of the QGIS-Server-Light interface Crs.

    Args:
        crs: The QGIS crs to take the information from.

    Returns:
        The instance of the QSL interface Crs.
    """
    return Crs(
        postgis_srid=crs.postgisSrid(),
        auth_id=crs.authid(),
        ogc_uri=crs.toOgcUri(),
        ogc_urn=crs.toOgcUrn(),
        axis_inverted=crs.hasAxisInverted(),
    )
