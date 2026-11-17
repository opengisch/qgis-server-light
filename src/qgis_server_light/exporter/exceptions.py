from qgis_server_light.interface.exporter.extract import ExportFailureContent, ExportMessage


class ExportFailure(Exception):
    EXIT_CODE = 3

    def __init__(self, messages: list[ExportMessage]):
        self.messages = messages

    def get_export_failure_content(self):
        return ExportFailureContent(messages=self.messages)
