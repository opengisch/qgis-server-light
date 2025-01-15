import json
import os
import uuid
from base64 import urlsafe_b64encode
from os import path
from typing import List
from typing import Tuple
from typing import Union

import pgserviceparser
from PyQt5.QtXml import QDomDocument
from qgis.core import QgsLayerTree
from qgis.core import QgsLayerTreeGroup
from qgis.core import QgsLayerTreeLayer
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
from qgis_server_light.interface.qgis import Tree
from qgis_server_light.interface.qgis import TreeGroup
from qgis_server_light.interface.qgis import Vector
from qgis_server_light.interface.qgis import VectorTileSource
from qgis_server_light.interface.qgis import WfsSource
from qgis_server_light.interface.qgis import WmsSource
from qgis_server_light.interface.qgis import WmtsSource


def extract_fields(layer: QgsVectorLayer) -> List[Field]:
    fields = []
    for field in layer.fields():
        fields.append(Field(name=field.name(), type=field.typeName()))
    return fields


def create_unified_short_name(name: str, path: list[str]):
    short_name_part = path + [name]
    return ".".join(short_name_part)


def extract_save_layer(
    project: QgsProject,
    child: QgsLayerTreeLayer,
    tree: Tree,
    datasets: Datasets,
    path: list[str],
    unify_layer_names_by_group=False,
):
    """Save the given layer to the output path."""
    if isinstance(child, QgsLayerTreeLayer):
        child = child.layer()
    os.path.join("/tmp", f"{str(uuid.uuid4())}.qml")
    style_doc = QDomDocument()
    child.exportNamedStyle(style_doc)
    layer_type = get_layer_type(child)
    decoded = QgsProviderRegistry.instance().decodeUri(
        child.providerType(), child.dataProvider().dataSourceUri()
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
    if unify_layer_names_by_group:
        short_name = create_unified_short_name(child.shortName(), path)
    else:
        short_name = child.shortName()
    crs = Crs(
        postgis_srid=child.dataProvider().crs().postgisSrid(),
        auth_id=child.dataProvider().crs().authid(),
        ogc_uri=child.dataProvider().crs().toOgcUri(),
    )

    extent_wgs_84 = extent_in_wgs84(project, child)
    bbox_wgs84 = BBox(
        x_min=extent_wgs_84[0],
        x_max=extent_wgs_84[2],
        y_min=extent_wgs_84[1],
        y_max=extent_wgs_84[3],
    )
    extent = child.extent()
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
        source_path = child.source()
        if child.providerType().lower() == "ogr":
            source = DataSource(
                ogr=OgrSource(
                    path=decoded["path"],
                    layer_name=decoded["layerName"],
                    layer_id=decoded["layerId"],
                )
            )
        elif child.providerType().lower() == "postgres":
            config = decoded
            if decoded.get("service"):
                service_config = pgserviceparser.service_config(decoded["service"])
                # merging pg_service content with config of qgis project (qgis project config overwrites
                # pg_service configs
                config = service_config | decoded
            source = DataSource(
                postgres=PostgresSource(
                    dbname=config["dbname"],
                    geometry_column=config["geometrycolumn"],
                    host=config["host"],
                    key=config["key"],
                    password=config["password"],
                    port=config["port"],
                    schema=config["schema"],
                    srid=config["srid"],
                    table=config["table"],
                    type=config["type"],
                    username=config["username"],
                )
            )
            if decoded.get("service"):
                del config["service"]
            source_path = QgsProviderRegistry.instance().encodeUri(
                child.providerType(), config
            )

        elif child.providerType().lower() == "wfs":
            # TODO: Correctly implement source!
            source = WfsSource()
        else:
            raise NotImplementedError(
                f"Unknown provider type: {child.providerType().lower()}"
            )
        fields = extract_fields(child)

        datasets.vector.append(
            Vector(
                path=source_path.replace(f'{project.readPath("./")}/', ""),
                name=short_name,
                title=child.title(),
                style=urlsafe_b64encode(style_doc.toByteArray()).decode(),
                driver=child.providerType(),
                bbox_wgs84=bbox_wgs84,
                fields=fields,
                source=source,
                id=child.id(),
                crs=crs,
                bbox=bbox,
                minimum_scale=child.minimumScale(),
                maximum_scale=child.maximumScale(),
            )
        )
    elif layer_type == "raster":
        if child.providerType() == "gdal":
            source = DataSource(
                gdal=GdalSource(path=decoded["path"], layer_name=decoded["layerName"])
            )
        elif child.providerType() == "wms":
            if "tileMatrixSet" in decoded:
                source = DataSource(
                    wmts=WmtsSource(
                        contextual_wms_legend=decoded["contextualWMSLegend"],
                        crs=decoded["crs"],
                        dpi_mode=decoded["dpiMode"],
                        feature_count=decoded["featureCount"],
                        format=decoded["format"],
                        layers=decoded["layers"],
                        styles=decoded["styles"],
                        tile_dimensions=decoded["tileDimensions"],
                        tile_matrix_set=decoded["tileMatrixSet"],
                        tile_pixel_ratio=decoded["tilePixelRatio"],
                        url=decoded["url"],
                    )
                )
            else:
                source = DataSource(
                    wms=WmsSource(
                        contextual_wms_legend=decoded["contextualWMSLegend"],
                        crs=decoded["crs"],
                        dpi_mode=decoded["dpiMode"],
                        feature_count=decoded["featureCount"],
                        format=decoded["format"],
                        layers=decoded["layers"],
                        url=decoded["url"],
                    )
                )
        else:
            raise NotImplementedError(
                f"Unknown provider type: {child.providerType().lower()}"
            )
        datasets.raster.append(
            Raster(
                path=child.source().replace(f'{project.readPath("./")}/', ""),
                name=short_name,
                title=child.title(),
                style=urlsafe_b64encode(style_doc.toByteArray()).decode(),
                driver=child.providerType(),
                bbox_wgs84=bbox_wgs84,
                source=source,
                id=child.id(),
                crs=crs,
                bbox=bbox,
                minimum_scale=child.minimumScale(),
                maximum_scale=child.maximumScale(),
            )
        )
    elif layer_type == "custom":
        if child.providerType().lower() == "xyzvectortiles":
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
                f"Unknown provider type: {child.providerType().lower()}"
            )
            # TODO: make this more configurable
        datasets.custom.append(
            Custom(
                path=child.source().replace(f'{project.readPath("./")}/', ""),
                name=short_name,
                title=child.title(),
                style=urlsafe_b64encode(style_doc.toByteArray()).decode(),
                driver=child.providerType(),
                bbox_wgs84=bbox_wgs84,
                source=source,
                id=child.id(),
                crs=crs,
                bbox=bbox,
                minimum_scale=child.minimumScale(),
                maximum_scale=child.maximumScale(),
            )
        )
    else:
        raise NotImplementedError(f'Unknown layer_type "{layer_type}"')


