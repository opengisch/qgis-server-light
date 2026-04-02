import datetime
import importlib
import inspect
import json
import logging
import pathlib
import uuid
from abc import ABC
from dataclasses import asdict, dataclass
from typing import Any, List, Optional, Type, Union

from qgis_server_light.interface.job.common.input import QslJobInfoParameter
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.worker.info import (
    EngineInfo,
    QgisInfo,
    Status,
)
from qgis_server_light.worker.qgis import Qgis, available_qgis_providers, qgis_version
from qgis_server_light.worker.runner.common import JobContext, Runner
from qgis_server_light.worker.runner.feature import GetFeatureRunner
from qgis_server_light.worker.runner.feature_info import GetFeatureInfoRunner
from qgis_server_light.worker.runner.render import RenderRunner


@dataclass
class EngineContext:
    base_path: Union[str, pathlib.Path]


_default_available_runners = {
    "qgis_server_light.worker.runner.render.RenderRunner": RenderRunner,
    "qgis_server_light.worker.runner.feature.GetFeatureRunner": GetFeatureRunner,
    "qgis_server_light.worker.runner.feature_info.GetFeatureInfoRunner": GetFeatureInfoRunner,
}


class Engine(ABC):
    def __init__(
        self,
        context: EngineContext,
        runner_plugins: list[str],
        svg_paths: Optional[List[str]] = None,
        log_level=logging.WARNING,
    ):
        self.qgis = Qgis(svg_paths, log_level)
        self.context = context
        self.layer_cache: dict[Any, Any] = {}
        self.available_runner_classes: dict[str, Type[Runner]] = {}
        self.available_runner_classes_by_job_info: dict[
            Type[QslJobInfoParameter], Type[Runner]
        ] = {}
        self.available_job_info_classes: dict[str, Type[QslJobInfoParameter]] = {}
        self._load_runner_plugins(runner_plugins)
        self.qgis_providers = available_qgis_providers()
        self.info = self._initialize_infos()

    def __del__(self):
        self.qgis.exitQgis()

    def _load_runner_plugins(self, worker_plugins: list[str]):
        for path in worker_plugins:
            if path in _default_available_runners:
                logging.info(
                    f"The runner with key {path} is a default runner, using this one..."
                )
                loaded_class = _default_available_runners[path]
            else:
                loaded_class = self._load_runner_class(path)
            self.available_runner_classes[path] = loaded_class
            self.available_runner_classes_by_job_info[loaded_class.job_info_class] = (
                loaded_class
            )
            self.available_job_info_classes[loaded_class.job_info_class.__name__] = (
                loaded_class.job_info_class
            )

    @staticmethod
    def _load_runner_class(path: str) -> Type[Runner]:
        """
        Loads a class dynamically at runtime, like:
        "mypackage.mymodule.MyClass"
        """

        module_path, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name, None)

        # Ensure the class was loaded correctly
        if cls is None:
            raise ImportError(
                f"Class '{class_name}' not found in module '{module_path}'."
            )
        if not inspect.isclass(cls):
            raise TypeError(f"Passed '{class_name}' is not a class.")

        if not issubclass(cls, Runner):
            raise TypeError(
                f"{cls.__name__} is not a plugin as expected (each plugin has to inherit from qgis_server_light.worker.job.common.Job)."
            )

        return cls

    def _initialize_infos(self):
        runner_infos = []
        for runner_key in self.available_runner_classes:
            runner_infos.append(
                self.available_runner_classes[runner_key].info(self.qgis)
            )
        worker_info = EngineInfo(
            id=str(uuid.uuid4()),
            qgis_info=QgisInfo(
                version=qgis_version(),
                path=self.qgis.prefixPath(),
                providers=self.qgis_providers,
            ),
            status=Status.STARTING,
            started=datetime.datetime.now().timestamp(),
            runner_infos=runner_infos,
        )
        logging.debug(json.dumps(asdict(worker_info), indent=2))
        return worker_info

    def runner_plugin_by_job_info(self, job_info: QslJobInfoParameter) -> Type[Runner]:
        """
        Here we decide which plugin we load dynamically out of the available ones.

        Args:
            job_info: Is the parameter instance we check the available worker classes and there the
                job_info_class at each.

        Returns:
            The selected runner class
        """
        try:
            return self.available_runner_classes_by_job_info[job_info.__class__]
        except KeyError:
            raise RuntimeError(f"Type {type(job_info)} not supported")

    def process(self, job_info: QslJobInfoParameter) -> JobResult:
        runner_class = self.runner_plugin_by_job_info(job_info)
        runner = runner_class(
            self.qgis,
            JobContext(self.context.base_path),
            job_info,
            layer_cache=self.layer_cache,
        )
        return runner.run()

    @property
    def status(self):
        return self.info.status.value

    def set_waiting(self):
        self.info.status = Status.WAITING

    def set_crashed(self):
        self.info.status = Status.CRASHED

    def set_processing(self):
        self.info.status = Status.PROCESSING
