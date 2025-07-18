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

from qgis_server_light.interface.job import JobError
from qgis_server_light.interface.job import JobRunnerInfoQslGetFeatureInfoJob
from qgis_server_light.interface.job import JobRunnerInfoQslGetMapJob
from qgis_server_light.interface.job import JobRunnerInfoQslLegendJob
from qgis_server_light.worker.engine import Engine
from qgis_server_light.worker.engine import EngineContext


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

        while True:
            r = redis.Redis.from_url(redis_url)

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
                _, job_info_json = r.blpop("jobs")
                job_info_dict = json.loads(job_info_json)
                if JobRunnerInfoQslGetMapJob.__name__ == job_info_dict["type"]:
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslGetMapJob
                    )
                elif (
                    JobRunnerInfoQslGetFeatureInfoJob.__name__ == job_info_dict["type"]
                ):
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslGetFeatureInfoJob
                    )
                elif JobRunnerInfoQslLegendJob.__name__ == job_info_dict["type"]:
                    job_info = JsonParser().from_bytes(
                        job_info_json, JobRunnerInfoQslLegendJob
                    )
                else:

                    raise NotImplementedError(
                        f'type {job_info_dict["type"]} is not supported by qgis-server-light'
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

            p = r.pipeline()
            p.hset(key, "status", "running")
            p.hset(key, "timestamp", datetime.datetime.now().isoformat())
            result = None
            try:
                start_time = time.time()
                result = self.process(job_info.job)
                p.hset(key, "content_type", result.content_type)
                p.hset(key, "data", bytes(result.data))
                p.hset(key, "status", "succeed")
                duration = time.time() - start_time
                p.hset(key, "duration", duration)
                p.hset(key, "timestamp", datetime.datetime.now().isoformat())
                logging.debug(f"duration of rendering: {duration}")
            except Exception as e:
                p.hset(key, "status", "failed")
                p.hset(key, "error", f"{e}")
                p.hset(key, "timestamp", datetime.datetime.now().isoformat())
                logging.error(e, exc_info=True)
                logging.debug("Job Failed")
            finally:

                if p.hget(key, "error") == "failed":
                    data = pickle.dumps(result)
                else:
                    data = pickle.dumps(
                        JobError(
                            error=p.hget(key, "error"),
                            duration=p.hget(key, "duration"),
                            status=p.hget(key, "status"),
                            timestamp=p.hget(key, "timestamp"),
                        )
                    )
                p.publish(f"notifications:{key}", data)
                p.execute()


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--redis-url",
        type=str,
        help="redis url",
        default=os.environ.get("QSL_REDIS_URL"),
    )

    parser.add_argument(
        "--log-level",
        type=str,
        help="log level (debug, info, warning or error)",
        default=os.environ.get("QSL_LOG_LEVEL") or "info",
    )

    parser.add_argument(
        "--data-root",
        type=str,
        help="Absolute path to the data dir.",
        default=os.environ.get("QSL_DATA_ROOT") or "/io/data",
    )

    parser.add_argument(
        "--svg-path",
        type=str,
        help="Absolute path to additional svg files. Multiple paths can be separated by `:`. Defaults to /io/svg",
        default=os.environ.get("QSL_SVG_PATH") or "/io/svg",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s [%(levelname)s] %(message)s"
    )

    log = logging.getLogger(__name__)
    log.info(json.dumps(dict(os.environ), indent=2))

    if not args.redis_url:
        raise AssertionError("no redis host specified (--redis-url, QSL_REDIS_URL)")

    svg_paths = args.svg_path.split(":")
    engine = RedisEngine(EngineContext(args.data_root), svg_paths)
    engine.run(
        args.redis_url,
    )


if __name__ == "__main__":
    main()
