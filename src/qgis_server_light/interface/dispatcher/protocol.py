"""This contains the protocol definition about how a job is passed
around a redis queue. It is shared by the dispatcher and the worker and
therefore must not depend on anything else than the standard library.

"""


class RedisProtocol:
    """Names of the redis queue, the job hash fields and the notification
    channel a job is exchanged with.

    A job is put into redis as hash under `job:{id}` (see `job_key`) and its
    id is pushed onto the list `job_queue_name`. The hash holds the fields:

    - `info`: The job info serialized as JSON.
    - `info_type`: The class name of the job info, used to parse `info`.
    - `status`: The current `Status` value of the job.
    - `timestamp.{status}`: ISO timestamp when the job entered that status.
    - `timestamp.last_update`: ISO timestamp of the last status change.
    - `duration`: Seconds since the job was posted, as string.

    The result of a job is published to the channel `notifications:{id}` (see
    `channel`).

    A worker registers itself as hash under `worker:{id}` (see `worker_key`) and
    adds its id to the set `worker_list_name`. The hash holds the fields:

    - `info`: The engine info serialized as JSON.
    - `last_seen`: ISO timestamp (UTC) of the last heartbeat.

    Attributes:
        job_queue_name: The name of the redis list the job ids are queued on.
        job_info_key: The hash field holding the serialized job info.
        job_info_type_key: The hash field holding the class name of the job info.
        job_channel_name: The prefix of the channel the job result is published to.
        job_status_key: The hash field holding the job status.
        job_duration_key: The hash field holding the job duration.
        job_timestamp_key: The prefix of the hash fields holding the timestamps.
        job_last_update_key: The hash field holding the timestamp of the last update.
        worker_list_name: The name of the redis set the worker ids are registered in.
        worker_info_key: The hash field holding the serialized engine info.
        worker_last_seen_key: The hash field holding the timestamp of the last heartbeat.
        worker_heartbeat_interval: Seconds between two heartbeats of a worker.
        worker_alive_age: Seconds a heartbeat may be old for the worker to count as alive.
    """

    job_queue_name: str = "jobs"
    job_info_key: str = "info"
    job_info_type_key: str = "info_type"
    job_channel_name: str = "notifications"
    job_status_key: str = "status"
    job_duration_key: str = "duration"
    job_timestamp_key: str = "timestamp"
    job_last_update_key: str = f"{job_timestamp_key}.last_update"
    worker_list_name: str = "workers"
    worker_info_key: str = "info"
    worker_last_seen_key: str = "last_seen"
    worker_heartbeat_interval: int = 1
    worker_alive_age: int = 10 * worker_heartbeat_interval

    @staticmethod
    def job_key(job_id: str) -> str:
        """The key of the redis hash holding the job.

        Args:
            job_id: The unique identifier of the job.
        """
        return f"job:{job_id}"

    @classmethod
    def channel(cls, job_id: str) -> str:
        """The channel the job result is published to.

        Args:
            job_id: The unique identifier of the job.
        """
        return f"{cls.job_channel_name}:{job_id}"

    @staticmethod
    def worker_key(worker_id: str) -> str:
        """The key of the redis hash holding the worker registration.

        Args:
            worker_id: The unique identifier of the worker.
        """
        return f"worker:{worker_id}"
