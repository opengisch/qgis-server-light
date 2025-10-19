""" This module contains all interface definition to translate from QGIS project to QGIS-Server-Light logic
and to write the JSON export of the QGIS project

"""
import logging
from abc import ABC
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from datetime import UTC
from datetime import datetime
from typing import List
from typing import Optional

from qgis_server_light.interface.common import BaseInterface


@dataclass(repr=False)
class BBox(BaseInterface):
    x_min: float = field(metadata={"type": "Element"})
    x_max: float = field(metadata={"type": "Element"})
    y_min: float = field(metadata={"type": "Element"})
    y_max: float = field(metadata={"type": "Element"})
    z_min: Optional[float] = field(default=0.0, metadata={"type": "Element"})
    z_max: Optional[float] = field(default=0.0, metadata={"type": "Element"})

    def to_list(self) -> list:
        return [self.x_min, self.y_min, self.z_min, self.x_max, self.y_max, self.z_max]

    def to_string(self) -> str:
        return ",".join([str(item) for item in self.to_list()])

    def to_2d_list(self) -> list:
        return [self.x_min, self.y_min, self.x_max, self.y_max]

    def to_2d_string(self) -> str:
        return ",".join([str(item) for item in self.to_2d_list()])

    @staticmethod
    def from_string(bbox_string: str) -> "BBox":
        """
        Takes a CSV string representation of a BBox in the form:
            '<x_min>,<y_min>,<x_max>,<y_max>' or
            '<x_min>,<y_min>,<z_min>,<x_max>,<y_max>,<z_max>'
        """
        coordinates = bbox_string.split(",")
        if len(coordinates) == 4:
            return BBox(
                x_min=float(coordinates[0]),
                y_min=float(coordinates[1]),
                x_max=float(coordinates[2]),
                y_max=float(coordinates[3]),
            )
        elif len(coordinates) == 6:
            return BBox(
                x_min=float(coordinates[0]),
                y_min=float(coordinates[1]),
                z_min=float(coordinates[2]),
                x_max=float(coordinates[3]),
                y_max=float(coordinates[4]),
                z_max=float(coordinates[5]),
            )
        else:
            raise ValueError(f"Invalid bbox string: {bbox_string}")

    @staticmethod
    def from_list(bbox_list: List[float]) -> "BBox":
        """
        Takes a list representation of a BBox in the form:
            [<x_min>,<y_min>,<x_max>,<y_max>] or
            [<x_min>,<y_min>,<z_min>,<x_max>,<y_max>,<z_max>]
        """
        if len(bbox_list) == 4:
            return BBox(
                x_min=bbox_list[0],
                y_min=bbox_list[1],
                x_max=bbox_list[3],
                y_max=bbox_list[4],
            )
        elif len(bbox_list) == 6:
            return BBox(
                x_min=bbox_list[0],
                y_min=bbox_list[1],
                z_min=bbox_list[2],
                x_max=bbox_list[3],
                y_max=bbox_list[4],
                z_max=bbox_list[5],
            )
        else:
            raise ValueError(f"Invalid bbox list: {bbox_list}")


@dataclass(repr=False)
class LayerLike(BaseInterface):
    id: str = field(metadata={"type": "Element"})
    name: str = field(metadata={"type": "Element"})


@dataclass(repr=False)
class TreeLayer(LayerLike):
    pass


@dataclass(repr=False)
class TreeGroup(TreeLayer):
    children: List[str] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )


