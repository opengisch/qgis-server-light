import asyncio
import datetime
import logging
import pickle
import sys
import time
from enum import Enum
from uuid import uuid4

import redis.asyncio as redis
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.job import JobResult
from qgis_server_light.interface.job import JobRunnerInfoQslGetFeatureInfoJob
from qgis_server_light.interface.job import JobRunnerInfoQslGetFeatureJob
from qgis_server_light.interface.job import JobRunnerInfoQslGetMapJob
from qgis_server_light.interface.job import JobRunnerInfoQslLegendJob
from qgis_server_light.interface.job import QslGetFeatureInfoJob
from qgis_server_light.interface.job import QslGetFeatureJob
from qgis_server_light.interface.job import QslGetMapJob
from qgis_server_light.interface.job import QslLegendJob

if sys.version_info >= (3, 11):
    from asyncio import timeout as async_to
else:
    from async_timeout import timeout as async_to


class Status(Enum):
    SUCCESS = "succeed"
    FAILURE = "failed"
    RUNNING = "running"
    QUEUED = "queued"


class RedisQueue:
    def __init__(
        self, pool: redis.BlockingConnectionPool, redis_client: redis.Redis
    ) -> None:
        # we use this to hold connections to redis in a pool, this way we are
        # event loop safe and when creating the redis client for every call of
        # post, we only instantiate a minimal wrapper object which is cheap.
        self.pool = pool
        self.client = redis_client

    @classmethod
    async def create(cls, url: str):
        pool = redis.BlockingConnectionPool.from_url(url)
        redis_client = await redis.Redis(connection_pool=pool)
        return cls(pool, redis_client)

    async def post(
        self,
        job: QslGetMapJob | QslGetFeatureInfoJob | QslLegendJob | QslGetFeatureJob,
        timeout: float = 10,
    ) -> JobResult:
        """
        Posts a new `job` to the job queue and waits maximum `timeout` seconds to complete.
        Will return a JobResult if successful or raise an error.
        """
        job_id = str(uuid4())
        creation_time = datetime.datetime.now().isoformat()
        start_time = time.time()
        if isinstance(job, QslGetMapJob):
            job = JobRunnerInfoQslGetMapJob(
                id=job_id, type=JobRunnerInfoQslGetMapJob.__name__, job=job
            )
        elif isinstance(job, QslGetFeatureInfoJob):
            job = JobRunnerInfoQslGetFeatureInfoJob(
                id=job_id, type=JobRunnerInfoQslGetFeatureInfoJob.__name__, job=job
            )
        elif isinstance(job, QslLegendJob):
            job = JobRunnerInfoQslLegendJob(
                id=job_id, type=JobRunnerInfoQslLegendJob.__name__, job=job
            )
        elif isinstance(job, QslGetFeatureJob):
            job = JobRunnerInfoQslGetFeatureJob(
                id=job_id, type=JobRunnerInfoQslGetFeatureJob.__name__, job=job
            )
        else:
            raise TypeError(f"Unsupported job type: {type(job)}")
        async with self.client.pipeline() as p:
            logging.info(f"{job_id} pushed")
            await p.rpush("jobs", JsonSerializer().render(job))
            await p.hset(job_id, "status", Status.QUEUED.value)
            await p.hset(job_id, f"timestamp.{Status.QUEUED.value}", creation_time)
            await p.hset(job_id, "timestamp", creation_time)
            await p.execute()

            async with self.client.pubsub() as ps:
                await ps.subscribe(f"notifications:{job_id}")
                try:
                    async with async_to(timeout):
                        while True:
                            message = await ps.get_message(
                                timeout=timeout, ignore_subscribe_messages=True
                            )
                            if not message:
                                continue  # https://github.com/redis/redis-py/issues/733
                            status_binary = await self.client.hget(job_id, "status")
                            status = status_binary.decode()
                            logging.info(f"Job {job_id} {status}")
                            if status == Status.SUCCESS.value:
                                result = pickle.loads(message["data"])
                                await asyncio.create_task(self.client.delete(job_id))
                                duration = time.time() - start_time
                                logging.debug(f"duration of job execution: {duration}")
                                return result
                            elif status == Status.FAILURE.value:
                                error = await self.client.hget(job_id, "error")
                                logging.error(
                                    f"Job {job_id} {status} with: {error.decode()}"
                                )
                                raise RuntimeError()
                except (asyncio.TimeoutError, asyncio.exceptions.CancelledError) as err:
                    logging.info(f"{job_id} timeout")
                    await self.client.delete(job_id)
                    raise
