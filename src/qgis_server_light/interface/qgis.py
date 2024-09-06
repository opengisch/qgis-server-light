from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import List
from typing import Optional


@dataclass
class BBox:
    x_min: float = field(metadata={"name": "XMin", "type": "Element", "required": True})
    x_max: float = field(metadata={"name": "XMax", "type": "Element", "required": True})
    y_min: float = field(metadata={"name": "YMin", "type": "Element", "required": True})
    y_max: float = field(metadata={"name": "YMax", "type": "Element", "required": True})
    z_min: Optional[float] = field(
        default=0.0, metadata={"name": "ZMin", "type": "Element", "required": False}
    )
    z_max: Optional[float] = field(
        default=0.0, metadata={"name": "ZMax", "type": "Element", "required": False}
    )

    def to_list(self) -> list:
        return [self.x_min, self.y_min, self.z_min, self.x_max, self.y_max, self.z_max]

    def to_string(self) -> str:
        return ",".join([str(item) for item in self.to_list()])

    @staticmethod
    def from_string(bbox_string: str) -> "BBox":
        """
        Takes a CSV string representation of a BBox in the form:
            '<x_min>,<y_min>,<z_min>,<x_max>,<y_max>,<z_max>'
        """
        coordinates = bbox_string.split(",")
        return BBox(
            x_min=float(coordinates[0]),
            y_min=float(coordinates[1]),
            z_min=float(coordinates[2]),
            x_max=float(coordinates[3]),
            y_max=float(coordinates[4]),
            z_max=float(coordinates[5]),
        )

    @staticmethod
    def from_list(bbox_list: List[float]) -> "BBox":
        """
        Takes a list representation of a BBox in the form:
            [<x_min>,<y_min>,<z_min>,<x_max>,<y_max>,<z_max>]
        """
        return BBox(
            x_min=bbox_list[0],
            y_min=bbox_list[1],
            z_min=bbox_list[2],
            x_max=bbox_list[3],
            y_max=bbox_list[4],
            z_max=bbox_list[5],
        )


@dataclass
class LayerLike:
    name: str = field(metadata={"name": "Name", "type": "Element", "required": True})


@dataclass
class TreeLayer(LayerLike):
    pass


@dataclass
class TreeGroup(TreeLayer):
    children: List[str] = field(
        default_factory=list,
        metadata={"name": "Child", "type": "Element", "required": False},
    )


@dataclass
class Field:
    name: str = field(metadata={"name": "Name", "type": "Element", "required": True})
    type: str = field(metadata={"name": "Type", "type": "Element", "required": True})


@dataclass
class AbstractDataset(LayerLike):
    title: str = field(metadata={"name": "Title", "type": "Element", "required": True})


@dataclass
class Source:
    pass


@dataclass
class GdalSource(Source):
    path: str = field(metadata={"name": "Path", "type": "Element", "required": True})
    layer_name: Optional[str] = field(
        default=None,
        metadata={"name": "LayerName", "type": "Element", "required": False},
    )

    @property
    def remote(self):
        return self.path.startswith("http")


@dataclass
class OgrSource(GdalSource):
    layer_id: Optional[str] = field(
        default=None, metadata={"name": "LayerId", "type": "Element", "required": False}
    )


@dataclass
class WfsSource:
    # currently not implemented because qgis does not allow to
    # use the decode uri approach on that URI
    pass


@dataclass
class WmsSource(Source):
    contextual_wms_legend: str = field(
        metadata={"name": "ContextualWMSLegend", "type": "Element", "required": True}
    )
    crs: str = field(metadata={"name": "Crs", "type": "Element", "required": True})
    dpi_mode: str = field(
        metadata={"name": "DpiMode", "type": "Element", "required": True}
    )
    feature_count: int = field(
        metadata={"name": "FeatureCount", "type": "Element", "required": True}
    )
    format: str = field(
        metadata={"name": "Format", "type": "Element", "required": True}
    )
    layers: str = field(
        metadata={"name": "Layers", "type": "Element", "required": True}
    )
    url: str = field(metadata={"name": "Url", "type": "Element", "required": True})