@dataclass(repr=False)
class Field(BaseInterface):
    """
    Transportable (serializable) form of a QGIS vector layer fiel (attribute). It contains the information of
    the original data datatype and its translated versions and the editor widget one as well.

    Attributes:
        name: Machine readable name of the field
        type: Original type as defined by data source (PostGIS, GPKG, etc.)
        is_primary_key: if the field is considered to be primary key.
        type_wfs: Translated type for further usage. Based on the simple types of
            [XSD spec](https://www.w3.org/TR/xmlschema11-2/#built-in-primitive-datatypes).
        type_oapif: Translated type based on the types of the
            [OpenAPI Spec](https://spec.openapis.org/oas/latest.html#data-types)
        type_oapif_format: Format of the above-mentioned type based on the
            [OpenAPI Spec](https://spec.openapis.org/oas/latest.html#data-types)
        alias: Human readable name.
        comment: Field description.
        nullable: If this field can be NULL or not.
        length: The limitation in length on the field value.
        precision: The precision of the field value (float types)
        editor_widget_type: The original type how it is defined in the QGIS form.
        editor_widget_type_wfs: The translated type based on the simple types of
            [XSD spec](https://www.w3.org/TR/xmlschema11-2/#built-in-primitive-datatypes).
        editor_widget_type_oapif: Translated type based on the types of the
            [OpenAPI Spec](https://spec.openapis.org/oas/latest.html#data-types)
        editor_widget_type_oapif_format: Format of the above-mentioned type based on the
            [OpenAPI Spec](https://spec.openapis.org/oas/latest.html#data-types)
    """

    name: str = field(metadata={"type": "Element"})
    type: str = field(metadata={"type": "Element"})
    is_primary_key: bool = field(
        default=False,
        metadata={"type": "Element"},
    )
    type_wfs: Optional[str] = field(default=None, metadata={"type": "Element"})
    type_oapif: Optional[str] = field(default=None, metadata={"type": "Element"})
    type_oapif_format: Optional[str] = field(default=None, metadata={"type": "Element"})
    alias: Optional[str] = field(default=None, metadata={"type": "Element"})
    comment: Optional[str] = field(default=None, metadata={"type": "Element"})
    nullable: bool = field(default=True, metadata={"type": "Element"})
    length: Optional[int] = field(default=None, metadata={"type": "Element"})
    precision: Optional[int] = field(default=None, metadata={"type": "Element"})
    editor_widget_type: Optional[str] = field(
        default=None, metadata={"type": "Element"}
    )
    editor_widget_type_wfs: Optional[str] = field(
        default=None, metadata={"type": "Element"}
    )
    editor_widget_type_oapif: Optional[str] = field(
        default=None, metadata={"type": "Element"}
    )
    editor_widget_type_oapif_format: Optional[str] = field(
        default=None, metadata={"type": "Element"}
    )


@dataclass(repr=False)
class AbstractDataset(LayerLike):
    title: str = field(metadata={"type": "Element"})


@dataclass(repr=False)
class Crs(BaseInterface):
    auth_id: str = field(default=None, metadata={"type": "Element"})
    postgis_srid: int = field(
        default=None,
        metadata={"type": "Element"},
    )
    ogc_uri: str = field(default=None, metadata={"type": "Element"})
    ogc_urn: str = field(default=None, metadata={"type": "Element"})


@dataclass(repr=False)
class Style(BaseInterface):
    name: str = field(metadata={"type": "Element"})
    definition: str = field(metadata={"type": "Element"})

    @property
    def shortened_fields(self) -> set:
        return {"definition"}


@dataclass(repr=False)
class Source(BaseInterface, ABC):
    @staticmethod
    def decide_remote(path: str) -> bool:
        return path.startswith("http")

    @property
    def to_qgis_decoded_uri(self) -> dict:
        raise NotImplementedError(
            "This is a base class, the method has to be defined at implementation level."
        )

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        raise NotImplementedError(
            "This is a base class, the method has to be defined at implementation level."
        )


@dataclass(repr=False)
class GdalSource(Source):
    path: str = field(metadata={"type": "Element"})
    layer_name: str | None = field(default=None, metadata={"type": "Element"})
    vsi_prefix: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def remote(self):
        return self.decide_remote(self.path)

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = {"path": self.path}
        if self.layer_name is not None:
            connection_dict["layerName"] = self.layer_name
        if self.vsi_prefix is not None:
            connection_dict["vsiPrefix"] = self.vsi_prefix
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        return cls(
            path=decoded_uri["path"],
            layer_name=decoded_uri.get("layerName"),
            vsi_prefix=decoded_uri.get("vsiPrefix"),
        )


@dataclass(repr=False)
class OgrSource(GdalSource):
    layer_id: str | None = field(default=None, metadata={"type": "Element"})
    subset: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = super().to_qgis_decoded_uri
        if self.layer_id:
            connection_dict["layerId"] = self.layer_id
        if self.subset:
            connection_dict["subset"] = self.subset
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        base_class_instance = GdalSource.from_qgis_decoded_uri(decoded_uri)
        return cls(
            path=base_class_instance.path,
            layer_name=base_class_instance.layer_name,
            vsi_prefix=base_class_instance.vsi_prefix,
            layer_id=decoded_uri.get("layerId"),
            subset=decoded_uri.get("subset"),
        )

    @property
    def encoded_uri_separator(self) -> str:
        return "|"


