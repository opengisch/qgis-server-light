import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union, cast

from qgis_server_light.interface.job import QslGetFeatureInfoJob, QslGetMapJob, JobResult
from qgis_server_light.worker.qgis import Qgis
from qgis_server_light.worker.runner import (
    GetFeatureInfoRunner,
    MapRunner,
    RenderRunner, RunnerContext,
)


@dataclass
class EngineContext:
    base_path: Union[str, pathlib.Path]


class Engine:

    def __init__(
        self, context: EngineContext, svg_paths: Optional[List[str]] = None, log_level=logging.WARNING
    ) -> None:
        self.qgis = Qgis(svg_paths, log_level)
        self.context = context
        self.layer_cache: Dict[Any, Any] = {}

    def __del__(self):
        self.qgis.exitQgis()

    def process(self, job) -> JobResult:

        if isinstance(job, QslGetMapJob):
            runner = cast(
                MapRunner,
                RenderRunner(
                    self.qgis,
                    RunnerContext(
                        self.context.base_path
                    ),
                    job,
                    layer_cache=self.layer_cache
                ),
            )
        elif isinstance(job, QslGetFeatureInfoJob):
            runner = cast(
                MapRunner,
                GetFeatureInfoRunner(
                    self.qgis,
                    RunnerContext(
                        self.context.base_path
                    ),
                    job,
                    layer_cache=self.layer_cache
                ),
            )
        else:
            raise RuntimeError(f"Type {type(job)} not supported")

        return runner.run()