def extract_group(
    group: QgsLayerTreeGroup,
    tree: Tree,
    datasets: Datasets,
    path: list[str],
    unify_layer_names_by_group=False,
):
    """Collects data pertaining to a QGIS layer tree group."""
    children = []
    for child in group.children():
        if isinstance(child, QgsLayerTreeGroup):
            children.append(child.customProperty("wmsShortName"))
        else:
            if unify_layer_names_by_group:
                children.append(
                    create_unified_short_name(child.layer().shortName(), path)
                )
            else:
                children.append(child.layer().shortName())
    tree.members.append(
        TreeGroup(name=group.customProperty("wmsShortName"), children=children)
    )
    datasets.group.append(
        Group(
            name=group.customProperty("wmsShortName"),
            title=group.customProperty("wmsTitle"),
        )
    )


def extract_entities(
    project: QgsProject,
    entity: Union[QgsLayerTree, QgsLayerTreeGroup, QgsLayerTreeLayer],
    tree: Tree,
    datasets: Datasets,
    path: list[str],
    unify_layer_names_by_group=False,
):
    if isinstance(entity, QgsLayerTreeLayer):
        extract_save_layer(
            project, entity, tree, datasets, path, unify_layer_names_by_group
        )

    # If the entity has an attribute `children`, assume it's a group
    elif isinstance(entity, QgsLayerTreeGroup) or isinstance(entity, QgsLayerTree):
        if entity.customProperty("wmsShortName") is not None:
            path = path + [entity.customProperty("wmsShortName")]
        extract_group(entity, tree, datasets, path, unify_layer_names_by_group)
        for child in entity.children():
            extract_entities(
                project, child, tree, datasets, path, unify_layer_names_by_group
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
