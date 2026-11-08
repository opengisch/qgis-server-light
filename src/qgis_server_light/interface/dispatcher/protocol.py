"""This contains the protocol definition about how a job is passed
around a redis queue. It is shared by the dispatcher and the worker and
therefore must not depend on anything else than the standard library.

"""


class RedisProtocol:
    """Names of the redis queue, the job hash fields and the notification
    channel a job is exchanged with. It is the common ground of both ways a
    job result is delivered, the concrete queue is defined by the subclasses
    `RedisPublishProtocol` and `RedisStateProtocol`.

    A job is put into redis as hash under `job:{id}` (see `job_key`) and its
    id is pushed onto the list returned by `queue_name`. A worker listens on
    the queue of the protocol it is built on. The hash holds the fields:

    - `info`: The job info serialized as JSON.
    - `info_type`: The class name of the job info, used to parse `info`.
    - `status`: The current `Status` value of the job.
    - `timestamp.{status}`: ISO timestamp when the job entered that status.
    - `timestamp.last_update`: ISO timestamp of the last status change.
    - `duration`: Seconds since the job was posted, as string.

    The channel `notifications:{id}` (see `channel`) is used to tell a waiting
    dispatcher that the job is finished. What is sent over it depends on the
    subclass.

    A process-worker writes the descriptions of the processes it serves as JSON
    (`ProcessDescriptions`) under `process_registry_key` on boot, unless the key
    exists already.

    Attributes:
        job_queue_name: The name of the redis list the ids of the jobs are
            queued on. Set by the subclasses.
        job_info_key: The hash field holding the serialized job info.
        job_info_type_key: The hash field holding the class name of the job info.
        job_channel_name: The prefix of the channel a finished job is notified on.
        job_status_key: The hash field holding the job status.
        job_duration_key: The hash field holding the job duration.
        job_timestamp_key: The prefix of the hash fields holding the timestamps.
        job_last_update_key: The hash field holding the timestamp of the last update.
        process_registry_key: The key holding the descriptions of the processes the
            process-workers serve.
    """

    job_queue_name: str
    job_info_key: str = "info"
    job_info_type_key: str = "info_type"
    job_channel_name: str = "notifications"
    job_status_key: str = "status"
    job_duration_key: str = "duration"
    job_timestamp_key: str = "timestamp"
    job_last_update_key: str = f"{job_timestamp_key}.last_update"
    process_registry_key: str = "processes"

    @staticmethod
    def job_key(job_id: str) -> str:
        """The key of the redis hash holding the job.

        Args:
            job_id: The unique identifier of the job.
        """
        return f"job:{job_id}"

    @classmethod
    def queue_name(cls) -> str:
        """The name of the queue the jobs of this protocol are queued on. It is
        a method on purpose, so the place where the name is decided stays the
        same if it ever needs to be assembled."""
        return cls.job_queue_name

    @classmethod
    def channel(cls, job_id: str) -> str:
        """The channel a finished job is notified on.

        Args:
            job_id: The unique identifier of the job.
        """
        return f"{cls.job_channel_name}:{job_id}"


class RedisPublishProtocol(RedisProtocol):
    """The protocol of short living jobs a dispatcher waits for, like
    rendering a map or a legend. The worker publishes the pickled `JobResult`
    over the channel and the dispatcher deletes the job hash after it has
    received it. Nothing is kept, a result is only there for the one who is
    listening.

    Attributes:
        job_queue_name: The name of the redis list the ids of the jobs are
            queued on.
    """

    job_queue_name: str = "jobs"


class RedisStateProtocol(RedisProtocol):
    """The protocol of jobs which keep their state, these are the processes.
    The worker writes the result (or the error message) into the job hash in
    the same transaction as the final status, so whoever reads the hash never
    sees a finished job without its result. The hash expires after
    `job_expire` seconds, it is the only place the result lives.

    Only the status value is sent over the channel and only if the job was
    submitted with `ExecutionMode.SYNC`. It just wakes the waiting dispatcher,
    which then reads the job hash. Asynchronous jobs are polled, nobody waits
    for a notification there.

    Processes are queued on their own list, so long-running processes never
    block map related jobs.

    Additional hash fields:

    - `result`: The data of the `JobResult` of a succeeded job.
    - `result_content_type`: The content type of `result`.
    - `message`: The error message of a failed job.

    Attributes:
        job_queue_name: The name of the redis list the ids of the jobs are
            queued on.
        job_result_key: The hash field holding the result data.
        job_result_content_type_key: The hash field holding the content type
            of the result data.
        job_message_key: The hash field holding the error message.
        job_expire: Seconds the job hash is kept after it was submitted and
            again after it is finished.
    """

    job_queue_name: str = "jobs:process"
    job_result_key: str = "result"
    job_result_content_type_key: str = "result_content_type"
    job_message_key: str = "message"
    job_expire: int = 86400
