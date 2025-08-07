import json
import re
import unicodedata
import zlib
from base64 import urlsafe_b64encode
from os import path
from typing import List
from typing import Tuple
from typing import Union

import pgserviceparser
from PyQt5.QtCore import QMetaType
from PyQt5.QtXml import QDomDocument
from qgis._core import QgsDataSourceUri
from qgis.core import QgsDateTimeFieldFormatter
from qgis.core import QgsField
from qgis.core import QgsFieldConstraints
from qgis.core import QgsLayerTree
from qgis.core import QgsLayerTreeGroup
from qgis.core import QgsLayerTreeLayer
from qgis.core import QgsMapLayer
from qgis.core import QgsProject
from qgis.core import QgsProviderRegistry
from qgis.core import QgsVectorLayer

from qgis_server_light.exporter.funcs import extent_in_wgs84
from qgis_server_light.exporter.funcs import get_layer_type
from qgis_server_light.exporter.funcs import get_project_server_entries
from qgis_server_light.interface.qgis import BBox
from qgis_server_light.interface.qgis import Config
from qgis_server_light.interface.qgis import Crs
from qgis_server_light.interface.qgis import Custom
from qgis_server_light.interface.qgis import Datasets
from qgis_server_light.interface.qgis import DataSource
from qgis_server_light.interface.qgis import Field
from qgis_server_light.interface.qgis import GdalSource
from qgis_server_light.interface.qgis import Group
from qgis_server_light.interface.qgis import MetaData
from qgis_server_light.interface.qgis import OgrSource
from qgis_server_light.interface.qgis import PostgresSource
from qgis_server_light.interface.qgis import Project
from qgis_server_light.interface.qgis import Raster
from qgis_server_light.interface.qgis import Service
from qgis_server_light.interface.qgis import Style
from qgis_server_light.interface.qgis import Tree
from qgis_server_light.interface.qgis import TreeGroup
from qgis_server_light.interface.qgis import Vector
from qgis_server_light.interface.qgis import VectorTileSource
from qgis_server_light.interface.qgis import WfsSource
from qgis_server_light.interface.qgis import WmsSource
from qgis_server_light.interface.qgis import WmtsSource


def obtain_simple_types(field: QgsField) -> str:
    """

    Args:
        field: The field of an `QgsVectorLayer`.

    Returns:
        Unified type name regarding
        [XSD spec](https://www.w3.org/TR/xmlschema11-2/#built-in-primitive-datatypes)
        IMPORTANT: If type is not matched within the function it will be `string` always!
    """
    attribute_type = field.type()
    if attribute_type == QMetaType.Type.Int:
        return "int"
    elif attribute_type == QMetaType.Type.UInt:
        return "unsignedInt"
    elif attribute_type == QMetaType.Type.LongLong:
        return "long"
    elif attribute_type == QMetaType.Type.ULongLong:
        return "unsignedLong"
    elif attribute_type == QMetaType.Type.Double:
        if field.length() > 0 and field.precision() == 0:
            return "integer"
        else:
            return "decimal"
    elif attribute_type == QMetaType.Type.Bool:
        return "boolean"
    elif attribute_type == QMetaType.Type.QDate:
        return "date"
    elif attribute_type == QMetaType.Type.QTime:
        return "time"
    elif attribute_type == QMetaType.Type.QDateTime:
        return "dateTime"
    else:
        return "string"


def obtain_simple_types_from_editor_widget(field: QgsField) -> str | None:
    """
    We simply mimikri [QGIS Server here](https://github.com/qgis/QGIS/blob/de98779ebb117547364ec4cff433f062374e84a3/src/server/services/wfs/qgswfsdescribefeaturetype.cpp#L153-L192)

    TODO: This could be improved alot! Maybe we can also backport that to QGIS core some day?

    Args:
        field: The field of an `QgsVectorLayer`.

    Returns:
        Unified type name regarding
        [XSD spec](https://www.w3.org/TR/xmlschema11-2/#built-in-primitive-datatypes)
    """
    attribute_type = field.type()
    setup = field.editorWidgetSetup()
    config = setup.config()
    if setup.type() == "DateTime":
        field_format = config.get(
            "field_format", QgsDateTimeFieldFormatter.defaultFormat(attribute_type)
        )
        if field_format == QgsDateTimeFieldFormatter.TIME_FORMAT:
            return "time"
        elif field_format == QgsDateTimeFieldFormatter.DATE_FORMAT:
            return "date"
        elif field_format == QgsDateTimeFieldFormatter.DATETIME_FORMAT:
            return "dateTime"
        elif field_format == QgsDateTimeFieldFormatter.QT_ISO_FORMAT:
            return "dateTime"
    elif setup.type() == "Range":
        if config.get("Precision"):
            config_precision = int(config["Precision"])
            if config_precision != field.precision():
                if config_precision == 0:
                    return "integer"
                else:
                    return "decimal"


