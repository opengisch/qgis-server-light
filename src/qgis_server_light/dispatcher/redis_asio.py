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
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.dispatcher.common import Status, Worker
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
from qgis_server_light.interface.worker.info import EngineInfo
from qgis_server_light.interface.worker.info import Status as WorkerStatus

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

    async def is_reachable(self) -> bool:
        """Pings redis. The caller only needs to know whether jobs could be queued, so
        the redis exceptions stay in here and are logged.

        Returns:
            True if redis answered, False if it could not be reached.
        """
        try:
            return await self.client.ping()
        except (RedisConnectionError, RedisTimeoutError) as e:
            logging.warning(f"Redis is not reachable: {e}")
            return False

    async def registered_workers(self) -> list[Worker]:
        """Collects every worker redis still knows, no matter how old its last heartbeat
        is. This way crashed or silently vanished workers can be shown until their info
        expires, the consumer tells them apart by `info.status` and `last_seen`.

        Returns:
            The registered workers, sorted by their id to give a stable order.
        """
        workers = []
        for worker_id in sorted(await self.client.smembers(self.worker_list_name)):
            last_seen = await self.client.hget(
                self.worker_key(worker_id.decode()), self.worker_last_seen_key
            )
            info = await self.client.hget(self.worker_key(worker_id.decode()), self.worker_info_key)
            if last_seen is None or info is None:
                # the worker vanished, its info expired already
                continue
            workers.append(
                Worker(
                    id=worker_id.decode(),
                    last_seen=self.parse_last_seen(last_seen),
                    info=JsonParser().from_bytes(info, EngineInfo),
                )
            )
        return workers

    async def alive_workers(self) -> list[Worker]:
        """Collects the workers which sent a heartbeat within `worker_alive_age` and did
        not crash. Workers which are still registered but stopped beating (e.g. killed)
        or reported a crash are left out, so the result tells who is really there to
        process jobs.

        Returns:
            The alive workers, sorted by their id to give a stable order.
        """
        now = datetime.datetime.now(datetime.UTC)
        alive_age = datetime.timedelta(seconds=self.worker_alive_age)
        return [
            worker
            for worker in await self.registered_workers()
            if now - worker.last_seen <= alive_age and worker.info.status != WorkerStatus.CRASHED
        ]

    @staticmethod
    def parse_last_seen(last_seen: bytes) -> datetime.datetime:
        """Reads the heartbeat timestamp of a worker as it is stored in redis.

        Args:
            last_seen: The ISO timestamp as redis returns it.

        Returns:
            The timezone aware timestamp, naive ones are taken as UTC.
        """
        timestamp = datetime.datetime.fromisoformat(last_seen.decode())
        if timestamp.tzinfo is None:
            # workers before the UTC heartbeat wrote their local time without offset, in
            # containers this is UTC usually
            timestamp = timestamp.replace(tzinfo=datetime.UTC)
        return timestamp

    async def set_job_runtime_status(
        self,
        job_id,
        pipeline: Pipeline,
        status: str,
        start_time: float,
        execute: bool = True,
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
        if execute:
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
        try:
            async with self.client.pubsub() as ps:
                # We subscribe to `notifications:{job_id}` *before* the job is
                # queued. Redis pub/sub does not buffer messages, so a fast job
                # (e.g. a legend) could otherwise be published by the worker
                # before we listen, and its result would be lost.
                await ps.subscribe(self.channel(job_id))
                async with self.client.pipeline() as p:
                    # Putting job info into redis
                    await p.hset(
                        self.job_key(job_id), self.job_info_key, JsonSerializer().render(job_info)
                    )
                    await p.hset(
                        self.job_key(job_id), self.job_info_type_key, job_info.__class__.__name__
                    )
                    # we inform, that the job was queued. This happens in the same
                    # transaction as the queuing, so it can not overwrite a status
                    # already set by the worker.
                    await self.set_job_runtime_status(
                        job_id, p, Status.QUEUED.value, start_time, execute=False
                    )
                    # Queuing the job onto the list/queue
                    await p.rpush(self.job_queue_name, job_id)
                    await p.execute()

                logging.info(f"{job_id} queued")
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
