import argparse
import datetime
import json
import logging
import math
import os
import pickle
import signal
import time
from typing import List
from typing import Optional

import redis
from xsdata.formats.dataclass.parsers import JsonParser

from qgis_server_light.interface.dispatcher import Status
from qgis_server_light.interface.job import JobRunnerInfoQslGetFeatureInfoJob
from qgis_server_light.interface.job import JobRunnerInfoQslGetFeatureJob
from qgis_server_light.interface.job import JobRunnerInfoQslGetMapJob
from qgis_server_light.interface.job import JobRunnerInfoQslLegendJob
from qgis_server_light.worker.engine import Engine
from qgis_server_light.worker.engine import EngineContext

DEFAULT_DATA_ROOT = "/io/data"
DEFAULT_SVG_PATH = "/io/svg"


class RedisEngine(Engine):
    def __init__(
        self, context: EngineContext, svg_paths: Optional[List] = None
    ) -> None:
        super().__init__(context, svg_paths)
        self.shutdown = False

    def exit_gracefully(self, signum, frame):
        print("Received:", signum)
        self.shutdown = True
        # actually exit the programm (for some reason it is not working with the shutdown switch)
        exit(0)

    def run(self, redis_url):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        r = redis.Redis.from_url(redis_url)
        p = r.pipeline()
        while True:
            try:
                r.ping()
            except redis.exceptions.ConnectionError:
                logging.warning(
                    f"Could not connect to redis on `{redis_url}`, trying again in 1 second"
                )
                time.sleep(1)
            else:
                break
        logging.info(f"Connection to redis on `{redis_url}`successful.")
        while not self.shutdown:
            retry_count = 0
            try:
                logging.debug(f"Waiting for jobs")
                # this is blocking the loop until a job is found in the redis queue
                _, job_info_json = r.blpop(["jobs"])

                if (
                    f'"type": "{JobRunnerInfoQslGetMapJob.__name__}"'.encode()
                    in job_info_json
                ):
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslGetMapJob
                    )
                elif (
                    f'"type": "{JobRunnerInfoQslGetFeatureInfoJob.__name__}"'.encode()
                    in job_info_json
                ):
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslGetFeatureInfoJob
                    )
                elif (
                    f'"type": "{JobRunnerInfoQslLegendJob.__name__}"'.encode()
                    in job_info_json
                ):
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslLegendJob
                    )
                elif (
                    f'"type": "{JobRunnerInfoQslGetFeatureJob.__name__}"'.encode()
                    in job_info_json
                ):
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslGetFeatureJob
                    )
                else:
                    raise NotImplementedError(
                        f"Type of job not supported by qgis-server-light. {job_info_json}"
                    )
                logging.debug(
                    f"Job info received: id: {job_info.id}, type: {job_info.type}"
                )
            except Exception as e:
                # TODO handle known exceptions like redis.exceptions.ConnectionError separately
                retry_count += 1
                logging.error(e, exc_info=True)
                retry_rate = math.pow(2, retry_count) * 0.01
                logging.warning(f"Retrying in {retry_rate} seconds...")
                time.sleep(retry_rate)
                continue
            key = job_info.id

            p.hset(key, "status", Status.RUNNING.value)
            p.hset(
                key,
                f"timestamp.{Status.RUNNING.value}",
                datetime.datetime.now().isoformat(),
            )
            p.hset(key, "timestamp", datetime.datetime.now().isoformat())
            p.execute()
            try:
                start_time = time.time()
                result = self.process(job_info.job)
                data = pickle.dumps(result)
                p.publish(f"notifications:{key}", data)
                p.hset(key, "content_type", result.content_type)
                p.hset(key, "status", Status.SUCCESS.value)
                duration = time.time() - start_time
                p.hset(key, "duration", str(duration))
                p.hset(
                    key,
                    f"timestamp.{Status.SUCCESS.value}",
                    datetime.datetime.now().isoformat(),
                )
                p.hset(key, "timestamp", datetime.datetime.now().isoformat())
                logging.debug(f"duration of rendering: {duration}")
            except Exception as e:
                p.hset(key, "status", Status.FAILURE.value)
                p.hset(key, "error", f"{e}")
                p.publish(f"notifications:{key}", 0)
                p.hset(
                    key,
                    f"timestamp.{Status.FAILURE.value}",
                    datetime.datetime.now().isoformat(),
                )
                p.hset(key, "timestamp", datetime.datetime.now().isoformat())
                logging.error(e, exc_info=True)
            finally:
                p.execute()


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
        help=f"Absolute path to additional svg files. Multiple paths can be separated by `:`. Defaults to {DEFAULT_SVG_PATH}",
        default=DEFAULT_SVG_PATH,
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s [%(levelname)s] %(message)s"
    )

    log = logging.getLogger(__name__)
    log.info(json.dumps(dict(os.environ), indent=2))

    if not args.redis_url:
        raise AssertionError(
            "no redis host specified: start qgis-server-light with '--redis-url <QSL_REDIS_URL>'"
        )

    svg_paths = args.svg_path.split(":")
    engine = RedisEngine(EngineContext(args.data_root), svg_paths)
    engine.run(
        args.redis_url,
    )


if __name__ == "__main__":
    main()