def obtain_nullable(field: QgsField):
    if not (
        field.constraints().constraints()
        == QgsFieldConstraints.Constraint.ConstraintNotNull
    ):
        return True


def extract_fields(
    layer: QgsVectorLayer, types_from_editor_widget: bool = False
) -> List[Field]:
    fields = []
    pk_indexes = layer.dataProvider().pkAttributeIndexes()
    for field_index, field in enumerate(layer.fields()):
        attribute_type = obtain_simple_types(field)
        if types_from_editor_widget:
            editor_widget_type = obtain_simple_types_from_editor_widget(field)
            if editor_widget_type:
                attribute_type = editor_widget_type
        fields.append(
            Field(
                name=field.name(),
                type=field.typeName(),
                type_simple=attribute_type,
                alias=field.alias() or field.name().title(),
                nullable=(field_index not in pk_indexes) and obtain_nullable(field),
            )
        )
    return fields


def create_unified_short_name(name: str, path: list[str]):
    short_name_part = path + [name]
    return ".".join(short_name_part)


def create_style_list(qgs_layer: QgsMapLayer) -> List[Style]:
    style_names = qgs_layer.styleManager().styles()
    style_list = []
    for style_name in style_names:
        style_doc = QDomDocument()
        qgs_layer.styleManager().setCurrentStyle(style_name)
        qgs_layer.exportNamedStyle(style_doc)
        style_list.append(
            Style(
                name=style_name,
                definition=urlsafe_b64encode(
                    zlib.compress(style_doc.toByteArray())
                ).decode(),
            )
        )
    return style_list


def decide_sslmode(ssl_mode: int) -> str:
    """
    Mapper to map ssl modes from QGIS to plain postgres.

    Args:
        ssl_mode: The ssl mode of the datasource.

    Returns:
        The string representation of the ssl mode as it is used by postgres connections.
    Raises:
        LookupError: If the given ssl mode is not supported.
    """
    if ssl_mode == QgsDataSourceUri.SslDisable:
        return "disable"
    elif ssl_mode == QgsDataSourceUri.SslAllow:
        return "allow"
    elif ssl_mode == QgsDataSourceUri.SslPrefer:
        return "prefer"
    elif ssl_mode == QgsDataSourceUri.SslRequire:
        return "require"
    elif ssl_mode == QgsDataSourceUri.SslVerifyCa:
        return "verify-ca"
    elif ssl_mode == QgsDataSourceUri.SslVerifyFull:
        return "verify-full"
    else:
        raise LookupError(f"Unknown ssl mode {ssl_mode}")


