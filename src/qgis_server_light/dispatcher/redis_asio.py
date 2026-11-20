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
from redis.exceptions import RedisError
from xsdata.formats.dataclass.parsers import JsonParser
from xsdata.formats.dataclass.serializers import JsonSerializer

from qgis_server_light.interface.dispatcher.common import JobState, Status, Worker
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
from qgis_server_light.interface.job.process.description import (
    ProcessDescription,
    ProcessDescriptions,
    ProcessWarning,
)
from qgis_server_light.interface.job.process.input import (
    QslJobInfoExecuteProcess,
    QslJobParameterExecuteProcess,
)
from qgis_server_light.interface.job.render.input import (
    QslJobInfoRender,
    QslJobParameterRender,
)
from qgis_server_light.interface.worker.info import EngineInfo, QgisInfo
from qgis_server_light.interface.worker.info import Status as WorkerStatus


class RedisDispatcher(RedisProtocol):
    """The common part of the dispatchers: the connection to redis and how a job
    is put into it. How the result comes back is up to the subclasses, they are
    combined with the matching protocol.

    Attributes:
        job_info_classes: The job info class per job parameter class, used to
            wrap a job parameter into its job info.
    """

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

    async def is_reachable(self) -> bool:
        """Pings redis. The caller only needs to know whether jobs could be queued, so
        the redis exceptions stay in here and are logged.

        Returns:
            True if redis answered, False if it could not be reached.
        """
        try:
            return await self.client.ping()
        except RedisError as e:
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
            last_seen, info = await self.client.hmget(
                self.worker_key(worker_id.decode()),
                [self.worker_last_seen_key, self.worker_info_key],
            )
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
        """Puts the job info into the job hash, sets the queued status and pushes
        the job id onto the queue of the protocol. Nothing is executed here, the
        caller adds what belongs to its protocol to the same transaction and
        executes it.

        Args:
            job_info: The job info of the job which should be queued.
            pipeline: The pipeline holding the transaction.
            start_time: The time the job was posted, used for the duration.
        """
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
    """The dispatcher for jobs which keep their state. A job is submitted and
    its state can be read at any time later, until the job hash expires. A
    caller who wants to wait for the result uses `wait`.
    """

    async def process_descriptions(self) -> ProcessDescriptions:
        """The descriptions of the processes the alive process-workers serve, each worker
        keeps its own in its hash. Empty as long as no process-worker is alive."""
        served = []
        for worker in await self.alive_workers():
            processes_json = await self.client.hget(
                self.worker_key(worker.id), self.worker_processes_key
            )
            if processes_json is None:
                # the worker serves no processes or redis lost them until its next beat
                continue
            process_descriptions = JsonParser().from_bytes(processes_json, ProcessDescriptions)
            served.append((worker.info.qgis_info, process_descriptions))
        return self.merge_process_descriptions(served)

    @staticmethod
    def merge_process_descriptions(
        served: list[tuple[QgisInfo, ProcessDescriptions]],
    ) -> ProcessDescriptions:
        """Merges the processes of several workers into one list. Workers on one redis
        should all run the same QGIS and serve the same processes. When they don't, the
        description of the newest QGIS is taken and the process gets a warning, so the
        deployment can be corrected.

        Args:
            served: The QGIS of each worker and the processes it serves.

        Returns:
            Each process once, with a warning for each process the workers don't agree on.
        """
        descriptions_by_process_id: dict[str, list[tuple[QgisInfo, ProcessDescription]]] = {}
        # the newest QGIS first, its description is the one taken
        for qgis_info, process_descriptions in sorted(
            served, key=lambda item: item[0].version, reverse=True
        ):
            for process in process_descriptions.processes:
                descriptions_by_process_id.setdefault(process.id, []).append((qgis_info, process))

        merged = ProcessDescriptions()
        for process_id, described in descriptions_by_process_id.items():
            newest = described[0][1]
            merged.processes.append(newest)
            # each version once, the newest first
            qgis_versions = list(dict.fromkeys(qgis.version_name for qgis, _ in described))
            descriptions_differ = any(process != newest for _, process in described)
            if len(qgis_versions) > 1 or descriptions_differ:
                logging.warning(
                    f"Process `{process_id}` is served by QGIS {qgis_versions}, "
                    f"descriptions differ: {descriptions_differ}"
                )
                merged.warnings.append(
                    ProcessWarning(
                        process_id=process_id,
                        qgis_versions=qgis_versions,
                        descriptions_differ=descriptions_differ,
                    )
                )
        return merged

    async def submit(
        self,
        job_id: str,
        job_parameter: QslJobParameterExecuteProcess,
        execution_mode: ExecutionMode = ExecutionMode.ASYNC,
    ) -> None:
        """Queues a process job and returns right away. The expiry is set in the
        same transaction, so a job which is never picked up does not stay in
        redis forever.

        Args:
            job_id: The unique identifier of the job, given by the caller so it
                can refer to the job later.
            job_parameter: The parameter for the process which should be executed.
            execution_mode: `ExecutionMode.SYNC` if the caller is going to
                `wait` for the job, the worker only notifies then.
        """
        job_info = self.derive_job_info(job_id, job_parameter)
        job_info.execution_mode = execution_mode
        async with self.client.pipeline() as p:
            await self.queue_job(job_info, p, time.time())
            await p.expire(self.job_key(job_id), self.job_expire)
            await p.execute()
        logging.info(f"{job_id} submitted")

    async def state(self, job_id: str) -> JobState | None:
        """Reads the current state of the job from its job hash.

        Args:
            job_id: The unique identifier of the job.

        Returns:
            The state of the job, `None` if the job does not exist (anymore).
        """
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
        """Decodes a hash field which might not be set."""
        return value.decode() if value is not None else None

    def job_result(self, job_id: str, job_hash: dict[str, bytes]) -> JobResult | None:
        """Assembles the result of the job from its decoded job hash. The data
        stays bytes, the content type tells the caller how to read it.

        Args:
            job_id: The unique identifier of the job.
            job_hash: The job hash with decoded field names.

        Returns:
            The result, `None` as long as the job has not succeeded.
        """
        if self.job_result_key not in job_hash:
            return None
        return JobResult(
            id=job_id,
            data=job_hash[self.job_result_key],
            content_type=job_hash[self.job_result_content_type_key].decode(),
        )

    async def wait(self, job_id: str, to: float = 10.0) -> JobState | None:
        """Waits maximum `to` seconds for the job to finish. This is what makes a
        synchronous execution possible on top of a job which keeps its state.
        It only gets notified if the job was submitted with
        `ExecutionMode.SYNC`, otherwise it runs into the timeout.

        Args:
            job_id: The unique identifier of the job.
            to: The timeout in seconds.

        Returns:
            The state of the job after it finished or the timeout passed, `None`
            if the job does not exist (anymore).
        """
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
        """Blocks until a message arrives on the subscribed channel or the timeout
        passes. The message itself is not of interest, the state is read from
        the job hash afterwards.

        Args:
            ps: The pubsub which is subscribed to the channel of the job.
            job_id: The unique identifier of the job, used for logging.
            to: The timeout in seconds.
        """
        try:
            async with timeout(to):
                while True:
                    message = await ps.get_message(timeout=to, ignore_subscribe_messages=True)
                    if message:
                        return
        except (TimeoutError, asyncio.exceptions.CancelledError):
            logging.info(f"{job_id} timeout")


class RedisQueue(RedisDispatcher, RedisPublishProtocol):
    """The dispatcher for short living jobs a caller waits for. The result is
    received over the channel and nothing is kept in redis afterwards.
    """

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
