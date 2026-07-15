import logging
import re
import unicodedata
import zlib
from base64 import urlsafe_b64encode
from dataclasses import fields
from functools import reduce
from itertools import zip_longest

from PyQt5.QtCore import QMetaType
from PyQt5.QtXml import QDomDocument
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDataSourceUri,
    QgsDateTimeFieldFormatter,
    QgsField,
    QgsFieldConstraints,
    QgsLayerTree,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsLayerTreeNode,
    QgsMapLayer,
    QgsMeshLayer,
    QgsPointCloudLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsRectangle,
    QgsTiledSceneLayer,
    QgsVectorLayer,
    QgsVectorTileLayer,
)
from xsdata.formats.dataclass.serializers import DictEncoder

from qgis_server_light.interface.common import BBox, Style
from qgis_server_light.interface.exporter.extract import (
    Config,
    Crs,
    Custom,
    Datasets,
    DataSource,
    Field,
    GdalSource,
    Group,
    MetaData,
    OgrSource,
    PostgresSource,
    Project,
    Raster,
    Service,
    Tree,
    TreeGroup,
    Vector,
    VectorTileSource,
    WfsSource,
    WmsSource,
    WmtsSource,
    XYZSource,
)


class Exporter:
    def __init__(
        self,
        qgis_project_path: str,
        unify_layer_names_by_group=False,
        unify_layer_names_by_group_separator=".",
        pg_service_configs=None,
    ):
        self.unify_layer_names_by_group_separator = unify_layer_names_by_group_separator
        self.path = qgis_project_path
        self.unify_layer_names_by_group = unify_layer_names_by_group
        self.pg_service_configs = pg_service_configs or {}

        # prepare QGIS instances
        self.qgis_project = self.open_qgis_project(qgis_project_path)
        self.qgis_project_tree_root = self.qgis_project.layerTreeRoot()
        self.name = self.prepare_qgis_project_name(self.qgis_project)
        self.version = self.qgis_project.lastSaveVersion().text()

        # prepare QSL interface instances
        self.qsl_tree = Tree()
        self.qsl_datasets = Datasets()
        self.qsl_project = Project(name=self.name, version=self.version)
        self.qsl_project_metadata = self.extract_metadata(self.qgis_project)
        self.qsl_config = Config(
            project=self.qsl_project,
            meta_data=self.qsl_project_metadata,
            tree=self.qsl_tree,
            datasets=self.qsl_datasets,
        )

    def run(self) -> Config:
        self.walk_qgis_project_tree(self.qgis_project_tree_root, [])
        return self.qsl_config

    def walk_qgis_project_tree(
        self,
        entity: QgsLayerTreeNode,
        path: list[str],
    ):
        """
        This is a highly recursive function which walks to the qgis job_layer_definition
        tree to extract all knowledge out
        of it. It is called from itself again for each level of group like elements
        which are found.

        Args:
            entity: The QGIS projects tree node which can be a QgsLayerTree, QgsLayerTreeGroup or
                QgsLayerTreeLayer.
            path: The path is a list of string which stores the information of the current
                tree path. This is
                used to construct a string for unifying job_layer_definition names by their
                tree path.
        """
        if isinstance(entity, QgsLayerTreeLayer):
            # this is a job_layer_definition, we can extract its information
            self.extract_save_layer(
                entity,
                path,
            )
        elif isinstance(entity, (QgsLayerTreeGroup, QgsLayerTree)):
            # these are "group like" elements, we need to step into them one level deeper.
            short_name = self.get_group_short_name(entity)
            if short_name != "":
                # '' is the root of the tree, we don't want it to be part of the path
                path = path + [short_name]
            self.extract_group(
                entity,
                path,
            )
            for child in entity.children():
                # we handle all the children of the group like thing.
                self.walk_qgis_project_tree(
                    child,
                    path,
                )
        else:
            logging.error(
                f"This element was not expected while walking QGIS project tree: {entity}"
            )

    def extract_group(
        self,
        group: QgsLayerTreeGroup,
        path: list[str],
    ):
        """
        Collects data pertaining to a QGIS job_layer_definition tree group. Basically
        this translates a QgsLayerTreeGroup
        into a QGIS-Server-Light TreeGroup.

        Args:
            group: The group which is handled.
            path: The path is a list of string which stores the information of the current
                tree path. This is
                used to construct a string for unifying job_layer_definition names by
                their tree path.
        """
        children = []
        for child in group.children():
            if isinstance(child, QgsLayerTreeGroup):
                children.append(
                    self.create_unified_short_name(self.get_group_short_name(child), path)
                )
            else:
                children.append(child.layer().id())
        short_name = self.create_unified_short_name(self.get_group_short_name(group), path[:-1])
        self.qsl_tree.members.append(
            TreeGroup(
                id=short_name,
                name=short_name,
                children=children,
            )
        )
        self.qsl_datasets.group.append(
            Group(
                id=short_name,
                name=short_name,
                title=self.get_group_title(group),
            )
        )

    def extract_save_layer(
        self,
        child: QgsLayerTreeLayer,
        path: list[str],
        types_from_editor_widget: bool = False,
    ):
        """Save the given job_layer_definition to the output path."""
        layer = child.layer()
        layer_type = self.get_layer_type(layer)
        if layer_type is None:
            return
        decoded = self.decode_datasource(layer)
        short_name = self.short_name(self.get_layer_short_name(child), path)
        if layer.isSpatial():
            crs = self.create_qsl_crs_from_qgs_layer(layer)
            layer_extent = layer.extent()
            bbox_wgs84 = self.create_qsl_bbox_from_qgis_rectangle_wgs84(
                self.qgis_project, layer, layer_extent
            )
            bbox = self.create_qsl_bbox_from_qgis_rectangle_extent(layer_extent)
            is_spatial = True
        else:
            crs = None
            bbox_wgs84 = None
            bbox = None
            is_spatial = False
        if layer_type == "vector":
            if layer.providerType().lower() == "ogr":
                source = DataSource(ogr=self.create_qsl_source_ogr(decoded))
            elif layer.providerType().lower() == "postgres":
                source = DataSource(postgres=self.create_qsl_source_postgresql(decoded))
                source_path_parts = []
                DictEncoder().encode(source.postgres)
                for field in fields(source.postgres):
                    source_path_parts.append(
                        f"{field.name}={getattr(source.postgres, field.name)!r}"
                    )
            elif layer.providerType().lower() == "wfs":
                # TODO: Correctly implement source!
                source = WfsSource()
            else:
                logging.error(
                    f"Unknown provider type {layer.providerType().lower()} for "
                    f"job_layer_definition {layer.title() or layer.name()}"
                )
                return
            qsl_vector_dataset_fields = self.create_qsl_fields_from_qgis_field(layer)
            self.qsl_datasets.vector.append(
                Vector(
                    name=short_name,
                    title=layer.title() or layer.name(),
                    styles=self.create_style_list(layer),
                    driver=layer.providerType(),
                    bbox_wgs84=bbox_wgs84,
                    fields=qsl_vector_dataset_fields,
                    source=source,
                    id=layer.id(),
                    crs=crs,
                    bbox=bbox,
                    minimum_scale=layer.minimumScale(),
                    maximum_scale=layer.maximumScale(),
                    geometry_type_simple=layer.geometryType().name,
                    geometry_type_wkb=layer.wkbType().name,
                    is_spatial=is_spatial,
                )
            )
        elif layer_type == "raster":
            if layer.providerType() == "gdal":
                source = DataSource(gdal=self.create_qsl_source_gdal(decoded))
            elif layer.providerType() == "wms":
                if "tileMatrixSet" in decoded:
                    source = DataSource(wmts=self.create_qsl_source_wmts(decoded))
                else:
                    if decoded.get("type") == "xyz":
                        source = DataSource(xyz=self.create_qsl_source_xyz(decoded))
                    else:
                        source = DataSource(wms=self.create_qsl_source_wms(decoded))
            else:
                logging.error(f"Unknown provider type: {layer.providerType().lower()}")
                return
            if source is not None:
                self.qsl_datasets.raster.append(
                    Raster(
                        name=short_name,
                        title=layer.title() or layer.name(),
                        styles=self.create_style_list(layer),
                        driver=layer.providerType(),
                        bbox_wgs84=bbox_wgs84,
                        source=source,
                        id=layer.id(),
                        crs=crs,
                        bbox=bbox,
                        minimum_scale=layer.minimumScale(),
                        maximum_scale=layer.maximumScale(),
                        is_spatial=is_spatial,
                    )
                )
            else:
                logging.error(
                    f"Source was None this is not expected. Layer was: {short_name}, "
                    f"QGIS job_layer_definition ID:{layer.id()}"
                )
        elif layer_type == "custom":
            if layer.providerType().lower() in ["xyzvectortiles", "mbtilesvectortiles"]:
                source = DataSource(vector_tile=self.create_qsl_source_vector_tiles(decoded))
            else:
                logging.error(
                    f"Unknown provider type: {layer.providerType().lower()} Layer "
                    f"was: {short_name}, QGIS job_layer_definition ID:{layer.id()}"
                )
                # TODO: make this more configurable
                return
            self.qsl_datasets.custom.append(
                Custom(
                    name=short_name,
                    title=layer.title() or layer.name(),
                    styles=self.create_style_list(layer),
                    driver=layer.providerType(),
                    bbox_wgs84=bbox_wgs84,
                    source=source,
                    id=layer.id(),
                    crs=crs,
                    bbox=bbox,
                    minimum_scale=layer.minimumScale(),
                    maximum_scale=layer.maximumScale(),
                    is_spatial=is_spatial,
                )
            )
        else:
            logging.error(
                f'Unknown layer_type "{layer_type}" Layer was: {short_name}, QGIS '
                f"job_layer_definition ID:{layer.id()}"
            )
            return

    def short_name(self, short_name: str, path: list[str]) -> str:
        """
        Decides if to use the short name itself or the unified version by the tree path.

        Args:
            short_name: The short name either of the group or the job_layer_definition.
            path: The path is a list of string which stores the information of the current
                tree path. This is
                used to construct a string for unifying job_layer_definition names by
                their tree path.

        Returns:
            The short name itself or its unified tree path.
        """
        if self.unify_layer_names_by_group:
            return self.create_unified_short_name(short_name, path)
        else:
            return short_name

    def create_unified_short_name(self, short_name: str, path: list[str]):
        """
        Creates the unified short name, separated by the configured separator.

        Args:
            short_name: The short name either of the group or the job_layer_definition.
            path: The path is a list of string which stores the information of the current
                tree path. This is
                used to construct a string for unifying job_layer_definition names by
                their tree path.

        Returns:

        """
        short_name_parts = path + [short_name]
        return self.unify_layer_names_by_group_separator.join(short_name_parts)

    def decode_datasource(self, layer: QgsMapLayer) -> dict:
        """
        Decodes a QGIS map job_layer_definition datasource into a dict and ensures that
        types are pythonic and pathes are
        clean for further usage.

        Args:
            layer: The job_layer_definition which the datasource should be extracted from.

        Returns:
            The decoded and cleaned datasource.
        """
        decoded = QgsProviderRegistry.instance().decodeUri(
            layer.providerType(), layer.dataProvider().dataSourceUri()
        )
        logging.debug(f"Layer source: {decoded}")
        for key in decoded:
            if str(decoded[key]) == "None" or str(decoded[key]) == "NULL":
                decoded[key] = None
            else:
                decoded[key] = str(decoded[key])
            if key == "path":
                decoded[key] = decoded[key].replace(f"{self.qgis_project.readPath('./')}/", "")
        return decoded

    @staticmethod
    def create_qsl_field_from_qgis_field(field: QgsField, is_primary_key: bool) -> Field:
        attribute_type_xml = Exporter.obtain_simple_types_from_qgis_field_xml(field)
        (
            editor_widget_type,
            editor_widget_type_wfs,
            editor_widget_type_json,
            editor_widget_type_json_format,
        ) = Exporter.obtain_editor_widget_type_from_qgis_field(field)
        (
            attribute_type_json,
            attribute_type_json_format,
        ) = Exporter.obtain_simple_types_from_qgis_field_json(field)
        return Field(
            is_primary_key=is_primary_key,
            name=field.name(),
            type=field.typeName(),
            type_wfs=attribute_type_xml,
            type_oapif=attribute_type_json,
            type_oapif_format=attribute_type_json_format,
            alias=field.alias() or field.name().title(),
            comment=field.comment(),
            nullable=is_primary_key and Exporter.obtain_nullable(field),
            length=Exporter.provide_field_length(field),
            precision=Exporter.provide_field_precision(field),
            editor_widget_type=editor_widget_type,
            editor_widget_type_wfs=editor_widget_type_wfs,
            editor_widget_type_oapif=editor_widget_type_json,
            editor_widget_type_oapif_format=editor_widget_type_json_format,
        )

    @staticmethod
    def obtain_nullable(field: QgsField):
        return field.constraints().constraints() != QgsFieldConstraints.Constraint.ConstraintNotNull

    @staticmethod
    def provide_field_length(field: QgsField) -> int | None:
        length = field.length()
        if length > 0:
            return length
        else:
            return None

    @staticmethod
    def provide_field_precision(field: QgsField) -> int | None:
        precision = field.precision()
        if precision > 0:
            return precision
        else:
            return None

    @staticmethod
    def create_qsl_fields_from_qgis_field(layer: QgsVectorLayer) -> list[Field]:
        fields = []
        pk_indexes = layer.dataProvider().pkAttributeIndexes()
        for field_index, field in enumerate(layer.fields().toList()):
            fields.append(
                Exporter.create_qsl_field_from_qgis_field(field, (field_index in pk_indexes))
            )
        return fields

    @staticmethod
    def obtain_simple_types_from_qgis_field_xml(field: QgsField) -> str:
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

    @staticmethod
    def get_group_title(group: QgsLayerTreeGroup) -> str:
        if group.customProperty("wmsTitle"):
            return group.customProperty("wmsTitle")
        elif hasattr(group, "groupLayer"):  # noqa: SIM102
            # since QGIS 3.38
            if (
                group.groupLayer()
                and group.groupLayer().serverProperties()
                and group.groupLayer().serverProperties().title()
            ):
                return group.groupLayer().serverProperties().title()
        return group.name()

    @staticmethod
    def get_group_short_name(group: QgsLayerTreeGroup) -> str:
        if group.customProperty("wmsShortName"):
            return group.customProperty("wmsShortName")
        elif hasattr(group, "groupLayer"):  # noqa: SIM102
            # since QGIS 3.38
            if (
                group.groupLayer()
                and group.groupLayer().serverProperties()
                and group.groupLayer().serverProperties().shortName()
            ):
                return group.groupLayer().serverProperties().shortName()
        short_name = Exporter.sanitize_name(group.name(), lower=True)
        if short_name == "_":
            # this is the tree root, we return empty string here
            return ""
        return short_name

    @staticmethod
    def sanitize_name(raw: str, lower: bool = False) -> str:
        """
        Transforms an arbitrary string into a WMS/WFS and URL compatible short name for a
        job_layer_definition or group.

        Steps:
        1. Unicode‑NFD → ASCII‑transliteration (removes umlauts/diacritics).
        2. All chars, which are NOT [A‑Za‑z0‑9_.‑], will be replaced by '_' ersetzen.
        3. Reduce multiple underscore '_' to a single one.
        4. Remove leading '_', '.', '-'.
        5. If the string is empty OR does not start with a letter OR not start with '_',
           a leading '_' will be added.
        6. Optional all will be converted to lowercase (lower=True).
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

    @staticmethod
    def obtain_editor_widget_type_from_qgis_field(
        field: QgsField,
    ) -> tuple[str, str, str, str] | tuple[str, None, None, None]:
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
        editor_widget_type = setup.type()
        if editor_widget_type == "DateTime":
            field_format = config.get(
                "field_format", QgsDateTimeFieldFormatter.defaultFormat(attribute_type)
            )
            if field_format == QgsDateTimeFieldFormatter.TIME_FORMAT:
                return editor_widget_type, "time", "string", "time"
            elif field_format == QgsDateTimeFieldFormatter.DATE_FORMAT:
                return editor_widget_type, "date", "string", "date"
            elif (
                field_format == QgsDateTimeFieldFormatter.DATETIME_FORMAT
                or field_format == QgsDateTimeFieldFormatter.QT_ISO_FORMAT
            ):
                return editor_widget_type, "dateTime", "string", "date-time"
        elif editor_widget_type == "Range":
            if config.get("Precision"):
                config_precision = int(config["Precision"])
                if config_precision != field.precision():
                    if config_precision == 0:
                        return editor_widget_type, "integer", "integer", "int64"
                    else:
                        return editor_widget_type, "decimal", "number", "double"

        logging.error(f"Editor widget type was not handled as expected: {editor_widget_type}")
        return editor_widget_type, None, None, None

    @staticmethod
    def obtain_simple_types_from_qgis_field_json(
        field: QgsField,
    ) -> tuple[str, str] | tuple[str, None]:
        """
        Delivers the type match for json based on the field QgsField type.

        Args:
            field: The field of an `QgsVectorLayer`.

        Returns:
            Unified type name and format in a tuple.
        """
        attribute_type = field.type()
        if attribute_type == QMetaType.Type.Int:
            return "integer", None
        elif attribute_type == QMetaType.Type.UInt:
            return "integer", "uint32"
        elif attribute_type == QMetaType.Type.LongLong:
            return "integer", "int64"
        elif attribute_type == QMetaType.Type.ULongLong:
            return "integer", "uint64"
        elif attribute_type == QMetaType.Type.Double:
            return "number", "double"
        elif attribute_type == QMetaType.Type.Float:
            return "number", "float"
        elif attribute_type == QMetaType.Type.Bool:
            return "boolean", None
        elif attribute_type == QMetaType.Type.QDate:
            return "string", "date"
        elif attribute_type == QMetaType.Type.QTime:
            return "string", "time"
        elif attribute_type == QMetaType.Type.QDateTime:
            return "string", "date-time"
        else:
            # we handle all unknown types as string. Since its for JavaScript, this should be safe.
            return "string", None

    @staticmethod
    def create_qsl_source_wms(datasource: dict) -> WmsSource:
        return WmsSource.from_qgis_decoded_uri(datasource)

    @staticmethod
    def create_qsl_source_vector_tiles(datasource: dict) -> VectorTileSource:
        return VectorTileSource.from_qgis_decoded_uri(datasource)

    @staticmethod
    def create_qsl_source_xyz(datasource: dict) -> XYZSource:
        return XYZSource.from_qgis_decoded_uri(datasource)

    @staticmethod
    def create_qsl_source_wmts(datasource: dict) -> WmtsSource:
        return WmtsSource.from_qgis_decoded_uri(datasource)

    @staticmethod
    def create_qsl_source_gdal(datasource: dict) -> GdalSource:
        return GdalSource.from_qgis_decoded_uri(datasource)

    @staticmethod
    def create_qsl_source_ogr(datasource: dict) -> OgrSource:
        return OgrSource.from_qgis_decoded_uri(datasource)

    def create_qsl_source_postgresql(self, datasource: dict) -> PostgresSource:
        config = datasource
        if datasource.get("service"):
            if self.pg_service_configs.get(datasource["service"]):
                service_config = self.pg_service_configs[datasource["service"]]
            else:
                service_config = {}
            if service_config == {}:
                logging.error(
                    f"""
                    There was a pg_service configuration in the project but it could not be found in
                    available configurations: {datasource["service"]}
                    Its highly possible that the exported project won't work.
                """
                )
            # merging pg_service content with config of qgis project (qgis project config overwrites
            # pg_service configs
            config = Exporter.merge_dicts(service_config, datasource)
        if not config.get("username") and not config.get("user"):
            raise LookupError(
                f"Configuration does not contain any info about the db user name {config}"
            )
        if config.get("sslmode") and isinstance(config["sslmode"], str):
            # this case happens when the sslmode is defined in the pg_service.conf and
            # not in the qgis project (happens when project files are generated not with
            # qgis desktop but with some automation (CI/CD) via pyqgis).
            # in those cases we first translate the string representation from pg_service.conf
            # to the int representation used in QGIS world.
            config["sslmode"] = self.sslmode_str_to_int(config["sslmode"])

        postgres_source = PostgresSource.from_qgis_decoded_uri(config)
        postgres_source.ssl_mode_text = self.sslmode_int_to_str(postgres_source.sslmode)
        return postgres_source

    @staticmethod
    def merge_dicts(a, b):
        """
        Merges two dicts recursively, b values overwrites a values.

        Args:
            a: Dictionary which is the base.
            b: Dictionary which is merged in and whose values overwrites the one.

        Returns:
            The merged dict.
        """
        result = a.copy()
        for key, value in b.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Exporter.merge_dicts(result[key], value)
            else:
                if key in ["user", "username"] and value is None:
                    logging.debug(
                        f"QGIS Datasource contained '{key}', but it's value was NONE, so we"
                        f"not copied that over! "
                    )
                else:
                    result[key] = value
        return result

    @staticmethod
    def sslmode_int_to_str(ssl_mode: int) -> str:
        """
        Mapper to map ssl modes from QGIS int to plain postgres.

        Args:
            ssl_mode: The ssl mode of the datasource as a int value matching one of
                https://qgis.org/pyqgis/3.44/core/QgsDataSourceUri.html#qgis.core.QgsDataSourceUri.SslMode

        Returns:
            The string representation of the ssl mode as it is used by postgres connections.
        """
        return QgsDataSourceUri.encodeSslMode(int(ssl_mode))

    @staticmethod
    def sslmode_str_to_int(ssl_mode: str) -> int:
        """
        Mapper to map ssl modes from plain postgres to QGIS int.

        Args:
            ssl_mode: The ssl mode of the datasource as a string matching one of
                https://www.postgresql.org/docs/current/libpq-ssl.html#LIBPQ-SSL-PROTECTION

        Returns:
            The integer representation of the ssl mode as it is used by qgis connections.
        """
        return QgsDataSourceUri.decodeSslMode(ssl_mode)

    @staticmethod
    def create_qsl_crs_from_qgs_layer(layer: QgsMapLayer) -> Crs:
        """
        Translates the QGIS job_layer_definition crs information into an instance of the
        QGIS-Server-Light interface Crs
        instance.

        Args:
            layer: The job_layer_definition to take the crs information from.

        Returns:
            The instance of the QSL interface Crs.
        """
        layer_crs = layer.dataProvider().crs()
        return Crs(
            postgis_srid=layer_crs.postgisSrid(),
            auth_id=layer_crs.authid(),
            ogc_uri=layer_crs.toOgcUri(),
            ogc_urn=layer_crs.toOgcUrn(),
        )

    @staticmethod
    def get_layer_short_name(layer: QgsLayerTreeLayer) -> str:
        """
        This method determines which name is used as the short name of the job_layer_definition.

        Args:
            layer: The job_layer_definition which the short name should be derived from.

        Returns:
            The short name.
        """
        if layer.layer().shortName():
            return layer.layer().shortName()
        elif (
            hasattr(layer.layer(), "serverProperties")
            and layer.layer().serverProperties().shortName()
        ):
            return layer.layer().serverProperties().shortName()
        return layer.layer().id()

    @staticmethod
    def make_wgs84_geom_transform(project, layer) -> QgsCoordinateTransform:
        """
        Creates a QgisCoordinateTransform context to transform a job_layer_definition
        to EPSG:4326 aka wgs84.

        Args:
            project: The QGIS project instance.
            layer: The job_layer_definition which's extent should be reprojected.

        Returns:
            The QGIS transformation context.
        """
        source_crs = layer.crs()
        epsg_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        return QgsCoordinateTransform(source_crs, epsg_4326, project)

    @staticmethod
    def create_qsl_bbox_from_qgis_rectangle_wgs84(
        project: QgsProject, layer: QgsMapLayer, extent: QgsRectangle
    ) -> BBox:
        """
        Reprojects the job_layer_definition's extent using WGS84.

        Args:
            project: The QGIS project instance for projection context.
            layer: The job_layer_definition which for the projection context.
            extent: The extent which will be reprojected.

        Returns:
            The QSL bbox reprojected to WGS84.
        """
        transformation_context = Exporter.make_wgs84_geom_transform(project, layer)
        reprojected_extent = transformation_context.transform(extent)
        return Exporter.create_qsl_bbox_from_qgis_rectangle_extent(reprojected_extent)

    @staticmethod
    def create_qsl_bbox_from_qgis_rectangle_extent(extent: QgsRectangle) -> BBox:
        return BBox(
            x_min=extent.xMinimum(),
            x_max=extent.xMaximum(),
            y_min=extent.yMinimum(),
            y_max=extent.yMaximum(),
        )

    @staticmethod
    def get_layer_type(layer: QgsMapLayer) -> str | None:
        """
        Gets the type of the given Qgis job_layer_definition as a string if the type is supported.
        This is to flatten the
        understanding of layers from qgis into something we can handle.

        Args:
            layer: The job_layer_definition to decide the type for.

        Returns:
            "raster", "vector" or "custom" if a job_layer_definition matched and None otherwise.
        """
        if isinstance(layer, QgsRasterLayer):
            return "raster"
        elif isinstance(layer, QgsVectorLayer):
            return "vector"
        elif isinstance(
            layer, (QgsVectorTileLayer, QgsTiledSceneLayer, QgsPointCloudLayer, QgsMeshLayer)
        ):
            return "custom"
        else:
            logging.error(f"Not implemented: {layer.type()}")
        return None

    @staticmethod
    def open_qgis_project(path_to_project: str) -> QgsProject:
        """


        Args:
            path_to_project: The absolute path on the file system where the project
            can be read from.

        Returns:
            The opened project (read).
        """
        project = QgsProject.instance()
        project.read(path_to_project)
        return project

    @staticmethod
    def prepare_qgis_project_name(project: QgsProject) -> tuple[str, str]:
        """


        Args:
            project: The instantiated QGIS project.

        Returns:
            Tuple of str version, name
        """
        return project.title() or project.baseName()

    @staticmethod
    def extract_metadata(project: QgsProject) -> MetaData:
        """
        Creates a QSL interface instance for metadate pulled out of the QGIS project.

        Args:
            project: The instantiated QGIS project.

        Returns:
            The metadata interface instance.
        """
        _meta = project.metadata()
        wms_entries = Exporter.get_project_server_entries(project, "wms")
        service = Service(**dict(sorted({**wms_entries}.items())))
        return MetaData(
            service=service,
            author=_meta.author(),
            categories=_meta.categories(),
            creationDateTime=_meta.creationDateTime().toPyDateTime().isoformat(),
            language=_meta.language(),
            links=[link.url for link in _meta.links()],
        )

    @staticmethod
    def get_project_server_entries(project, scope_or_scopes: str | list) -> dict:
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
            if scope not in supported_scopes:
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
                    # PyQGIS sometimes violates Liskov's substitution principle so naming
                    # tricks needed
                    list_as_text = ", ".join(project.readListEntry(qgis_scope_name, key)[0])
                    acc.append((our_scope_name, list_as_text))
                else:
                    acc.append(
                        (
                            our_scope_name,
                            project.readEntry(qgis_scope_name, key)[0],
                        )
                    )

                return acc

            return dict(reduce(collect, to_collect, []))

    @staticmethod
    def create_style_list(qgs_layer: QgsMapLayer) -> list[Style]:
        style_names = qgs_layer.styleManager().styles()
        style_list = []
        for style_name in style_names:
            style_doc = QDomDocument()
            qgs_layer.styleManager().setCurrentStyle(style_name)
            qgs_layer.exportNamedStyle(style_doc)
            style_list.append(
                Style(
                    name=style_name,
                    definition=urlsafe_b64encode(zlib.compress(style_doc.toByteArray())).decode(),
                )
            )
        return style_list
