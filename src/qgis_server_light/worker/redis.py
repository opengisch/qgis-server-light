import argparse
import datetime
import logging
import math
import pickle
import signal
import socket
import threading
import time
from abc import abstractmethod

from redis.backoff import ExponentialBackoff
from redis.client import Pipeline, Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError
from redis.retry import Retry
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer
from xsdata.formats.dataclass.serializers.dict import DictFactory

from qgis_server_light.interface.dispatcher.common import Status
from qgis_server_light.interface.dispatcher.protocol import (
    RedisProtocol,
    RedisPublishProtocol,
    RedisStateProtocol,
)
from qgis_server_light.interface.job.common.input import ExecutionMode, QslJobInfoParameter
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.process.description import ProcessDescriptions
from qgis_server_light.interface.job.process.input import QslJobInfoExecuteProcess
from qgis_server_light.worker.engine import Engine, EngineContext

DEFAULT_DATA_ROOT = "/io/data"
DEFAULT_SVG_PATH = "/io/svg"
DEFAULT_RUNNER_PLUGINS = ":".join(
    [
        "qgis_server_light.worker.runner.render.RenderRunner",
        "qgis_server_light.worker.runner.legend.GetLegendRunner",
        "qgis_server_light.worker.runner.feature.GetFeatureRunner",
        "qgis_server_light.worker.runner.crs.CrsRunner",
        # Not fully functional yet
        # "qgis_server_light.worker.runner.feature_info.GetFeatureInfoRunner",
    ]
)
DEFAULT_PROCESS_ALLOWLIST = ",".join(
    [
        "native:buffer",
        "native:centroids",
    ]
)


