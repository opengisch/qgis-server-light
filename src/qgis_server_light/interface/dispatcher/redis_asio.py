"""This contains the interface definition about how a job info
is passed around a redis queue.

"""

import asyncio
import datetime
import logging
import pickle
import time
from asyncio import timeout
from uuid import uuid4

from redis import asyncio as redis_aio
from redis.client import Pipeline
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.dispatcher.common import Status
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.feature.input import (
    QslJobInfoFeature,
    QslJobParameterFeature,
)
from qgis_server_light.interface.job.feature_info.input import (
    QslJobInfoFeatureInfo,
    QslJobParameterFeatureInfo,
)
from qgis_server_light.interface.job.legend.input import (
    QslJobInfoLegend,
    QslJobParameterLegend,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)


class RedisQueue:
    job_queue_name: str = "jobs"
    job_info_key: str = "info"
    job_info_type_key: str = "info_type"
    job_channel_name: str = "notifications"
    job_status_key: str = "status"
    job_duration_key: str = "duration"
    job_timestamp_key: str = "timestamp"
    job_last_update_key: str = f"{job_timestamp_key}.last_update"

    def __init__(self, redis_client: redis_aio.Redis) -> None:
        # we use this to hold connections to redis in a pool, this way we are
        # event loop safe and when creating the redis client for every call of
        # post, we only instantiate a minimal wrapper object which is cheap.

        self.client = redis_client

    @classmethod
    def create(cls, url: str):
        redis_client = redis_aio.Redis.from_url(url)
        return cls(redis_client)

    async def set_job_runtime_status(
        self,
        job_id,
        pipeline: Pipeline,
        status: str,
        start_time: float,
    ):
        duration = time.time() - start_time
        ts = datetime.datetime.now().isoformat()
        await pipeline.hset(f"job:{job_id}", self.job_status_key, status)
        await pipeline.hset(
            f"job:{job_id}",
            f"{self.job_timestamp_key}.{status}",
            ts,
        )
        await pipeline.hset(f"job:{job_id}", self.job_last_update_key, ts)
        await pipeline.hset(f"job:{job_id}", self.job_duration_key, str(duration))
        await pipeline.execute()

    async def post(
        self,
        job_parameter: (
            QslJobParameterRender
            | QslJobParameterFeatureInfo
            | QslJobParameterLegend
            | QslJobParameterFeature
        ),
        to: float = 10.0,
    ) -> tuple[JobResult, str]:
        """
        Posts a new `runner` to the runner queue and waits maximum `timeout` seconds to complete.
        Will return a JobResult if successful or raise an error.

        Args:
            job_parameter: The parameter for the job which should be executed.
            to: The timeout a job is expected to be waited for before canceling
                job execution.
        """
        job_id = str(uuid4())
        start_time = time.time()
        if isinstance(job_parameter, QslJobParameterRender):
            job_info = QslJobInfoRender(
                id=job_id, type=QslJobInfoRender.__name__, job=job_parameter
            )
        elif isinstance(job_parameter, QslJobParameterFeatureInfo):
            job_info = QslJobInfoFeatureInfo(
                id=job_id, type=QslJobParameterFeatureInfo.__name__, job=job_parameter
            )
        elif isinstance(job_parameter, QslJobParameterLegend):
            job_info = QslJobInfoLegend(
                id=job_id, type=QslJobInfoLegend.__name__, job=job_parameter
            )
        elif isinstance(job_parameter, QslJobParameterFeature):
            job_info = QslJobInfoFeature(
                id=job_id, type=QslJobInfoFeature.__name__, job=job_parameter
            )
        else:
            return (
                JobResult(
                    id=job_id,
                    data=f"Unsupported runner type: {type(job_parameter)}",
                    content_type="application/text",
                ),
                Status.FAILURE.value,
            )
        async with self.client.pipeline() as p:
            # Putting job info into redis
            await p.hset(f"job:{job_id}", self.job_info_key, JsonSerializer().render(job_info))
            await p.hset(f"job:{job_id}", self.job_info_type_key, job_info.__class__.__name__)
            # Queuing the job onto the list/queue
            await p.rpush(self.job_queue_name, job_id)
            await p.execute()

            logging.info(f"{job_id} queued")

            # we inform, that the job was queued
            await self.set_job_runtime_status(job_id, p, Status.QUEUED.value, start_time)
            try:
                async with self.client.pubsub() as ps:
                    # we tell redis to let us know if a message is published
                    # for this channel `notifications:{job_id}`.
                    await ps.subscribe(f"{self.job_channel_name}:{job_id}")
                    try:
                        # this puts a timeout trigger on the subscription, after timeout
                        # an asyncio.TimeoutError or asyncio.exceptions.CancelledError
                        # is raised. See except block below.
                        async with timeout(to):
                            while True:
                                message = await ps.get_message(
                                    timeout=to, ignore_subscribe_messages=True
                                )
                                if not message:
                                    continue  # https://github.com/redis/redis-py/issues/733
                                status_binary = await self.client.hget(f"job:{job_id}", "status")
                                status = status_binary.decode()
                                result: JobResult = pickle.loads(message["data"])
                                duration = time.time() - start_time
                                if status == Status.SUCCESS.value:
                                    logging.info(
                                        f"Job id: {job_id}, status: {status}, duration: {duration}"
                                    )
                                elif status == Status.FAILURE.value:
                                    logging.info(
                                        f"Job id: {job_id}, status: {status}, "
                                        f"duration: {duration}, error: {result.data}"
                                    )
                                return result, status
                    except (TimeoutError, asyncio.exceptions.CancelledError):
                        logging.info(f"{job_id} timeout")
                        raise
            except Exception as e:
                duration = time.time() - start_time
                logging.info(
                    f"Job id: {job_id}, status: {Status.FAILURE.value}, duration: {duration}",
                    exc_info=True,
                )
                return (
                    JobResult(
                        id=job_id,
                        data=str(e),
                        content_type="application/text",
                    ),
                    Status.FAILURE.value,
                )
            finally:
                try:
                    await self.client.delete(f"job:{job_id}")
                except Exception:
                    logging.warning(
                        f"Cleanup failed for {job_id}",
                        exc_info=True,
                    )