def extract_save_layer(
    project: QgsProject,
    child: QgsLayerTreeLayer,
    tree: Tree,
    datasets: Datasets,
    path: list[str],
    unify_layer_names_by_group: bool = False,
    types_from_editor_widget: bool = False,
):
    """Save the given layer to the output path."""
    layer = child.layer()

    QDomDocument()

    layer_type = get_layer_type(layer)
    decoded = QgsProviderRegistry.instance().decodeUri(
        layer.providerType(), layer.dataProvider().dataSourceUri()
    )
    for key in decoded:
        if str(decoded[key]) == "None":
            decoded[key] = None
        elif str(decoded[key]) == "NULL":
            decoded[key] = None
        else:
            decoded[key] = str(decoded[key])
        if key == "path":
            decoded[key] = decoded[key].replace(f'{project.readPath("./")}/', "")
    short_name = get_layer_short_name(child)
    if unify_layer_names_by_group:
        short_name = create_unified_short_name(short_name, path)
    layer_crs = layer.dataProvider().crs()
    crs = Crs(
        postgis_srid=layer_crs.postgisSrid(),
        auth_id=layer_crs.authid(),
        ogc_uri=layer_crs.toOgcUri(),
        ogc_urn=layer_crs.toOgcUrn(),
    )

    extent_wgs_84 = extent_in_wgs84(project, layer)
    bbox_wgs84 = BBox(
        x_min=extent_wgs_84[0],
        x_max=extent_wgs_84[2],
        y_min=extent_wgs_84[1],
        y_max=extent_wgs_84[3],
    )
    extent = layer.extent()
    bbox = BBox.from_list(
        [
            extent.xMinimum(),
            extent.yMinimum(),
            0.0,
            extent.xMaximum(),
            extent.yMaximum(),
            0.0,
        ]
    )
    if layer_type == "vector":
        source_path = layer.source()
        if layer.providerType().lower() == "ogr":
            source = DataSource(
                ogr=OgrSource(
                    path=decoded["path"],
                    layer_name=decoded["layerName"],
                    layer_id=decoded["layerId"],
                )
            )
        elif layer.providerType().lower() == "postgres":
            config = decoded
            if decoded.get("service"):
                service_config = pgserviceparser.service_config(decoded["service"])
                # merging pg_service content with config of qgis project (qgis project config overwrites
                # pg_service configs
                config = service_config | decoded
            if config.get("username"):
                username = config["username"]
            elif config.get("user"):
                username = config["user"]
            else:
                raise LookupError(
                    f"Configuration does not contain any info about the db user name {config}"
                )
            source = DataSource(
                postgres=PostgresSource(
                    dbname=config["dbname"],
                    geometry_column=config["geometrycolumn"],
                    host=config["host"],
                    key=config["key"],
                    password=config["password"],
                    port=config["port"],
                    schema=config["schema"],
                    srid=config.get("srid"),
                    table=config["table"],
                    type=config["type"],
                    username=username,
                    sslmode=decide_sslmode(int(config.get("sslmode", 0))),
                )
            )
            if decoded.get("service"):
                del config["service"]
            source_path = QgsProviderRegistry.instance().encodeUri(
                layer.providerType(), config
            )

        elif layer.providerType().lower() == "wfs":
            # TODO: Correctly implement source!
            source = WfsSource()
        else:
            raise NotImplementedError(
                f"Unknown provider type: {layer.providerType().lower()}"
            )
        fields = extract_fields(layer, types_from_editor_widget)
        datasets.vector.append(
            Vector(
                path=source_path.replace(f'{project.readPath("./")}/', ""),
                name=short_name,
                title=layer.title() or layer.name(),
                styles=create_style_list(layer),
                driver=layer.providerType(),
                bbox_wgs84=bbox_wgs84,
                fields=fields,
                source=source,
                id=layer.id(),
                crs=crs,
                bbox=bbox,
                minimum_scale=layer.minimumScale(),
                maximum_scale=layer.maximumScale(),
                geometry_type_simple=layer.geometryType().name,
                geometry_type_wkb=layer.wkbType().name,
            )
        )
    elif layer_type == "raster":
        if layer.providerType() == "gdal":
            source = DataSource(
                gdal=GdalSource(path=decoded["path"], layer_name=decoded["layerName"])
            )
        elif layer.providerType() == "wms":
            if "tileMatrixSet" in decoded:
                source = DataSource(
                    wmts=WmtsSource(
                        contextual_wms_legend=decoded.get("contextualWMSLegend"),
                        crs=decoded["crs"],
                        dpi_mode=decoded.get("dpiMode"),
                        feature_count=decoded.get("featureCount"),
                        format=decoded["format"],
                        layers=decoded["layers"],
                        styles=decoded["styles"],
                        tile_dimensions=decoded.get("tileDimensions"),
                        tile_matrix_set=decoded["tileMatrixSet"],
                        tile_pixel_ratio=decoded.get("tilePixelRatio"),
                        url=decoded["url"],
                    )
                )
            else:
                source = DataSource(
                    wms=WmsSource(
                        contextual_wms_legend=decoded.get("contextualWMSLegend"),
                        crs=decoded["crs"],
                        dpi_mode=decoded.get("dpiMode"),
                        feature_count=decoded.get("featureCount"),
                        format=decoded["format"],
                        layers=decoded["layers"],
                        url=decoded["url"],
                    )
                )
        else:
            raise NotImplementedError(
                f"Unknown provider type: {layer.providerType().lower()}"
            )
        datasets.raster.append(
            Raster(
                path=layer.source().replace(f'{project.readPath("./")}/', ""),
                name=short_name,
                title=layer.title() or layer.name(),
                styles=create_style_list(layer),
                driver=layer.providerType(),
                bbox_wgs84=bbox_wgs84,
                source=source,
                id=layer.id(),
                crs=crs,
                bbox=bbox,
                minimum_scale=layer.minimumScale(),
                maximum_scale=layer.maximumScale(),
            )
        )
    elif layer_type == "custom":
        if layer.providerType().lower() == "xyzvectortiles":
            source = DataSource(
                vector_tile=VectorTileSource(
                    styleUrl=decoded["styleUrl"],
                    url=decoded["url"],
                    zmax=decoded["zmax"],
                    zmin=decoded["zmin"],
                    type=decoded["type"],
                )
            )
        else:
            raise NotImplementedError(
                f"Unknown provider type: {layer.providerType().lower()}"
            )
            # TODO: make this more configurable
        datasets.custom.append(
            Custom(
                path=layer.source().replace(f'{project.readPath("./")}/', ""),
                name=short_name,
                title=layer.title() or layer.name(),
                styles=create_style_list(layer),
                driver=layer.providerType(),
                bbox_wgs84=bbox_wgs84,
                source=source,
                id=layer.id(),
                crs=crs,
                bbox=bbox,
                minimum_scale=layer.minimumScale(),
                maximum_scale=layer.maximumScale(),
            )
        )
    else:
        raise NotImplementedError(f'Unknown layer_type "{layer_type}"')


