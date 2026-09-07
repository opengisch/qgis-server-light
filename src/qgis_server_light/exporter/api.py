import subprocess
import sys
from pathlib import Path

import click
from flask import Flask, Response, request
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.exporter.api import ExportParameters, ExportResult

app = Flask(__name__)

DATA_ROOT: Path | None = None
LOGLEVEL: str = "INFO"


def assemble_project_base_path(data_path: Path, project_path: str) -> Path:
    return Path(data_path, project_path)


def assemble_output_file_path(project_base_path: Path, output_format: str) -> Path:
    return Path(str(project_base_path) + f".{output_format}")


@app.route(
    "/export",
    methods=["POST"],
)
def api_export():
    global DATA_ROOT, LOGLEVEL
    response_mime_type = "text/json"
    if DATA_ROOT is None:
        e = (
            "Something is wrong with the DATA_ROOT, it has the value None."
            "This means the api has started wrongly, we cant run the export."
        )
        app.logger.error(e)
        result = ExportResult(successful=False, content=e)
        return Response(JsonSerializer().render(result), mimetype=response_mime_type)
    body = request.get_json()
    app.logger.debug(f"Received a new task to export {type(body)} {body}")
    parser_config = ParserConfig(fail_on_unknown_properties=True)
    try:
        parameters = JsonParser(config=parser_config).from_string(body, ExportParameters)
    except Exception as e:
        app.logger.exception(e)
        result = ExportResult(successful=False, content=str(e))
        return Response(JsonSerializer().render(result), mimetype=response_mime_type)

    qualified_path = assemble_project_base_path(DATA_ROOT, parameters.project_path)
    if not qualified_path.exists():
        e = f"project_file: {parameters.project_path} DOES NOT EXISTS in dataroot"
        app.logger.info(e)
        result = ExportResult(successful=False, content=str(e))
        return Response(JsonSerializer().render(result), mimetype=response_mime_type)

    try:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "qgis_server_light.exporter.cli",
                "export",
                "--project",
                str(qualified_path),
                "--unify_layer_names_by_group",
                str(parameters.unify_layer_names_by_group),
                "--output_format",
                parameters.output_format,
            ],
            text=True,
            check=True,
            capture_output=True,
        )
        result = ExportResult(successful=True, content=process.stdout)
        app.logger.debug(f"Successfully extracted information from QGIS Project {result}")
    except subprocess.CalledProcessError as e:
        app.logger.exception(e.stderr)
        result = ExportResult(successful=False, content=str(e))
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