@dataclass(repr=False)
class WfsSource(BaseInterface):
    # currently not implemented because qgis does not allow to
    # use the decode uri approach on that URI
    pass


@dataclass(repr=False)
class XYZSource(Source):
    url: str = field(metadata={"type": "Element"})
    zmin: int | None = field(default=None, metadata={"type": "Element"})
    zmax: int | None = field(default=None, metadata={"type": "Element"})
    type: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = {
            "url": self.url,
            "zmin": self.zmin,
            "zmax": self.zmax,
            "type": self.type,
        }
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        return cls(
            url=decoded_uri["url"],
            zmin=decoded_uri.get("zmin"),
            zmax=decoded_uri.get("zmax"),
            type=decoded_uri.get("type"),
        )


@dataclass(repr=False)
class WmsSource(Source):
    crs: str = field(metadata={"type": "Element"})
    format: str = field(metadata={"type": "Element"})
    layers: str = field(metadata={"type": "Element"})
    url: str = field(metadata={"type": "Element"})
    dpi_mode: str | None = field(default=None, metadata={"type": "Element"})
    feature_count: int | None = field(default=None, metadata={"type": "Element"})
    contextual_wms_legend: str | None = field(
        default=None, metadata={"type": "Element"}
    )
    styles: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = {
            "crs": self.crs,
            "format": self.format,
            "layers": self.layers,
            "url": self.url,
        }
        if self.dpi_mode is not None:
            connection_dict["dpiMode"] = self.dpi_mode
        if self.feature_count is not None:
            connection_dict["featureCount"] = self.feature_count
        if self.contextual_wms_legend is not None:
            connection_dict["contextualWMSLegend"] = self.contextual_wms_legend
        if self.styles is not None:
            connection_dict["styles"] = self.styles
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        return cls(
            crs=decoded_uri["crs"],
            format=decoded_uri["format"],
            layers=decoded_uri["layers"],
            url=decoded_uri["url"],
            dpi_mode=decoded_uri.get("dpiMode"),
            feature_count=decoded_uri.get("featureCount"),
            contextual_wms_legend=decoded_uri.get("contextualWMSLegend"),
            styles=decoded_uri.get("styles"),
        )


@dataclass(repr=False, kw_only=True)
class WmtsSource(WmsSource):
    tile_matrix_set: str = field(metadata={"type": "Element"})
    tile_dimensions: str | None = field(
        default=None,
        metadata={"type": "Element"},
    )
    tile_pixel_ratio: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = super().to_qgis_decoded_uri
        connection_dict["tileMatrixSet"] = self.tile_matrix_set
        if self.tile_dimensions is not None:
            connection_dict["tileDimensions"] = self.tile_dimensions
        if self.tile_pixel_ratio is not None:
            connection_dict["tilePixelRatio"] = self.tile_pixel_ratio
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        base_class_instance = WmsSource.from_qgis_decoded_uri(decoded_uri)
        return cls(
            crs=base_class_instance.crs,
            format=base_class_instance.format,
            layers=base_class_instance.layers,
            url=base_class_instance.url,
            dpi_mode=base_class_instance.dpi_mode,
            feature_count=base_class_instance.feature_count,
            contextual_wms_legend=base_class_instance.contextual_wms_legend,
            styles=base_class_instance.styles,
            tile_matrix_set=decoded_uri["tileMatrixSet"],
            tile_dimensions=decoded_uri.get("tileDimensions"),
            tile_pixel_ratio=decoded_uri.get("tilePixelRatio"),
        )


