import logging
import subprocess
import sys
from pathlib import Path

import click
from flask import Flask, Response, request
from xsdata.formats.dataclass.parsers import DictDecoder
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.exporter.api import ExportParameters, ExportResult

allowed_extensions = (".qgz", ".qgs")

app = Flask(__name__)

DATA_ROOT: Path | None = None
LOGLEVEL: str = "INFO"


def assemble_project_base_path(data_path: Path, mandant_name: str, project_name: str) -> Path:
    return Path(data_path, mandant_name, project_name)


def assemble_output_file_path(project_base_path: Path, output_format: str) -> Path:
    return Path(str(project_base_path) + f".{output_format}")


@app.route("/export", methods=["POST"])
def api_export():
    global DATA_ROOT, LOGLEVEL
    response_mime_type = "text/json"
    logging.getLogger().setLevel(LOGLEVEL)
    if DATA_ROOT is None:
        logging.error(
            "Something is wrong with the DATA_ROOT, it has the value None."
            "This means the api has started wrongly, we cant run the export."
        )
        result = ExportResult(successful=False)
        return Response(JsonSerializer().render(result), mimetype=response_mime_type)
    body = request.get_json()
    parser_config = ParserConfig(fail_on_unknown_properties=True)
    try:
        parameters = DictDecoder(config=parser_config).decode(body, ExportParameters)
    except Exception as e:
        logging.exception(e)
        result = ExportResult(successful=False)
        return Response(JsonSerializer().render(result), mimetype=response_mime_type)

    project_base_path = assemble_project_base_path(
        DATA_ROOT, parameters.mandant, parameters.project
    )
    project_file = None
    for extension in allowed_extensions:
        project_file = Path(str(project_base_path) + extension)
        logging.info(f"testing project_file: {project_file}")
        if project_file.exists():
            logging.info(f"project_file: {project_file} EXISTS")
            break

    try:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "qgis_server_light.exporter.cli",
                "--project",
                str(project_file),
                "--unify_layer_names_by_group",
                str(parameters.unify_layer_names_by_group),
                "--output_format",
                parameters.output_format,
            ],
            text=True,
            check=True,
            capture_output=True,
        )
        output_file = assemble_output_file_path(project_base_path, parameters.output_format)
        output_file.write_text(process.stdout)
        result = ExportResult(successful=True)
    except subprocess.CalledProcessError as e:
        logging.exception(e.stderr)
        result = ExportResult(successful=False)
    return Response(JsonSerializer().render(result), mimetype=response_mime_type)


@click.group
def main() -> None:
    """
    Just the central cli entry command. Currently, we don't use it, but its here
    for future content.

    """
    pass


@click.option(
    "--data-root",
    help="The host address the service will be started on.",
)
@click.option(
    "--host",
    type=str,
    default="127.0.0.1",
    help="The host address the service will be started on.",
)
@click.option(
    "--port",
    type=int,
    default=5000,
    help="The port the service will be exposed to.",
)
@click.option(
    "--log-level",
    type=str,
    default="info",
    help="log level (debug, info, warning or error)",
)
@main.command(
    "start",
    context_settings={"max_content_width": 120},
    help="""
    Starts the exporter API. be sure to set the data_root to an accessible directory!
    """,
)
def start(
    data_root,
    host: str = "127.0.0.1",
    port: int = 5000,
    log_level: str = "info",
):
    global DATA_ROOT, LOGLEVEL
    root_path = Path(data_root)
    if root_path.exists() and root_path.is_dir():
        DATA_ROOT = root_path
        LOGLEVEL = log_level.upper()
        app.run(
            host=host,
            debug=log_level.upper() in ["DEBUG"],
            threaded=False,
            port=port,
        )
    else:
        raise RuntimeError(f"Mandatory 'data_root' => {data_root} does not exist or is not a dir.")


if __name__ == "__main__":
    main()
