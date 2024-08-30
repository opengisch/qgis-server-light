import asyncio
import datetime
import logging
import pickle
from uuid import uuid4

import async_timeout
import redis.asyncio as redis
from qgis_server_light.interface.job import JobResult, QslGetMapJob, QslGetFeatureInfoJob, QslLegendJob, \
    JobRunnerInfoQslGetMapJob, JobRunnerInfoQslGetFeatureInfoJob, JobRunnerInfoQslLegendJob
from xsdata.formats.dataclass.serializers import JsonSerializer


class RedisQueue:
    def __init__(self, url: str) -> None:
        self.pool = redis.BlockingConnectionPool.from_url(url)

    async def post(
            self,
            job: QslGetMapJob | QslGetFeatureInfoJob | QslLegendJob,
            timeout: float = 10
    ) -> JobResult:
        """
        Posts a new `job` to the job queue and waits maximum `timeout` seconds to complete.
        Will return a JobResult if successful or raise an error.
        """
        r = await redis.Redis(connection_pool=self.pool)
        job_id = str(uuid4())
        creation_time = datetime.datetime.now().isoformat()
        datetime.datetime.now()
        if isinstance(job, QslGetMapJob):
            job = JobRunnerInfoQslGetMapJob(
                id=job_id,
                type=JobRunnerInfoQslGetMapJob.__name__,
                job=job
            )
        elif isinstance(job, QslGetFeatureInfoJob):
            job = JobRunnerInfoQslGetFeatureInfoJob(
                id=job_id,
                type=JobRunnerInfoQslGetFeatureInfoJob.__name__,
                job=job
            )
        elif isinstance(job, QslLegendJob):
            job = JobRunnerInfoQslLegendJob(
                id=job_id,
                type=JobRunnerInfoQslLegendJob.__name__,
                job=job
            )
        async with r.pipeline() as p:
            logging.info(f"{job_id} pushed")
            p.rpush("jobs", JsonSerializer().render(job))
            p.hset(job_id, "status", "queued")
            p.hset(job_id, "timestamp", creation_time)
            await p.execute()

            async with r.pubsub() as ps:
                await ps.subscribe(f"notifications:{job_id}")
                try:
                    async with async_timeout.timeout(timeout):
                        while True:
                            message = await ps.get_message(
                                timeout=timeout, ignore_subscribe_messages=True
                            )
                            if not message:
                                continue  # https://github.com/redis/redis-py/issues/733
                            # TODO: handle errors
                            logging.info(f"{job_id} succeeded")
                            result = pickle.loads(message["data"])
                            await asyncio.create_task(r.delete(job_id))
                            return result
                except (asyncio.TimeoutError, asyncio.exceptions.CancelledError) as err:
                    logging.info(f"{job_id} timeout")
                    await r.delete(job_id)
                    raise
