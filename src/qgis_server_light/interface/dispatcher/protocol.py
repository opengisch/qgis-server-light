"""This contains the protocol definition about how a job is passed
around a redis queue. It is shared by the dispatcher and the worker and
therefore must not depend on anything else than the standard library.

"""


class RedisProtocol:
    """Names of the redis queue, the job hash fields and the notification
    channel a job is exchanged with.

    A job is put into redis as hash under `job:{id}` (see `job_key`) and its
    id is pushed onto the list returned by `queue_name` for its job info type.
    Process jobs are queued on `job_process_queue_name`, all other jobs on
    `job_queue_name`, so long-running processes never block map related jobs.
    A worker listens on the queues of the job info types of its runner plugins
    (see `queue_names`). The hash holds the fields:

    - `info`: The job info serialized as JSON.
    - `info_type`: The class name of the job info, used to parse `info`.
    - `status`: The current `Status` value of the job.
    - `timestamp.{status}`: ISO timestamp when the job entered that status.
    - `timestamp.last_update`: ISO timestamp of the last status change.
    - `duration`: Seconds since the job was posted, as string.

    The result of a job is published to the channel `notifications:{id}` (see
    `channel`).

    Attributes:
        job_queue_name: The name of the redis list the ids of map related jobs
            are queued on.
        job_process_queue_name: The name of the redis list the ids of process
            jobs are queued on.
        job_queue_name_by_info_type: The queue name per job info type (class
            name of the job info).
        job_info_key: The hash field holding the serialized job info.
        job_info_type_key: The hash field holding the class name of the job info.
        job_channel_name: The prefix of the channel the job result is published to.
        job_status_key: The hash field holding the job status.
        job_duration_key: The hash field holding the job duration.
        job_timestamp_key: The prefix of the hash fields holding the timestamps.
        job_last_update_key: The hash field holding the timestamp of the last update.
    """

    job_queue_name: str = "jobs"
    job_process_queue_name: str = "jobs:process"
    job_queue_name_by_info_type: dict[str, str] = {
        "QslJobInfoRender": "jobs",
        "QslJobInfoFeatureInfo": "jobs",
        "QslJobInfoLegend": "jobs",
        "QslJobInfoFeature": "jobs",
        "QslJobInfoCrs": "jobs",
        "QslJobInfoExecuteProcess": "jobs:process",
    }
    job_info_key: str = "info"
    job_info_type_key: str = "info_type"
    job_channel_name: str = "notifications"
    job_status_key: str = "status"
    job_duration_key: str = "duration"
    job_timestamp_key: str = "timestamp"
    job_last_update_key: str = f"{job_timestamp_key}.last_update"

    @staticmethod
    def job_key(job_id: str) -> str:
        """The key of the redis hash holding the job.

        Args:
            job_id: The unique identifier of the job.
        """
        return f"job:{job_id}"

    @classmethod
    def queue_name(cls, job_info_type: str) -> str:
        """The name of the queue a job of this type is queued on.

        Args:
            job_info_type: The class name of the job info.
        """
        return cls.job_queue_name_by_info_type[job_info_type]

    @classmethod
    def queue_names(cls, job_info_types: list[str]) -> list[str]:
        """The names of the queues a worker serving these job types listens on.
        Each name is contained once, in the order of its first job info type.

        Args:
            job_info_types: The class names of the job infos the worker serves.
        """
        queue_names = []
        for job_info_type in job_info_types:
            queue_name = cls.queue_name(job_info_type)
            if queue_name not in queue_names:
                queue_names.append(queue_name)
        return queue_names

    @classmethod
    def channel(cls, job_id: str) -> str:
        """The channel the job result is published to.

        Args:
            job_id: The unique identifier of the job.
        """
        return f"{cls.job_channel_name}:{job_id}"
