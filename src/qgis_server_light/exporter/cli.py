import os.path

import click
from qgis.core import QgsApplication
from xsdata.formats.dataclass.serializers import JsonSerializer
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from qgis_server_light.exporter.extract import extract

os.environ["QT_QPA_PLATFORM"] = "offscreen"
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False)
qgs.initQgis()

allowed_output_formats = ("json", "xml")
allowed_extensions = ("qgz", "qgs")


@click.group
def cli():
    pass


@click.option("--project")
@click.option("--unify_layer_names_by_group")
@click.option("--output_format")
@cli.command(
    "export",
    help=f"Export a QGIS project ({f'|'.join(allowed_extensions)}) (1st argument) file to json format",
)
def export(
    project: str,
    unify_layer_names_by_group: bool = False,
    output_format: str | None = None,
) -> None:
    serializer_config = SerializerConfig(indent="  ")
    if output_format is None:
        output_format = "json"
    if not project.lower().endswith(allowed_extensions):
        raise NotImplementedError(
            f'Allowed qgis project file extensions are: {"|".join(allowed_extensions)} not => {project}'
        )
    if not output_format.lower() in allowed_output_formats:
        raise NotImplementedError(
            f'Allowed output formats are: {"|".join(allowed_output_formats)} not => {output_format}'
        )
    if os.path.isfile(project):
        config = extract(
            path_to_project=project,
            unify_layer_names_by_group=bool(unify_layer_names_by_group),
        )
        if output_format == "json":
            click.echo(JsonSerializer(config=serializer_config).render(config))
        elif output_format == "xml":
            click.echo(XmlSerializer(config=serializer_config).render(config))

    else:
        raise AttributeError("Project file does not exist")


if __name__ == "__main__":
    export()