class RedisEngine(Engine):
    """The common part of the redis workers: connecting, registering, the
    heartbeat and the loop taking jobs from the queue. How a finished job is
    delivered is decided by the subclasses, so the loop does not need to know
    about it.

    Attributes:
        protocol: The protocol the engine is built on, it defines the queue the
            engine listens on.
    """

    protocol: type[RedisProtocol]

    def __init__(
        self,
        context: EngineContext,
        runner_plugins: list[str],
        svg_paths: list | None = None,
    ) -> None:
        self.boot_start = time.time()
        super().__init__(context, runner_plugins, svg_paths)
        # the worker only listens on the queue of its protocol
        self.queue_name = self.protocol.queue_name()
        self.shutdown = False
        self.retry_wait = 0.01
        self.max_retries = 11
        self.info_expire: int = 300
        self.heartbeat_interval = 1  # Heartbeat every second
        self.heartbeat_thread = None

    def retry_handling_with_jitter(self, count: int):
        if count <= self.max_retries:
            sleep = math.pow(2, count) * self.retry_wait
            logging.warning(f"Retrying in {sleep} seconds...")
            time.sleep(sleep)
        else:
            self.exit_connection_error()

    @staticmethod
    def exit_connection_error():
        logging.error("Shutting down => now connection to Redis")
        exit(404)

    def exit_gracefully(self, signum, frame):
        logging.error(f"Received: {signum}")
        self.shutdown = True
        exit(0)

    @staticmethod
    def set_job_runtime_status(
        job_id: str,
        pipeline: Pipeline,
        status: str,
        start_time: float,
    ):
        duration = time.time() - start_time
        ts = datetime.datetime.now().isoformat()
        pipeline.hset(RedisProtocol.job_key(job_id), RedisProtocol.job_status_key, status)
        pipeline.hset(
            RedisProtocol.job_key(job_id),
            f"{RedisProtocol.job_timestamp_key}.{status}",
            ts,
        )
        pipeline.hset(RedisProtocol.job_key(job_id), RedisProtocol.job_last_update_key, ts)
        pipeline.hset(RedisProtocol.job_key(job_id), RedisProtocol.job_duration_key, str(duration))
        pipeline.execute()

    def heartbeat(self, client: Redis) -> datetime.datetime:
        now = datetime.datetime.now()
        client.hset(f"worker:{self.info.id}", "last_seen", now.isoformat())
        return now

    def register_worker(self, client: Redis):
        # writing worker info to redis
        client.hset(f"worker:{self.info.id}", "info", JsonSerializer().render(self.info))
        # set timer to automatically remove worker info from list
        client.expire(f"worker:{self.info.id}", self.info_expire)
        # add worker to list of workers in redis
        client.sadd("workers", self.info.id)
        self.heartbeat(client)
        logging.info("Worker was registered in Redis")

    @staticmethod
    def write_process_registry(client: Redis, process_descriptions: ProcessDescriptions) -> bool:
        """Writes the process descriptions into the process registry, unless it holds
        descriptions already.

        Returns:
            If the descriptions were written.
        """
        return bool(
            client.set(
                RedisProtocol.process_registry_key,
                JsonSerializer(dict_factory=DictFactory.FILTER_NONE).render(process_descriptions),
                nx=True,
            )
        )

    def register_processes(self, client: Redis):
        """Registers the processes the worker serves. Workers without the process runner
        don't serve processes and register nothing."""
        process_runner_class = self.available_runner_classes_by_job_info.get(
            QslJobInfoExecuteProcess.__name__
        )
        if process_runner_class is None:
            return
        process_descriptions = process_runner_class.info(self.qgis, self.context.process_allowlist)
        if self.write_process_registry(client, process_descriptions):
            logging.info(f"Processes {self.context.process_allowlist} were registered in Redis")
        else:
            logging.info("Processes were registered in Redis already")

    def retry_connection(self, redis_url: str, count: int):
        logging.warning(f"Could not connect to redis on `{redis_url}`.")
        self.retry_handling_with_jitter(count)

    def start(self, redis_url) -> Redis:
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        r = Redis.from_url(redis_url, decode_responses=True, retry=Retry(ExponentialBackoff(), 0))
        retry_count = 0
        while True:
            try:
                retry_count += 1
                logging.debug(f"Looking up redis: {redis_url}")
                r.ping()
            except RedisConnectionError as e:
                logging.debug(f"Connection on Redis not successful => {e}")
                self.retry_connection(redis_url, retry_count)
            else:
                break
        logging.info(f"Connection to redis on `{redis_url}`successful.")
        return r

    def start_heartbeat_worker(self, client: Redis):
        """Creates an own thread which is responsible for renewing the heartbeat info
        of the worker in redis"""

        def heartbeat_loop():
            while not self.shutdown:
                try:
                    self.heartbeat(client)
                except Exception as e:
                    logging.warning(f"Heartbeat failed: {e}")
                time.sleep(self.heartbeat_interval)

        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logging.info("Heartbeat worker started")

    def run(self, redis_url):
        r = self.start(redis_url)
        p = r.pipeline()
        self.register_worker(r)
        self.register_processes(r)
        # Starte Heartbeat-Worker
        self.start_heartbeat_worker(r)
        retry_count = 0
        while not self.shutdown:
            try:
                logging.debug(f"Waiting for jobs on {self.queue_name}")
                self.set_waiting()
                # this is blocking the loop until a job is found in the redis
                # list/queue, if there is one we take it
                result = r.blpop(self.queue_name, timeout=0)
                if result is not None:
                    _, job_id = result
                    start_time = time.time()
                    job_info = None
                    try:
                        # we inform, that the job is running.
                        self.set_job_runtime_status(job_id, p, Status.RUNNING.value, start_time)

                        job_info_json = r.hget(
                            RedisProtocol.job_key(job_id), RedisProtocol.job_info_key
                        )
                        job_info_class_name = r.hget(
                            RedisProtocol.job_key(job_id), RedisProtocol.job_info_type_key
                        )
                        job_info_class = self.available_job_info_classes[job_info_class_name]
                        job_info = JsonParser().from_string(job_info_json, job_info_class)
                        result: JobResult = self.process(job_info)
                        self.succeed_job(job_id, job_info, result, p, start_time)
                    except Exception as e:
                        self.fail_job(job_id, job_info, e, p, start_time)

                        # we provide error information to the logs
                        logging.error(e, exc_info=True)
                    finally:
                        p.execute()
                    logging.debug(f"Job duration: {time.time() - start_time}")
            except (RedisConnectionError, TimeoutError) as _:
                retry_count += 1
                self.retry_connection(redis_url, retry_count)
                continue
        exit(0)

    @abstractmethod
    def succeed_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter,
        result: JobResult,
        pipeline: Pipeline,
        start_time: float,
    ):
        """Delivers the result of a job which was solved.

        Args:
            job_id: The unique identifier of the job.
            job_info: The job info of the job.
            result: The result the runner returned.
            pipeline: The pipeline holding the transaction.
            start_time: The time the job was taken from the queue.
        """
        pass

    @abstractmethod
    def fail_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter | None,
        error: Exception,
        pipeline: Pipeline,
        start_time: float,
    ):
        """Delivers the error of a job which failed.

        Args:
            job_id: The unique identifier of the job.
            job_info: The job info of the job, `None` if it failed before the
                job info could be read.
            error: The error the job failed with.
            pipeline: The pipeline holding the transaction.
            start_time: The time the job was taken from the queue.
        """
        pass


class RedisPublishEngine(RedisEngine):
    """The engine publishing the result to the waiting dispatcher (see
    `RedisPublishProtocol`). This is the default, map related jobs are served
    by it.
    """

    protocol = RedisPublishProtocol

    def publish_result(
        self, job_id: str, result: JobResult, pipeline: Pipeline, status: str, start_time: float
    ):
        """Sets the final status and publishes the pickled result. Success and
        failure only differ in the result and the status, so both end here.

        Args:
            job_id: The unique identifier of the job.
            result: The result to publish, the worker information is added.
            pipeline: The pipeline holding the transaction.
            status: The final status of the job.
            start_time: The time the job was taken from the queue.
        """
        result.worker_id = self.info.id
        result.worker_host_name = socket.gethostname()
        data = pickle.dumps(result)

        # we inform, that the job was finished
        self.set_job_runtime_status(job_id, pipeline, status, start_time)

        # we publish the result to any subscribers
        pipeline.publish(self.protocol.channel(job_id), data)

    def succeed_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter,
        result: JobResult,
        pipeline: Pipeline,
        start_time: float,
    ):
        self.publish_result(job_id, result, pipeline, Status.SUCCESS.value, start_time)

    def fail_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter | None,
        error: Exception,
        pipeline: Pipeline,
        start_time: float,
    ):
        # preparation of the result, containing error information
        result = JobResult(id=job_id, data=str(error), content_type="text")
        self.publish_result(job_id, result, pipeline, Status.FAILURE.value, start_time)


