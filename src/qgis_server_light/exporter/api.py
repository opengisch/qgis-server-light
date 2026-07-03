import logging
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, request
from xsdata.formats.dataclass.parsers import DictDecoder
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.exporter.api import ExportParameters, ExportResult

allowed_extensions = (".qgz", ".qgs")

app = Flask(__name__)


def assemble_project_base_path(
    data_path: str, mandant_name: str, project_name: str
) -> Path:
    return Path(data_path, mandant_name, project_name)


def assemble_output_file_path(project_base_path: Path, output_format: str) -> Path:
    return Path(str(project_base_path) + output_format)


@app.route("/export", methods=["POST"])
def api_export():
    logging.getLogger().setLevel(logging.DEBUG)
    data_path = os.environ.get("QSL_DATA_ROOT")
    if data_path is None:
        logging.error(
            "QSL_DATA_ROOT was not defined in the services ENV, we cant run the export."
        )
        result = ExportResult(successful=False)
        return Response(JsonSerializer().render(result), mimetype="text/json")
    body = request.get_json()
    parser_config = ParserConfig(fail_on_unknown_properties=True)
    try:
        parameters = DictDecoder(config=parser_config).decode(body, ExportParameters)
    except Exception as e:
        logging.error(e)
        result = ExportResult(successful=False)
        return Response(JsonSerializer().render(result), mimetype="text/json")

    project_base_path = assemble_project_base_path(
        data_path, parameters.mandant, parameters.project
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
        output_file = assemble_output_file_path(
            project_base_path, parameters.output_format
        )
        output_file.write_text(process.stdout)
        result = ExportResult(successful=True)
    except subprocess.CalledProcessError as e:
        logging.error(e.stderr)
        result = ExportResult(successful=False)
    return Response(JsonSerializer().render(result), mimetype="text/json")


if __name__ == "__main__":
    data_path = os.environ.get("QSL_DATA_ROOT", None)
    exporter_host = os.environ.get("QSL_EXPORTER_API_HOST", "127.0.0.1")
    exporter_port = int(os.environ.get("QSL_EXPORTER_API_PORT", 5000))
    if data_path is None:
        raise RuntimeError(
            "Mandatory 'QSL_DATA_ROOT' does not exist in the environment."
        )
    app.run(host=exporter_host, debug=True, threaded=False, port=exporter_port)
