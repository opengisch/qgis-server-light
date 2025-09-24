import os
import os.path as path

from flask import Flask, Response, request
from qgis.core import QgsApplication

from xsdata.formats.dataclass.serializers import JsonSerializer
from xsdata.formats.dataclass.parsers import DictDecoder
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig
from xsdata.formats.dataclass.parsers.config import ParserConfig

from qgis_server_light.exporter.extract import extract
from qgis_server_light.interface.exporter import ExportParameters, ExportResult

allowed_output_formats = ("json", "xml")
allowed_extensions = ("qgz", "qgs")

app = Flask(__name__)


# init QGIS
os.environ["QT_QPA_PLATFORM"] = "offscreen"
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False)
qgs.initQgis()

@app.route('/export', methods=['POST'])
def api_export():

    body = request.get_json()
    parser_config = ParserConfig(fail_on_unknown_properties=True)
    parameters: ExportParameters = DictDecoder(config=parser_config).decode(body, ExportParameters)
    serializer_config = SerializerConfig(indent="  ")

    # project file
    project_file = ""
    for extension in allowed_extensions:
        project_file = path.join(parameters.mandant, parameters.project, ".".join([parameters.project, extension]))
        print(f"testing project_file: {project_file}")
        if path.exists(project_file):
            print(f"project_file: {project_file} EXISTS")
            break
    if not path.exists(project_file):
        raise NotImplementedError(
            f'Project {parameters.project} from mandant {parameters.mandant} not found.'
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

    # serializing
    if output_format == "json":
        return Response(JsonSerializer(config=serializer_config).render(config), mimetype='text/json')
    elif output_format == "xml":
        return Response(XmlSerializer(config=serializer_config).render(config), mimetype='text/xml')




if __name__ == "__main__":
    app.run(host= '0.0.0.0', debug=True, threaded=False)