class RedisStateEngine(RedisEngine):
    """The engine keeping the result in the job hash (see `RedisStateProtocol`).
    Process-workers are started with it.
    """

    protocol = RedisStateProtocol

    def finish_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter | None,
        pipeline: Pipeline,
        status: str,
        start_time: float,
    ):
        """Renews the expiry, sets the final status and notifies a waiting
        dispatcher. Success and failure only differ in the fields written
        before, so both end here.

        Args:
            job_id: The unique identifier of the job.
            job_info: The job info of the job, `None` if it could not be read. A
                waiting dispatcher can not be ruled out then, so it is notified.
            pipeline: The pipeline holding the transaction.
            status: The final status of the job.
            start_time: The time the job was taken from the queue.
        """
        # the fields written before are executed in the same transaction as the
        # final status
        pipeline.expire(self.protocol.job_key(job_id), self.protocol.job_expire)
        self.set_job_runtime_status(job_id, pipeline, status, start_time)
        # the notification only wakes a waiting dispatcher, the job hash is
        # written already
        if job_info is None or job_info.execution_mode == ExecutionMode.SYNC:
            pipeline.publish(self.protocol.channel(job_id), status)

    def succeed_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter,
        result: JobResult,
        pipeline: Pipeline,
        start_time: float,
    ):
        pipeline.hset(self.protocol.job_key(job_id), self.protocol.job_result_key, result.data)
        pipeline.hset(
            self.protocol.job_key(job_id),
            self.protocol.job_result_content_type_key,
            result.content_type,
        )
        self.finish_job(job_id, job_info, pipeline, Status.SUCCESS.value, start_time)

    def fail_job(
        self,
        job_id: str,
        job_info: QslJobInfoParameter | None,
        error: Exception,
        pipeline: Pipeline,
        start_time: float,
    ):
        pipeline.hset(self.protocol.job_key(job_id), self.protocol.job_message_key, str(error))
        self.finish_job(job_id, job_info, pipeline, Status.FAILURE.value, start_time)


engine_classes: dict[str, type[RedisEngine]] = {
    "publish": RedisPublishEngine,
    "state": RedisStateEngine,
}


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--redis-url", type=str, help="redis url")

    parser.add_argument(
        "--log-level",
        type=str,
        help="log level (debug, info, warning or error)",
        default="info",
    )

    parser.add_argument(
        "--data-root",
        type=str,
        help=f"Absolute path to the data dir. Defaults to {DEFAULT_DATA_ROOT}",
        default=DEFAULT_DATA_ROOT,
    )

    parser.add_argument(
        "--svg-path",
        type=str,
        help=f"Absolute path to additional svg files. Multiple paths "
        f"can be separated by `:`. Defaults to {DEFAULT_SVG_PATH}",
        default=DEFAULT_SVG_PATH,
    )

    parser.add_argument(
        "--runner-plugins",
        type=str,
        help="Runner classes the worker boots with, as dotted paths. Multiple plugins "
        "can be separated by `:`. The worker listens on the queues of their jobs only, "
        "e.g. `qgis_server_light.worker.runner.process.ProcessRunner` for a worker "
        "serving processes. Defaults to the map related runners.",
        default=DEFAULT_RUNNER_PLUGINS,
    )

    parser.add_argument(
        "--process-allowlist",
        type=str,
        help="Ids of the QGIS algorithms the worker serves as processes, separated by `,`. "
        "Only used when the worker boots with the process runner. "
        f"Defaults to {DEFAULT_PROCESS_ALLOWLIST}",
        default=DEFAULT_PROCESS_ALLOWLIST,
    )

    parser.add_argument(
        "--engine",
        type=str,
        choices=list(engine_classes),
        help="How the worker delivers job results: `publish` publishes the result to the "
        "waiting dispatcher, `state` keeps it in the job hash. Defaults to publish",
        default="publish",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if not args.redis_url:
        raise AssertionError(
            "no redis host specified: start qgis-server-light with '--redis-url <QSL_REDIS_URL>'"
        )

    svg_paths = args.svg_path.split(":")
    runner_plugins = args.runner_plugins.split(":")
    process_allowlist = args.process_allowlist.split(",")
    engine = engine_classes[args.engine](
        EngineContext(args.data_root, process_allowlist),
        runner_plugins,
        svg_paths=svg_paths,
    )
    engine.run(
        args.redis_url,
    )


if __name__ == "__main__":
    main()