@dataclass
class WmtsSource(WmsSource):
    styles: str = field(
        metadata={"name": "Styles", "type": "Element", "required": True}
    )
    tile_dimensions: str = field(
        metadata={"name": "TileDimensions", "type": "Element", "required": True}
    )
    tile_matrix_set: str = field(
        metadata={"name": "TileMatrixSet", "type": "Element", "required": True}
    )
    tile_pixel_ratio: str = field(
        metadata={"name": "TilePixelRatio", "type": "Element", "required": True}
    )


@dataclass
class PostgresSource(Source):
    dbname: str = field(
        metadata={"name": "Dbname", "type": "Element", "required": True}
    )
    geometry_column: str = field(
        metadata={"name": "GeometryColumn", "type": "Element", "required": True}
    )
    host: str = field(metadata={"name": "Host", "type": "Element", "required": True})
    key: str = field(metadata={"name": "Key", "type": "Element", "required": True})
    password: str = field(
        metadata={"name": "Password", "type": "Element", "required": True}
    )
    port: str = field(metadata={"name": "Port", "type": "Element", "required": True})
    schema: str = field(
        metadata={"name": "Schema", "type": "Element", "required": True}
    )
    srid: str = field(metadata={"name": "Srid", "type": "Element", "required": True})
    table: str = field(metadata={"name": "Table", "type": "Element", "required": True})
    type: str = field(metadata={"name": "Type", "type": "Element", "required": True})
    username: str = field(
        metadata={"name": "Username", "type": "Element", "required": True}
    )


@dataclass
class VectorTileSource(Source):
    styleUrl: str = field(
        metadata={"name": "styleUrl", "type": "Element", "required": True}
    )
    type: str = field(metadata={"name": "Type", "type": "Element", "required": True})
    url: str = field(metadata={"name": "Url", "type": "Element", "required": True})
    zmax: str = field(metadata={"name": "Zmax", "type": "Element", "required": True})
    zmin: str = field(metadata={"name": "Zmin", "type": "Element", "required": True})

    @property
    def remote(self):
        return self.url.startswith("http")


@dataclass
class Crs:
    auth_id: str = field(
        default=None, metadata={"name": "AuthId", "type": "Element", "required": False}
    )
    postgis_srid: int = field(
        default=None,
        metadata={"name": "PostgisSrid", "type": "Element", "required": False},
    )
    ogc_uri: str = field(
        default=None, metadata={"name": "OgcUri", "type": "Element", "required": False}
    )


@dataclass
class DataSource:
    postgres: PostgresSource = field(
        default=None,
        metadata={"name": "Postgres", "type": "Element", "required": False},
    )
    wmts: WmtsSource = field(
        default=None, metadata={"name": "Wmts", "type": "Element", "required": False}
    )
    wms: WmsSource = field(
        default=None, metadata={"name": "Wms", "type": "Element", "required": False}
    )
    ogr: OgrSource = field(
        default=None, metadata={"name": "Ogr", "type": "Element", "required": False}
    )
    gdal: GdalSource = field(
        default=None, metadata={"name": "Gdal", "type": "Element", "required": False}
    )
    wfs: WfsSource = field(
        default=None, metadata={"name": "Wfs", "type": "Element", "required": False}
    )
    vector_tile: VectorTileSource = field(
        default=None,
        metadata={"name": "VectorTile", "type": "Element", "required": False},
    )


@dataclass
class DataSet(AbstractDataset):
    id: str = field(metadata={"name": "Id", "type": "Element", "required": False})
    bbox: BBox = field(metadata={"name": "BBox", "type": "Element", "required": True})
    bbox_wgs84: BBox = field(
        metadata={"name": "BBoxWgs84", "type": "Element", "required": True}
    )
    path: str = field(metadata={"name": "Path", "type": "Element", "required": True})
    source: DataSource = field(
        metadata={"name": "Source", "type": "Element", "required": True}
    )
    driver: str = field(
        metadata={"name": "Driver", "type": "Element", "required": True}
    )
    crs: Crs = field(metadata={"name": "Crs", "type": "Element", "required": True})
    style: Optional[str] = field(
        default=None, metadata={"name": "Style", "type": "Element", "required": True}
    )


@dataclass
class Raster(DataSet):
    """
    A real QGIS Raster dataset. That are usually all `QgsRasterLayer` (in opposition to `QgsVectorTileLayer`
    which is not a real `QgsRasterLayer`.
    """


