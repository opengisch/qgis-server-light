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
from qgis_server_light.interface.dispatcher.protocol import RedisProtocol
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
        self.heartbeat_interval = RedisProtocol.worker_heartbeat_interval
        self.heartbeat_thread = None
        self.redis_client: Redis | None = None

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
        if self.redis_client is not None:
            self.unregister_worker(self.redis_client)
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
        """Tells redis that this worker is still alive. The worker info gets its
        expiry renewed at the same time, so it only vanishes when the worker stops
        beating.

        Args:
            client: The redis client.

        Returns:
            The UTC timestamp which was written as last seen.
        """
        now = datetime.datetime.now(datetime.UTC)
        pipeline = client.pipeline()
        # writing the full worker info with every beat, so it is back after redis lost
        # its keys (restart, flush, eviction) and it carries the current status
        pipeline.hset(
            RedisProtocol.worker_key(self.info.id),
            mapping={
                RedisProtocol.worker_info_key: JsonSerializer().render(self.info),
                RedisProtocol.worker_last_seen_key: now.isoformat(),
            },
        )
        # renewing the timer, otherwise the worker info expires while the worker is alive
        pipeline.expire(RedisProtocol.worker_key(self.info.id), self.info_expire)
        pipeline.sadd(RedisProtocol.worker_list_name, self.info.id)
        pipeline.execute()
        return now

    def register_worker(self, client: Redis):
        """Makes this worker known in redis and cleans up behind workers which vanished
        without unregistering. This way the list of workers heals itself with every
        worker start.

        Args:
            client: The redis client.
        """
        self.prune_vanished_workers(client)
        # the first beat writes the worker info and adds the worker to the list
        self.heartbeat(client)
        logging.info("Worker was registered in Redis")

    @staticmethod
    def prune_vanished_workers(client: Redis):
        # removing workers from the list which vanished without unregistering (e.g. killed),
        # their info expired already
        for worker_id in client.smembers(RedisProtocol.worker_list_name):
            if not client.exists(RedisProtocol.worker_key(worker_id)):
                client.srem(RedisProtocol.worker_list_name, worker_id)

    def unregister_worker(self, client: Redis):
        """Removes this worker from redis on a graceful shutdown. If redis is gone
        already, the worker does not insist: its info expires and the next registering
        worker cleans the list.

        Args:
            client: The redis client.
        """
        try:
            client.srem(RedisProtocol.worker_list_name, self.info.id)
            client.delete(RedisProtocol.worker_key(self.info.id))
        except (RedisConnectionError, TimeoutError) as e:
            # the info expires on its own, the next registering worker cleans the list
            logging.warning(f"Worker could not be unregistered from Redis: {e}")
        else:
            logging.info("Worker was unregistered from Redis")

    def retry_connection(self, redis_url: str, count: int):
        logging.warning(f"Could not connect to redis on `{redis_url}`.")
        self.retry_handling_with_jitter(count)

    def start(self, redis_url) -> Redis:
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        r = Redis.from_url(redis_url, decode_responses=True, retry=Retry(ExponentialBackoff(), 0))
        self.wait_for_connection(r, redis_url)
        return r

    def wait_for_connection(self, client: Redis, redis_url: str):
        # the retries are counted per outage, so only one long outage makes the worker
        # give up and not the sum of all short ones
        retry_count = 0
        while True:
            try:
                retry_count += 1
                logging.debug(f"Looking up redis: {redis_url}")
                client.ping()
            except (RedisConnectionError, TimeoutError) as e:
                logging.debug(f"Connection on Redis not successful => {e}")
                self.retry_connection(redis_url, retry_count)
            else:
                break
        logging.info(f"Connection to redis on `{redis_url}`successful.")

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
        self.redis_client = r
        # Starte Heartbeat-Worker
        self.start_heartbeat_worker(r)
        try:
            self.serve_jobs(r, p, redis_url)
        except Exception:
            self.report_crash(r)
            raise
        exit(0)

    def report_crash(self, client: Redis):
        self.set_crashed()
        try:
            # beating once more right away, the process might be gone before the
            # heartbeat thread gets its next turn
            self.heartbeat(client)
        except (RedisConnectionError, TimeoutError) as e:
            logging.warning(f"Crash could not be reported to Redis: {e}")

    def serve_jobs(self, r: Redis, p: Pipeline, redis_url: str):
        while not self.shutdown:
            try:
                logging.debug("Waiting for jobs")
                self.set_waiting()
                # this is blocking the loop until a job is found in the redis
                # list/queue, if there is one we take it
                result = r.blpop([RedisProtocol.job_queue_name], timeout=0)
                if result is not None:
                    _, job_id = result
                    self.set_processing()
                    start_time = time.time()
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
                        result.worker_id = self.info.id
                        result.worker_host_name = socket.gethostname()
                        data = pickle.dumps(result)

                        # we inform, that the job was finished successful
                        self.set_job_runtime_status(job_id, p, Status.SUCCESS.value, start_time)

                        # we publish the result to any subscribers
                        p.publish(RedisProtocol.channel(job_id), data)

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
                        p.publish(RedisProtocol.channel(job_id), data)

                        # we provide error information to the logs
                        logging.error(e, exc_info=True)
                    finally:
                        p.execute()
                    logging.debug(f"Job duration: {time.time() - start_time}")
            except (RedisConnectionError, TimeoutError) as _:
                self.wait_for_connection(r, redis_url)
                continue


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
            "qgis_server_light.worker.runner.legend.GetLegendRunner",
            "qgis_server_light.worker.runner.feature.GetFeatureRunner",
            "qgis_server_light.worker.runner.crs.CrsRunner",
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
