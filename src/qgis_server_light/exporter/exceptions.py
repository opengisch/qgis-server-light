from qgis_server_light.interface.exporter.extract import (
    Exporter,
    ExportMessage,
    Project,
    ResultWithMessages,
)


class ExportFailure(Exception):
    EXIT_CODE = 3

    def __init__(
        self,
        *,
        messages: list[ExportMessage],
        project: Project,
        exporter: Exporter,
    ) -> None:
        super().__init__("QGIS project export failed")
        self.messages = messages
        self.project = project
        self.exporter = exporter

    def get_result(self) -> ResultWithMessages:
        return ResultWithMessages(
            project=self.project,
            exporter=self.exporter,
            messages=self.messages,
        )