@dataclass(repr=False)
class PostgresSource(Source):
    key: str = field(metadata={"type": "Element"})
    schema: str = field(metadata={"type": "Element"})
    table: str = field(metadata={"type": "Element"})
    geometry_column: str | None = field(default=None, metadata={"type": "Element"})
    dbname: str | None = field(default=None, metadata={"type": "Element"})
    host: str | None = field(default=None, metadata={"type": "Element"})
    password: str | None = field(default=None, metadata={"type": "Element"})
    port: int | None = field(default=None, metadata={"type": "Element"})
    type: int | None = field(default=None, metadata={"type": "Element"})
    username: str | None = field(default=None, metadata={"type": "Element"})
    srid: str | None = field(default=None, metadata={"type": "Element"})
    sslmode: int | None = field(default=None, metadata={"type": "Element"})
    ssl_mode_text: str | None = field(default=None, metadata={"type": "Element"})
    service: str | None = field(default=None, metadata={"type": "Element"})
    check_primary_key_unicity: str | None = field(
        default=None, metadata={"type": "Element"}
    )
    sql: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def redacted_fields(self) -> set:
        return {"password"}

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = {"key": self.key, "schema": self.schema, "table": self.table}
        if self.geometry_column is not None:
            connection_dict["geometrycolumn"] = self.geometry_column
        if self.dbname is not None:
            connection_dict["dbname"] = self.dbname
        if self.host is not None:
            connection_dict["host"] = self.host
        if self.password is not None:
            connection_dict["password"] = self.password
        if self.port is not None:
            connection_dict["port"] = self.port
        if self.type is not None:
            connection_dict["type"] = self.type
        if self.username is not None:
            connection_dict["username"] = self.username
        if self.srid is not None:
            connection_dict["srid"] = self.srid
        if self.sslmode is not None:
            connection_dict["sslmode"] = self.sslmode
        if self.service is not None:
            connection_dict["service"] = self.service
        if self.check_primary_key_unicity is not None:
            connection_dict["checkPrimaryKeyUnicity"] = self.check_primary_key_unicity
        if self.sql is not None:
            connection_dict["sql"] = self.sql
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        return cls(
            key=decoded_uri["key"],
            schema=decoded_uri["schema"],
            table=decoded_uri["table"],
            geometry_column=decoded_uri.get("geometrycolumn"),
            dbname=decoded_uri.get("dbname"),
            host=decoded_uri.get("host"),
            password=decoded_uri.get("password"),
            port=int(decoded_uri.get("port"))
            if decoded_uri.get("port") is not None
            else None,
            type=int(decoded_uri.get("type"))
            if decoded_uri.get("type") is not None
            else None,
            username=decoded_uri.get("username"),
            srid=decoded_uri.get("srid"),
            sslmode=int(decoded_uri.get("sslmode", 2)),
            service=decoded_uri.get("service"),
            check_primary_key_unicity=decoded_uri.get("check_primary_key_unicity"),
            sql=decoded_uri.get("sql"),
        )


@dataclass(repr=False)
class VectorTileSource(Source):

    type: str = field(metadata={"type": "Element"})
    zmin: int | None = field(metadata={"type": "Element"})
    zmax: int | None = field(metadata={"type": "Element"})
    url: str | None = field(default=None, metadata={"type": "Element"})
    path: str | None = field(default=None, metadata={"type": "Element"})
    style_url: str | None = field(default=None, metadata={"type": "Element"})

    @property
    def remote(self):
        return self.decide_remote(self.url)

    @property
    def to_qgis_decoded_uri(self) -> dict:
        connection_dict = {"type": self.type, "zmin": self.zmin, "zmax": self.zmax}
        if self.url is not None:
            connection_dict["url"] = self.url
        if self.path is not None:
            connection_dict["path"] = self.path
        if self.style_url is not None:
            connection_dict["styleUrl"] = self.style_url
        return connection_dict

    @classmethod
    def from_qgis_decoded_uri(cls, decoded_uri: dict):
        return cls(
            type=decoded_uri["type"],
            zmin=decoded_uri.get("zmin"),
            zmax=decoded_uri.get("zmax"),
            url=decoded_uri.get("url"),
            path=decoded_uri.get("path"),
            style_url=decoded_uri.get("styleUrl"),
        )


@dataclass(repr=False)
class DataSource(BaseInterface):
    postgres: PostgresSource | None = field(default=None, metadata={"type": "Element"})
    wmts: WmtsSource | None = field(default=None, metadata={"type": "Element"})
    wms: WmsSource | None = field(default=None, metadata={"type": "Element"})
    ogr: OgrSource | None = field(default=None, metadata={"type": "Element"})
    gdal: GdalSource | None = field(default=None, metadata={"type": "Element"})
    wfs: WfsSource | None = field(default=None, metadata={"type": "Element"})
    vector_tile: VectorTileSource | None = field(
        default=None, metadata={"type": "Element"}
    )
    xyz: XYZSource | None = field(default=None, metadata={"type": "Element"})

    @property
    def definition(
        self,
    ) -> PostgresSource | WmtsSource | WmsSource | OgrSource | GdalSource | WfsSource | VectorTileSource | XYZSource | None:
        for dataclass_field in fields(self):
            name = dataclass_field.name
            value = getattr(self, name)
            if value:
                return value
        logging.error(
            f"No source was definied at {self.__class__.__name__}, this is not expected"
        )
        return None