@dataclass
class Vector(DataSet):
    """
    A real QGIS Vector dataset. That are usually all `QgsVectorLayer` (in opposition to `QgsVectorTileLayer`
    which is not a real `QgsVectorLayer`.
    """

    fields: Optional[List[Field]] = field(
        default_factory=list,
        metadata={"name": "Fields", "type": "Element", "required": True},
    )


@dataclass
class Custom(DataSet):
    pass


@dataclass
class Group(AbstractDataset):
    pass


@dataclass
class Contact:
    mail: str
    organization: str
    person: str
    phone: str
    position: str
    url: str


@dataclass
class Service:
    contact_organization: Optional[str] = field(
        metadata={"name": "WMSContactOrganization", "type": "Element", "required": True}
    )
    contact_mail: Optional[str] = field(
        metadata={"name": "WMSContactMail", "type": "Element", "required": True}
    )
    contact_person: Optional[str] = field(
        default=None,
        metadata={"name": "WMSContactPerson", "type": "Element", "required": False},
    )
    contact_phone: Optional[str] = field(
        default=None,
        metadata={"name": "WMSContactPhone", "type": "Element", "required": False},
    )
    contact_position: Optional[str] = field(
        default=None,
        metadata={"name": "WMSContactPosition", "type": "Element", "required": False},
    )
    fees: Optional[str] = field(
        default=None, metadata={"name": "WMSFees", "type": "Element", "required": False}
    )
    keyword_list: Optional[str] = field(
        default=None,
        metadata={"name": "WMSKeywordList", "type": "Element", "required": False},
    )
    online_resource: Optional[str] = field(
        default=None,
        metadata={"name": "WMSOnlineResource", "type": "Element", "required": False},
    )
    service_abstract: Optional[str] = field(
        default=None,
        metadata={"name": "WMSServiceAbstract", "type": "Element", "required": False},
    )
    service_title: Optional[str] = field(
        default=None,
        metadata={"name": "WMSServiceTitle", "type": "Element", "required": False},
    )
    resource_url: Optional[str] = field(
        default=None, metadata={"name": "WMSUrl", "type": "Element", "required": False}
    )


@dataclass
class MetaData:
    service: Service = field(
        metadata={"name": "Service", "type": "Element", "required": True}
    )
    links: Optional[List[str]] = field(
        default_factory=list,
        metadata={"name": "Links", "type": "Element", "required": False},
    )
    language: Optional[str] = field(
        default=None,
        metadata={"name": "Language", "type": "Element", "required": False},
    )
    categories: Optional[List[str]] = field(
        default_factory=list,
        metadata={"name": "Categories", "type": "Element", "required": False},
    )
    creationDateTime: datetime = field(
        default_factory=datetime.utcnow,
        metadata={"name": "CreationDateTime", "type": "Element", "required": False},
    )
    author: Optional[Contact] = field(
        default=None, metadata={"name": "Author", "type": "Element", "required": False}
    )


@dataclass
class Project:
    version: str = field(
        metadata={"name": "Version", "type": "Element", "required": True}
    )
    name: str = field(metadata={"name": "Name", "type": "Element", "required": True})


@dataclass
class Tree:
    members: list[TreeGroup] = field(
        default_factory=list,
        metadata={"name": "Memeber", "type": "Element", "required": False},
    )

    def find_by_name(self, name: str) -> TreeGroup | None:
        for member in self.members:
            if member.name == name:
                return member


@dataclass
class Datasets:
    vector: list[Vector] = field(
        default_factory=list,
        metadata={"name": "VectorDataset", "type": "Element", "required": False},
    )
    raster: list[Raster] = field(
        default_factory=list,
        metadata={"name": "RasterDataset", "type": "Element", "required": False},
    )
    custom: list[Custom] = field(
        default_factory=list,
        metadata={"name": "Custom", "type": "Element", "required": False},
    )
    group: list[Group] = field(
        default_factory=list,
        metadata={"name": "GroupDataset", "type": "Element", "required": False},
    )


@dataclass
class Config:
    project: Project = field(
        metadata={"name": "Project", "type": "Element", "required": True}
    )
    meta_data: MetaData = field(
        metadata={"name": "MetaData", "type": "Element", "required": True}
    )
    tree: Tree = field(metadata={"name": "Tree", "type": "Element"})
    datasets: Datasets = field(metadata={"name": "DataSet", "type": "Element"})
