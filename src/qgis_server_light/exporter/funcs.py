from functools import reduce
from itertools import zip_longest
from typing import Any, Dict, List, Union

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsVectorLayer, QgsRasterLayer


def compose(*fs):
    """
    Returns the left-to-right composition of any Iterable of functions.
    Ex: compose(f, g, h)(*args, **kwargs) == h(g(f(*args, **kwargs)))
    """

    def reducer(out, f):
        if isinstance(out, tuple):
            args, kwargs = out
            if isinstance(args, tuple) and isinstance(kwargs, dict):
                return f(*args, **kwargs)

        return f(out)

    def capture_args(*args, **kwargs):
        return reduce(reducer, fs, (args, kwargs))

    return capture_args


def make_wgs84_geom_transform(project, layer) -> Any:
    """Makes a QgisCoordinateTransform to transform a layer to EPSG:4326)."""
    sourceCrs = layer.crs()
    EPSG_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
    return QgsCoordinateTransform(sourceCrs, EPSG_4326, project)


def extent_in_wgs84(project, layer) -> List:
    """
    Reprojects the layer's extent using a custom projection.
    Returns the coordinates as List of floats.
    """
    tr = make_wgs84_geom_transform(project, layer)
    rect = layer.extent()
    reprojected_rect = tr.transform(rect)
    return [
        reprojected_rect.xMinimum(),
        reprojected_rect.yMinimum(),
        reprojected_rect.xMaximum(),
        reprojected_rect.yMaximum(),
    ]


def get_layer_type(layer: QgsVectorLayer | QgsRasterLayer) -> str:
    """Gets the type of the given Qgis layer as a string if the type is supported."""
    if isinstance(layer, QgsRasterLayer):
        return "raster"
    elif isinstance(layer, QgsVectorLayer):
        return "vector"
    else:
        raise TypeError(f"Not implemented: {layer.type()}")


def get_project_server_entries(project, scope_or_scopes: Union[str, List]) -> Dict:
    """
    Gets values from the fields displayed in QGIS under Project > Properties > Server.
    Returns a Dictionary holding all pairs of <key, value> found at the corresponding scopes.
    Example:
        given   scope_or_scope = "wms" (or: ["wms"])
        returns { <wms_key1>: <wms_key1_value>, <wms_key2>: <wms_key2_value> ... }
    For now the implementation supports only WMS fields but can be easily expanded by
    adding <key/values> to the Dictionary below.
    """
    supported_scopes = {
        "wms": {
            "scopes": [
                ("WMSContactOrganization", "contact_organization"),
                ("WMSContactMail", "contact_mail"),
                ("WMSContactPerson", "contact_person"),
                ("WMSContactPhone", "contact_phone"),
                ("WMSContactPosition", "contact_position"),
                ("WMSFees", "fees"),
                ("WMSKeywordList", "keyword_list"),
                ("WMSOnlineResource", "online_resource"),
                ("WMSServiceAbstract", "service_abstract"),
                ("WMSServiceTitle", "service_title"),
                ("WMSUrl", "resource_url"),
            ],
            "keys": ["/"],
        }
    }

    scopes = [scope_or_scopes] if isinstance(scope_or_scopes, str) else scope_or_scopes

    for scope in scopes:

        if not scope in supported_scopes:
            supported = ", ".join(supported_scopes.keys())
            error_detail = (
                f"This scope is not supported: {scope}. Supported scopes: {supported}"
            )
            raise ValueError(error_detail)

        scope_entries = supported_scopes[scope]["scopes"]
        key_entries = supported_scopes[scope]["keys"]
        to_collect = zip_longest(scope_entries, key_entries, fillvalue=key_entries[0])

        def collect(acc, pair):
            scope, key = pair
            qgis_scope_name, our_scope_name = scope

            if "list" in qgis_scope_name.lower():
                # PyQGIS sometimes violates Liskov's substitution principle so naming tricks needed
                list_as_text = ", ".join(project.readListEntry(qgis_scope_name, key)[0])
                acc.append((our_scope_name, list_as_text))
            else:
                acc.append((our_scope_name, project.readEntry(qgis_scope_name, key)[0]))

            return acc

        return dict(reduce(collect, to_collect, []))