@dataclass(repr=False)
class DataSet(AbstractDataset):
    id: str = field(metadata={"type": "Element"})
    source: DataSource = field(metadata={"type": "Element"})
    driver: str = field(metadata={"type": "Element"})
    bbox: BBox | None = field(default=None, metadata={"type": "Element"})
    bbox_wgs84: BBox | None = field(default=None, metadata={"type": "Element"})
    crs: Crs | None = field(default=None, metadata={"type": "Element"})
    styles: List[Style] = field(default_factory=list, metadata={"type": "Element"})
    minimum_scale: float | None = field(default=None, metadata={"type": "Element"})
    maximum_scale: float | None = field(default=None, metadata={"type": "Element"})
    style_name: str = field(default="default", metadata={"type": "Element"})
    is_spatial: bool = field(default=True, metadata={"type": "Element"})

    def get_style_by_name(self, name: str) -> Style | None:
        for style in self.styles:
            if name == style.name:
                return style
        return None

    def style(self) -> Style | None:
        return self.get_style_by_name(self.style_name)


@dataclass(repr=False)
class Raster(DataSet):
    """
    A real QGIS Raster dataset. That are usually all `QgsRasterLayer` (in opposition to `QgsVectorTileLayer`
    which is not a real `QgsRasterLayer`.
    """


@dataclass(repr=False)
class Vector(DataSet):
    """
    A real QGIS Vector dataset. That are usually all `QgsVectorLayer` (in opposition to `QgsVectorTileLayer`
    which is not a real `QgsVectorLayer`.
    """

    fields: Optional[List[Field]] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
    geometry_type_simple: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    geometry_type_wkb: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )

    def get_field_by_name(self, name: str) -> Field | None:
        for dataclass_field in self.fields:
            if dataclass_field.name == name:
                return dataclass_field
        return None


@dataclass(repr=False)
class Custom(DataSet):
    pass


@dataclass(repr=False)
class Group(AbstractDataset):
    pass


@dataclass(repr=False)
class Service(BaseInterface):
    contact_organization: Optional[str] = field(metadata={"type": "Element"})
    contact_mail: Optional[str] = field(metadata={"type": "Element"})
    contact_person: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    contact_phone: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    contact_position: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    fees: Optional[str] = field(default=None, metadata={"type": "Element"})
    keyword_list: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    online_resource: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    service_abstract: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    service_title: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    resource_url: Optional[str] = field(default=None, metadata={"type": "Element"})


@dataclass(repr=False)
class MetaData(BaseInterface):
    service: Service = field(metadata={"type": "Element"})
    links: Optional[List[str]] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
    language: Optional[str] = field(
        default=None,
        metadata={"type": "Element"},
    )
    categories: Optional[List[str]] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
    creationDateTime: str = field(
        default=None,
        metadata={"type": "Element"},
    )
    author: Optional[str] = field(default=None, metadata={"type": "Element"})

    def __post_init__(self):
        if self.creationDateTime is None:
            self.creationDateTime = datetime.now(UTC).isoformat()


@dataclass(repr=False)
class Project(BaseInterface):
    version: str = field(metadata={"type": "Element"})
    name: str = field(metadata={"type": "Element"})


@dataclass(repr=False)
class Tree(BaseInterface):
    members: list[TreeGroup] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )

    def find_by_name(self, name: str) -> TreeGroup | None:
        for member in self.members:
            if member.name == name:
                return member
        return None


@dataclass(repr=False)
class Datasets(BaseInterface):
    vector: list[Vector] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
    raster: list[Raster] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
    custom: list[Custom] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )
    group: list[Group] = field(
        default_factory=list,
        metadata={"type": "Element"},
    )


@dataclass(repr=False)
class Config(BaseInterface):
    project: Project = field(metadata={"type": "Element"})
    meta_data: MetaData = field(metadata={"type": "Element"})
    tree: Tree = field(metadata={"type": "Element"})
    datasets: Datasets = field(metadata={"type": "Element"})
