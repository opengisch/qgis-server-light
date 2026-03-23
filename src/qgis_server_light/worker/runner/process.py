import logging
from typing import Optional

from qgis.analysis import QgsNativeAlgorithms, QgsPdalAlgorithms
from qgis.core import Qgis, QgsApplication, QgsProviderRegistry
from qgis.processing import ProcessingAlgFactory

from qgis_server_light.interface.job.common.input import QslJobInfoParameter
from qgis_server_light.interface.worker.info import (
    Algorithm,
    Output,
    Parameter,
    Process,
)
from qgis_server_light.worker.runner.common import JobContext, MapRunner


class ProcessRunner(MapRunner):
    def __init__(
        self,
        qgis: QgsApplication,
        context: JobContext,
        job_info: QslJobInfoParameter,
        layer_cache: Optional[dict],
    ):
        super().__init__(qgis, context, job_info, layer_cache)

        ProcessingAlgFactory()
        providers = QgsProviderRegistry.instance().pluginList().split("\n")
        logging.info("Found Providers:")
        for provider in providers:
            logging.info(f" - {provider}")

    def load_providers(self, qgis: Qgis):
        qgis.processingRegistry().addProvider(QgsNativeAlgorithms())
        qgis.processingRegistry().addProvider(QgsPdalAlgorithms())

    @classmethod
    def info(cls, qgis: Qgis) -> Process:
        registry = qgis.processingRegistry()
        algorithms = registry.algorithms()
        process = Process()
        for alg in algorithms:
            algorithm = Algorithm(
                id=alg.id(),
                name=alg.name(),
                display_name=alg.displayName(),
                help_string=alg.helpString(),
            )
            for param in alg.parameterDefinitions():
                algorithm.parameters.append(
                    Parameter(
                        name=param.name(),
                        type=param.type(),
                        description=param.description(),
                    )
                )
            for output in alg.outputDefinitions():
                algorithm.outputs.append(
                    Output(
                        name=output.name(),
                        type=output.type(),
                        description=output.description(),
                    )
                )
            process.algorithms.append(algorithm)
        return process
