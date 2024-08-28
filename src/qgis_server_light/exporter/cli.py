import os.path
import click
from qgis_server_light.exporter.extract import extract
from xsdata.formats.dataclass.serializers import JsonSerializer
from qgis.core import QgsApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"
QgsApplication.setPrefixPath('/usr', True)
qgs = QgsApplication([], False)
qgs.initQgis()


@click.group
def cli():
    pass


@click.option("--project")
@cli.command(
    "export",
    help="Export a QGIS project (.qgs|qgz) (1st argument) file to json format",
)
def export(project):

    if os.path.isfile(project):
        config = extract(path_to_project=project)
        click.echo(JsonSerializer().render(config))
    else:
        raise AttributeError


if __name__ == '__main__':
    export()