def sanitize_name(raw: str, lower: bool = False) -> str:
    """
    Wandelt einen beliebigen String in einen WMS/WFS‑ und URL‑Pfad‑
    kompatiblen Layer‑Kurznamen um.

    Schritte:
    1. Unicode‑NFD → ASCII‑Transliteration (entfernt Umlaute/Diakritika).
    2. Alle Zeichen, die NICHT [A‑Za‑z0‑9_.‑] sind, durch '_' ersetzen.
    3. Mehrere Unterstriche auf einen reduzieren.
    4. Führende/abschließende '_', '.', '-' entfernen.
    5. Falls der Name leer ist ODER nicht mit Buchstabe bzw. '_' beginnt,
       vorne '_' voranstellen.
    6. Optional alles in Kleinbuchstaben konvertieren (lower=True).
    """
    # 1. cleaning to ASCII
    ascii_str = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    # 2. not allowed → '_'
    ascii_str = re.sub(r"[^A-Za-z0-9_.-]+", "_", ascii_str)
    # 3. remove multiple '_'
    ascii_str = re.sub(r"_+", "_", ascii_str)
    # 4. remove trailing chars
    ascii_str = ascii_str.strip("._-")
    # 5. ensure first char is correct (mainly xml stuff and URL)
    if not ascii_str or not re.match(r"[A-Za-z_]", ascii_str[0]):
        ascii_str = "_" + ascii_str
    # 6. Optional lowercase
    if lower:
        ascii_str = ascii_str.lower()
    return ascii_str


def get_group_short_name(group: QgsLayerTreeGroup) -> str:
    if group.customProperty("wmsShortName"):
        return group.customProperty("wmsShortName")
    elif hasattr(group, "groupLayer"):
        # since QGIS 3.38
        if group.groupLayer():
            if group.groupLayer().serverProperties():
                if group.groupLayer().serverProperties().shortName():
                    return group.groupLayer().serverProperties().shortName()
    short_name = sanitize_name(group.name(), lower=True)
    if short_name == "_":
        # this is the tree root, we return empty string here
        return ""
    return short_name


def get_group_title(group: QgsLayerTreeGroup) -> str:
    if group.customProperty("wmsTitle"):
        return group.customProperty("wmsTitle")
    elif hasattr(group, "groupLayer"):
        # since QGIS 3.38
        if group.groupLayer():
            if group.groupLayer().serverProperties():
                if group.groupLayer().serverProperties().title():
                    return group.groupLayer().serverProperties().title()
    return group.name()


