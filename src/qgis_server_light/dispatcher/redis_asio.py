"""This contains the dispatcher which passes a job info around a redis queue."""

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
from qgis_server_light.interface.dispatcher.protocol import RedisProtocol
from qgis_server_light.interface.job.common.input import QslJobInfoParameter, QslJobParameter
from qgis_server_light.interface.job.common.output import JobResult
from qgis_server_light.interface.job.crs.input import (
    QslJobInfoCrs,
    QslJobParameterCrs,
)
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

job_info_classes: dict[type[QslJobParameter], type[QslJobInfoParameter]] = {
    QslJobParameterRender: QslJobInfoRender,
    QslJobParameterFeatureInfo: QslJobInfoFeatureInfo,
    QslJobParameterLegend: QslJobInfoLegend,
    QslJobParameterFeature: QslJobInfoFeature,
    QslJobParameterCrs: QslJobInfoCrs,
}


def derive_job_info(job_id: str, job_parameter: QslJobParameter) -> QslJobInfoParameter:
    """Wraps the job parameter into the job info matching its type.

    Args:
        job_id: The unique identifier of the job.
        job_parameter: The parameter for the job which should be executed.

    Raises:
        TypeError: If there is no job info for the type of the job parameter.
    """
    job_info_class = job_info_classes.get(type(job_parameter))
    if job_info_class is None:
        raise TypeError(f"Unsupported runner type: {type(job_parameter)}")
    return job_info_class(id=job_id, type=job_info_class.__name__, job=job_parameter)


class RedisQueue(RedisProtocol):
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
        await pipeline.hset(self.job_key(job_id), self.job_status_key, status)
        await pipeline.hset(
            self.job_key(job_id),
            f"{self.job_timestamp_key}.{status}",
            ts,
        )
        await pipeline.hset(self.job_key(job_id), self.job_last_update_key, ts)
        await pipeline.hset(self.job_key(job_id), self.job_duration_key, str(duration))
        await pipeline.execute()

    async def post(
        self,
        job_parameter: (
            QslJobParameterRender
            | QslJobParameterFeatureInfo
            | QslJobParameterLegend
            | QslJobParameterFeature
            | QslJobParameterCrs
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
        try:
            job_info = derive_job_info(job_id, job_parameter)
        except TypeError as e:
            return (
                JobResult(
                    id=job_id,
                    data=str(e),
                    content_type="application/text",
                ),
                Status.FAILURE.value,
            )
        async with self.client.pipeline() as p:
            # Putting job info into redis
            await p.hset(self.job_key(job_id), self.job_info_key, JsonSerializer().render(job_info))
            await p.hset(self.job_key(job_id), self.job_info_type_key, job_info.__class__.__name__)
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
                    await ps.subscribe(self.channel(job_id))
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
                                status_binary = await self.client.hget(
                                    self.job_key(job_id), self.job_status_key
                                )
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
                    await self.client.delete(self.job_key(job_id))
                except Exception:
                    logging.warning(
                        f"Cleanup failed for {job_id}",
                        exc_info=True,
                    )
