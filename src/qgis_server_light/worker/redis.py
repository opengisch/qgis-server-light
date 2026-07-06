import argparse
import datetime
import logging
import math
import pickle
import signal
import socket
import threading
import time

from redis.backoff import ExponentialBackoff
from redis.client import Pipeline, Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError
from redis.retry import Retry
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.dispatcher.common import Status
from qgis_server_light.interface.dispatcher.redis_asio import RedisQueue
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.worker.engine import Engine, EngineContext

DEFAULT_DATA_ROOT = "/io/data"
DEFAULT_SVG_PATH = "/io/svg"


class RedisEngine(Engine):
    def __init__(
        self,
        context: EngineContext,
        runner_plugins: list[str],
        svg_paths: list | None = None,
    ) -> None:
        self.boot_start = time.time()
        super().__init__(context, runner_plugins, svg_paths)
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
        pipeline.hset(f"job:{job_id}", RedisQueue.job_status_key, status)
        pipeline.hset(
            f"job:{job_id}",
            f"{RedisQueue.job_timestamp_key}.{status}",
            ts,
        )
        pipeline.hset(f"job:{job_id}", RedisQueue.job_last_update_key, ts)
        pipeline.hset(f"job:{job_id}", RedisQueue.job_duration_key, str(duration))
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
                    logging.debug("Heartbeat published")
                except Exception as e:
                    logging.warning(f"Heartbeat failed: {e}")
                time.sleep(self.heartbeat_interval)

        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logging.info("Heartbeat worker started")

    def run(self, redis_url):
        r = self.start(redis_url)
        p = r.pipeline()
        # Starte Heartbeat-Worker
        self.start_heartbeat_worker(r)
        retry_count = 0
        while not self.shutdown:
            try:
                self.register_worker(r)
                logging.debug("Waiting for jobs")
                self.set_waiting()
                # this is blocking the loop until a job is found in the redis
                # list/queue, if there is one we take it
                result = r.blpop([RedisQueue.job_queue_name], timeout=0)
                if result is not None:
                    _, job_id = result
                    start_time = time.time()
                    try:
                        # we inform, that the job is running.
                        self.set_job_runtime_status(job_id, p, Status.RUNNING.value, start_time)

                        job_info_json = r.hget(f"job:{job_id}", RedisQueue.job_info_key)
                        job_info_class_name = r.hget(f"job:{job_id}", RedisQueue.job_info_type_key)
                        job_info_class = self.available_job_info_classes[job_info_class_name]
                        job_info = JsonParser().from_string(job_info_json, job_info_class)
                        result: JobResult = self.process(job_info)
                        result.worker_id = self.info.id
                        result.worker_host_name = socket.gethostname()
                        data = pickle.dumps(result)

                        # we inform, that the job was finished successful
                        self.set_job_runtime_status(job_id, p, Status.SUCCESS.value, start_time)

                        # we publish the result to any subscribers
                        p.publish(f"{RedisQueue.job_channel_name}:{job_id}", data)

                    except Exception as e:
                        # preparation of the result, containing error information
                        result = JobResult(id=job_id, data=str(e), content_type="text")
                        result.worker_id = self.info.id
                        result.worker_host_name = socket.gethostname()
                        data = pickle.dumps(result)

                        # we inform, that the job has failed with errors
                        # self.set_job_runtime_status(job_id, p, Status.FAILURE.value,
                        # start_time)

                        # we publish the result to any subscribers
                        p.publish(f"{RedisQueue.job_channel_name}:{job_id}", data)

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

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if not args.redis_url:
        raise AssertionError(
            "no redis host specified: start qgis-server-light with '--redis-url <QSL_REDIS_URL>'"
        )

    svg_paths = args.svg_path.split(":")
    engine = RedisEngine(
        EngineContext(args.data_root),
        [
            "qgis_server_light.worker.runner.render.RenderRunner",
            "qgis_server_light.worker.runner.feature.GetFeatureRunner",
            # Not fully functional yet
            # "qgis_server_light.worker.runner.feature_info.GetFeatureInfoRunner",
        ],
        svg_paths=svg_paths,
    )
    engine.run(
        args.redis_url,
    )


if __name__ == "__main__":
    main()