def get_layer_short_name(layer: QgsLayerTreeLayer) -> str:
    if layer.layer().shortName():
        return layer.layer().shortName()
    elif hasattr(layer.layer(), "serverProperties"):
        if layer.layer().serverProperties().shortName():
            return layer.layer().serverProperties().shortName()
    return layer.layer().id()


def extract_group(
    group: QgsLayerTreeGroup,
    tree: Tree,
    datasets: Datasets,
    path: list[str],
    unify_layer_names_by_group=False,
    types_from_editor_widget: bool = False,
):
    """Collects data pertaining to a QGIS layer tree group."""
    children = []
    for child in group.children():
        if isinstance(child, QgsLayerTreeGroup):
            children.append(get_group_short_name(child))
        else:
            if unify_layer_names_by_group:
                children.append(
                    create_unified_short_name(get_layer_short_name(child), path)
                )
            else:
                children.append(get_layer_short_name(child))
    tree.members.append(TreeGroup(name=get_group_short_name(group), children=children))
    datasets.group.append(
        Group(
            name=get_group_short_name(group),
            title=get_group_title(group),
        )
    )


def extract_entities(
    project: QgsProject,
    entity: Union[QgsLayerTree, QgsLayerTreeGroup, QgsLayerTreeLayer],
    tree: Tree,
    datasets: Datasets,
    path: list[str],
    unify_layer_names_by_group=False,
    types_from_editor_widget: bool = False,
):
    if isinstance(entity, QgsLayerTreeLayer):
        extract_save_layer(
            project,
            entity,
            tree,
            datasets,
            path,
            unify_layer_names_by_group,
            types_from_editor_widget,
        )

    # If the entity has an attribute `children`, assume it's a group
    elif isinstance(entity, QgsLayerTreeGroup) or isinstance(entity, QgsLayerTree):
        short_name = get_group_short_name(entity)
        if short_name != "":
            # '' is the root of the tree, we dont want it to be part of the path
            path = path + [short_name]
        extract_group(
            entity,
            tree,
            datasets,
            path,
            unify_layer_names_by_group,
            types_from_editor_widget,
        )
        for child in entity.children():
            extract_entities(
                project,
                child,
                tree,
                datasets,
                path,
                unify_layer_names_by_group,
                types_from_editor_widget,
            )


def extract_metadata(project) -> MetaData:
    """Construct a JSON object from the given layers and metadata"""
    _meta = project.metadata()
    wms_entries = get_project_server_entries(project, "wms")
    service = Service(**dict(sorted({**wms_entries}.items())))
    return MetaData(
        service=service,
        author=_meta.author(),
        categories=_meta.categories(),
        creationDateTime=_meta.creationDateTime().toPyDateTime().isoformat(),
        language=_meta.language(),
        links=_meta.links(),
    )


def save_to_disk(path_to_output_dir, built):
    path_to_config_json = path.join(path_to_output_dir, "config.json")

    with open(path_to_config_json, "w") as fh:
        json.dump(built, fh, indent=2)


def get_project_root(path_to_project) -> Tuple[QgsProject, QgsLayerTree]:
    """Returns a Tuple <Project, LayerTreeRoot>."""
    project = QgsProject.instance()
    project.read(path_to_project)
    return project, project.layerTreeRoot()


def prepare_project_name(project: QgsProject) -> tuple[str, str]:
    # TODO: Find a good approach to recognize different "versions" of a project.
    name = project.baseName()
    parts = name.split(".")
    version = parts.pop(0)
    assembled_name = ".".join(parts)
    if assembled_name == "":
        assembled_name = project.title()
    return version, assembled_name


def extract(path_to_project: str, unify_layer_names_by_group=False) -> Config:
    """
    Extract the styles and configuration of the given Qgis project
    to the given output directory.
    """
    project, root = get_project_root(path_to_project)
    version, assembled_name = prepare_project_name(project)
    tree = Tree()
    datasets = Datasets()
    config = Config(
        project=Project(name=assembled_name, version=version),
        meta_data=extract_metadata(project),
        tree=tree,
        datasets=datasets,
    )
    extract_entities(project, root, tree, datasets, [], unify_layer_names_by_group)
    return config
