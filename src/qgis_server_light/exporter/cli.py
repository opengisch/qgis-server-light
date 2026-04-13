import logging
import os.path

import click
from qgis.analysis import QgsNativeAlgorithms
from qgis.core import QgsApplication
from xsdata.formats.dataclass.serializers import JsonSerializer, XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from qgis_server_light.exporter.exceptions import ExportFailure
from qgis_server_light.exporter.extract import Exporter
from qgis_server_light.interface.exporter.extract import Process
from qgis_server_light.worker.runner.process import algorithm_from_qgs_definition

os.environ["QT_QPA_PLATFORM"] = "offscreen"
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False)
qgs.initQgis()

allowed_output_formats = ("json", "xml")
allowed_extensions = ("qgz", "qgs")


@click.group
def main() -> None:
    """
    Just the central cli entry command. Currently, we don't use it, but its here
    for future content.

    """
    pass


@click.option("--project", help="Absolute path to the QGIS project.")
@click.option(
    "--unify_layer_names_by_group",
    default=False,
    help="Use the full tree path to unify job_layer_definition names.",
)
@click.option(
    "--output_format",
    default="json",
    help=f"The desired output format. Allowed are {'|'.join(allowed_output_formats)}.",
)
@main.command(
    "export",
    context_settings={"max_content_width": 120},
    help=f"""
    Export a QGIS project ({"|".join(allowed_extensions)}) (1st argument) file
    to {"|".join(allowed_output_formats)} format.

    Layers referencing a pg_service need the PGSERVICEFILE environment variable so
    that QGIS can open them during the export. The cli might be called with:

      PGSERVICEFILE=<absolute-path-to-pg_service.conf> python -m qgis_server_light.exporter.cli ...
    """,
)
def export(
    project: str,
    unify_layer_names_by_group: bool = False,
    output_format: str | None = None,
) -> None:
    logging.getLogger().setLevel(logging.DEBUG)
    serializer_config = SerializerConfig(indent="  ")
    output_format = "json" if output_format is None else output_format.lower()
    if not project.lower().endswith(allowed_extensions):
        raise click.BadParameter(
            f"Allowed qgis project file extensions "
            f"are: {'|'.join(allowed_extensions)} not => {project}",
            param_hint="--project",
        )
    if output_format not in allowed_output_formats:
        raise click.BadParameter(
            f"Allowed output formats are: {'|'.join(allowed_output_formats)} "
            f"not => {output_format}",
            param_hint="--output_format",
        )
    if not os.path.isfile(project):
        raise click.BadParameter(
            f"Project file '{project}' does not exist",
            param_hint="--project",
        )

    exporter = Exporter(
        project,
        unify_layer_names_by_group=bool(unify_layer_names_by_group),
    )

    if output_format == "json":
        serializer = JsonSerializer(config=serializer_config)
    elif output_format == "xml":
        serializer = XmlSerializer(config=serializer_config)
    else:
        raise RuntimeError(f"Unexpected output format {output_format}")

    try:
        config = exporter.run()
    except ExportFailure as err:
        click.echo(serializer.render(err.get_result()))
        raise click.exceptions.Exit(code=err.EXIT_CODE) from err
    else:
        click.echo(serializer.render(config))


@cli.command("export-processes")
def export_processes():
    serializer_config = SerializerConfig(indent="  ")
    registry = qgs.processingRegistry()
    registry.addProvider(QgsNativeAlgorithms())
    process = Process(
        algorithms=[
            algorithm_from_qgs_definition(registry.algorithmById(alg))
            for alg in [
                "native:buffer",
                "native:centroids",
                "native:concavehull",
                "native:rasterlayerproperties",
                "native:rescaleraster",
                "native:collect",
                "native:rasterize",
                "native:affinetransform",
            ]
        ]
    )
    click.echo(JsonSerializer(config=serializer_config).render(process))


if __name__ == "__main__":
    main()
