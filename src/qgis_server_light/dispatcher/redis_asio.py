"""This contains the dispatcher which passes a job info around a redis queue."""

import asyncio
import datetime
import logging
import pickle
import time
from asyncio import timeout
from typing import ClassVar
from uuid import uuid4

from redis import asyncio as redis_aio
from redis.asyncio.client import PubSub
from redis.client import Pipeline
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.dispatcher.common import JobState, Status
from qgis_server_light.interface.dispatcher.protocol import (
    RedisProtocol,
    RedisPublishProtocol,
    RedisStateProtocol,
)
from qgis_server_light.interface.job.common.input import (
    ExecutionMode,
    QslJobInfoParameter,
    QslJobParameter,
)
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
from qgis_server_light.interface.job.process.description import ProcessDescriptions
from qgis_server_light.interface.job.process.input import (
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)


class RedisDispatcher(RedisProtocol):
    job_info_classes: ClassVar[dict[type[QslJobParameter], type[QslJobInfoParameter]]] = {
        QslJobParameterRender: QslJobInfoRender,
        QslJobParameterFeatureInfo: QslJobInfoFeatureInfo,
        QslJobParameterLegend: QslJobInfoLegend,
        QslJobParameterFeature: QslJobInfoFeature,
        QslJobParameterCrs: QslJobInfoCrs,
        QslJobParameterExecuteProcess: QslJobInfoExecuteProcess,
    }

    def __init__(self, redis_client: redis_aio.Redis) -> None:
        # we use this to hold connections to redis in a pool, this way we are
        # event loop safe and when creating the redis client for every call of
        # post, we only instantiate a minimal wrapper object which is cheap.

        self.client = redis_client

    @classmethod
    def create(cls, url: str):
        redis_client = redis_aio.Redis.from_url(url)
        return cls(redis_client)

    @classmethod
    def derive_job_info(cls, job_id: str, job_parameter: QslJobParameter) -> QslJobInfoParameter:
        """Wraps the job parameter into the job info matching its type.

        Args:
            job_id: The unique identifier of the job.
            job_parameter: The parameter for the job which should be executed.

        Raises:
            TypeError: If there is no job info for the type of the job parameter.
        """
        job_info_class = cls.job_info_classes.get(type(job_parameter))
        if job_info_class is None:
            raise TypeError(f"Unsupported runner type: {type(job_parameter)}")
        return job_info_class(
            id=job_id,
            type=job_info_class.__name__,
            job=job_parameter,
        )

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

    async def queue_job(
        self, job_info: QslJobInfoParameter, pipeline: Pipeline, start_time: float
    ) -> None:
        # Putting job info into redis
        await pipeline.hset(
            self.job_key(job_info.id), self.job_info_key, JsonSerializer().render(job_info)
        )
        await pipeline.hset(
            self.job_key(job_info.id), self.job_info_type_key, job_info.__class__.__name__
        )
        # we inform, that the job was queued. This happens in the same
        # transaction as the queuing, so it can not overwrite a status
        # already set by the worker.
        await self.set_job_runtime_status(
            job_info.id, pipeline, Status.QUEUED.value, start_time, execute=False
        )
        # Queuing the job onto the list/queue of the protocol
        await pipeline.rpush(self.queue_name(), job_info.id)


class RedisStateQueue(RedisDispatcher, RedisStateProtocol):
    async def process_descriptions(self) -> ProcessDescriptions:
        """The descriptions of the processes the process-workers serve, read from the
        process registry. Empty as long as no process-worker has booted."""
        registry_json = await self.client.get(self.process_registry_key)
        if registry_json is None:
            return ProcessDescriptions()
        return JsonParser().from_bytes(registry_json, ProcessDescriptions)

    async def submit(
        self,
        job_id: str,
        job_parameter: QslJobParameterExecuteProcess,
        execution_mode: ExecutionMode = ExecutionMode.ASYNC,
    ) -> None:
        job_info = self.derive_job_info(job_id, job_parameter)
        job_info.execution_mode = execution_mode
        async with self.client.pipeline() as p:
            await self.queue_job(job_info, p, time.time())
            await p.expire(self.job_key(job_id), self.job_expire)
            await p.execute()
        logging.info(f"{job_id} submitted")

    async def state(self, job_id: str) -> JobState | None:
        job_hash = await self.client.hgetall(self.job_key(job_id))
        if not job_hash:
            return None
        job_hash = {key.decode(): value for key, value in job_hash.items()}
        return JobState(
            id=job_id,
            status=Status(job_hash[self.job_status_key].decode()),
            last_update=self.decode_optional(job_hash.get(self.job_last_update_key)),
            result=self.job_result(job_id, job_hash),
            message=self.decode_optional(job_hash.get(self.job_message_key)),
        )

    @staticmethod
    def decode_optional(value: bytes | None) -> str | None:
        return value.decode() if value is not None else None

    def job_result(self, job_id: str, job_hash: dict[str, bytes]) -> JobResult | None:
        if self.job_result_key not in job_hash:
            return None
        return JobResult(
            id=job_id,
            data=job_hash[self.job_result_key],
            content_type=job_hash[self.job_result_content_type_key].decode(),
        )

    async def wait(self, job_id: str, to: float = 10.0) -> JobState | None:
        async with self.client.pubsub() as ps:
            # We subscribe before reading the state, so a notification published in
            # between is not lost.
            await ps.subscribe(self.channel(job_id))
            job_state = await self.state(job_id)
            if job_state is None or job_state.finished:
                return job_state
            await self.wait_for_notification(ps, job_id, to)
        return await self.state(job_id)

    @staticmethod
    async def wait_for_notification(ps: PubSub, job_id: str, to: float) -> None:
        try:
            async with timeout(to):
                while True:
                    message = await ps.get_message(timeout=to, ignore_subscribe_messages=True)
                    if message:
                        return
        except (TimeoutError, asyncio.exceptions.CancelledError):
            logging.info(f"{job_id} timeout")


class RedisQueue(RedisDispatcher, RedisPublishProtocol):
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
            job_info = self.derive_job_info(job_id, job_parameter)
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
                    await self.queue_job(job_info, p, start_time)
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
