import os
import os.path as path

from flask import Flask
from flask import Response
from flask import request
from qgis.core import QgsApplication
from xsdata.formats.dataclass.parsers import DictDecoder
from xsdata.formats.dataclass.parsers.config import ParserConfig
from xsdata.formats.dataclass.serializers import JsonSerializer
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from qgis_server_light.exporter.extract import extract
from qgis_server_light.interface.exporter import ExportParameters
from qgis_server_light.interface.exporter import ExportResult

allowed_output_formats = ("json", "xml")
allowed_extensions = ("qgz", "qgs")

app = Flask(__name__)


# init QGIS
os.environ["QT_QPA_PLATFORM"] = "offscreen"
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False)
qgs.initQgis()


@app.route("/export", methods=["POST"])
def api_export():
    data_path = os.environ.get("QSL_DATA_ROOT")
    body = request.get_json()
    parser_config = ParserConfig(fail_on_unknown_properties=True)
    parameters: ExportParameters = DictDecoder(config=parser_config).decode(
        body, ExportParameters
    )
    serializer_config = SerializerConfig(indent="  ")

    # project file
    project_file = ""
    for extension in allowed_extensions:
        project_file = path.join(
            data_path, parameters.mandant, ".".join([parameters.project, extension])
        )
        print(f"testing project_file: {project_file}")
        if path.exists(project_file):
            print(f"project_file: {project_file} EXISTS")
            break
    if not path.exists(project_file):
        raise NotImplementedError(
            f"Project {parameters.project} from mandant {parameters.mandant} not found."
        )
    print(f"project_file: {project_file}")

    # output format
    if not parameters.output_format.lower() in allowed_output_formats:
        raise NotImplementedError(
            f'Allowed output formats are: {"|".join(allowed_output_formats)} not => {parameters.output_format}'
        )
    output_format = parameters.output_format.lower()

    # extract
    config = extract(
        path_to_project=project_file,
        unify_layer_names_by_group=bool(parameters.unify_layer_names_by_group),
    )
    result = ExportResult(successful=False)

    content = None
    if output_format == "json":
        content = JsonSerializer(config=serializer_config).render(config)
    elif output_format == "xml":
        content = XmlSerializer(config=serializer_config).render(config)
    else:
        return Response(JsonSerializer().render(result), mimetype="text/json")
    if content:
        with open(
            path.join(
                data_path,
                parameters.mandant,
                ".".join([parameters.project, output_format]),
            ),
            mode="w+",
        ) as f:
            f.write(content)
    result.successful = True
    return Response(JsonSerializer().render(result), mimetype="text/json")


if __name__ == "__main__":
    data_path = os.environ.get("QSL_DATA_ROOT", None)
    if data_path is None:
        raise RuntimeError(
            "Mandatory 'QSL_DATA_ROOT' does not exist in the environment."
        )
    app.run(host="0.0.0.0", debug=True, threaded=False)
