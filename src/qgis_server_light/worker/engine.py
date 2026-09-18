import datetime
import importlib
import inspect
import json
import logging
import pathlib
import uuid
from abc import ABC
from dataclasses import asdict, dataclass
from typing import Any

from qgis_server_light.interface.job.common.input import QslJobInfoParameter
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.worker.info import (
    EngineInfo,
    QgisInfo,
    Status,
)
from qgis_server_light.worker.qgis import Qgis, version, version_name
from qgis_server_light.worker.runner.common import JobContext, Runner


@dataclass
class EngineContext:
    base_path: str | pathlib.Path


class Engine(ABC):  # noqa: B024
    def __init__(
        self,
        context: EngineContext,
        runner_plugins: list[str],
        svg_paths: list[str] | None = None,
        log_level=logging.WARNING,
    ):
        self.qgis = Qgis(svg_paths, log_level)
        self.context = context
        self.layer_cache: dict[Any, Any] = {}
        self.available_runner_classes: dict[str, type[Runner]] = {}
        self.available_runner_classes_by_job_info: dict[str, type[Runner]] = {}
        self.available_job_info_classes: dict[str, type[QslJobInfoParameter]] = {}
        self._load_runner_plugins(runner_plugins)
        logging.debug(self.available_runner_classes)
        logging.debug(self.available_runner_classes_by_job_info)
        logging.debug(self.available_job_info_classes)
        self.info = self._initialize_infos()

    def __del__(self):
        self.qgis.exitQgis()

    def _load_runner_plugins(self, worker_plugins: list[str]):
        for path in worker_plugins:
            loaded_class = self._load_runner_class(path)
            if loaded_class is not None:
                self.available_runner_classes[path] = loaded_class
                self.available_runner_classes_by_job_info[loaded_class.job_info_class.__name__] = (
                    loaded_class
                )
                self.available_job_info_classes[loaded_class.job_info_class.__name__] = (
                    loaded_class.job_info_class
                )

    @staticmethod
    def _load_runner_class(path: str) -> type[Runner] | None:
        """
        Loads a class dynamically at runtime, like:
        "mypackage.mymodule.MyClass"
        """

        module_path, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name, None)

        # Ensure the class was loaded correctly
        if cls is None:
            raise ImportError(f"Class '{class_name}' not found in module '{module_path}'.")
        if not inspect.isclass(cls):
            raise TypeError(f"Passed '{class_name}' is not a class.")

        if not issubclass(cls, Runner):
            raise TypeError(
                f"{cls.__name__} is not a plugin as expected (each plugin has to inherit "
                f"from qgis_server_light.worker.job.common.Job)."
            )

        return cls

    def _initialize_infos(self):
        worker_info = EngineInfo(
            id=str(uuid.uuid4()),
            qgis_info=QgisInfo(
                version=version(),
                version_name=version_name(),
                path=self.qgis.prefixPath(),
            ),
            status=Status.STARTING,
            started=datetime.datetime.now().timestamp(),
        )
        logging.debug(json.dumps(asdict(worker_info), indent=2))
        return worker_info

    def runner_plugin_by_job_info(self, job_info: QslJobInfoParameter) -> type[Runner]:
        """
        Here we decide which plugin we load dynamically out of the available ones.

        Args:
            job_info: Is the parameter instance we check the available worker classes and there the
                job_info_class at each.

        Returns:
            The selected runner class
        """
        try:
            return self.available_runner_classes_by_job_info[job_info.__class__.__name__]
        except KeyError as e:
            raise RuntimeError(f"Type {type(job_info)} not supported") from e

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
