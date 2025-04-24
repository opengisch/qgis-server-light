import logging
import pathlib
from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union
from typing import cast

from qgis_server_light.interface.job import JobResult
from qgis_server_light.interface.job import QslGetFeatureInfoJob
from qgis_server_light.interface.job import QslGetFeatureJob
from qgis_server_light.interface.job import QslGetMapJob
from qgis_server_light.worker.qgis import Qgis
from qgis_server_light.worker.runner import GetFeatureInfoRunner
from qgis_server_light.worker.runner import GetFeatureRunner
from qgis_server_light.worker.runner import MapRunner
from qgis_server_light.worker.runner import RenderRunner
from qgis_server_light.worker.runner import RunnerContext


@dataclass
class EngineContext:
    base_path: Union[str, pathlib.Path]


class Engine:
    def __init__(
        self,
        context: EngineContext,
        svg_paths: Optional[List[str]] = None,
        log_level=logging.WARNING,
    ) -> None:
        self.qgis = Qgis(svg_paths, log_level)
        self.context = context
        self.layer_cache: Dict[Any, Any] = {}

    def __del__(self):
        self.qgis.exitQgis()

    def process(self, job: QslGetMapJob | QslGetFeatureInfoJob) -> JobResult:

        if isinstance(job, QslGetMapJob):
            runner = cast(
                MapRunner,
                RenderRunner(
                    self.qgis,
                    RunnerContext(self.context.base_path),
                    job,
                    layer_cache=self.layer_cache,
                ),
            )
        elif isinstance(job, QslGetFeatureInfoJob):
            runner = cast(
                MapRunner,
                GetFeatureInfoRunner(
                    self.qgis,
                    RunnerContext(self.context.base_path),
                    job,
                    layer_cache=self.layer_cache,
                ),
            )
        elif isinstance(job, QslGetFeatureJob):
            runner = cast(
                MapRunner,
                GetFeatureRunner(
                    self.qgis,
                    RunnerContext(self.context.base_path),
                    job,
                    layer_cache=self.layer_cache,
                ),
            )
        else:
            raise RuntimeError(f"Type {type(job)} not supported")

        return runner.run()
