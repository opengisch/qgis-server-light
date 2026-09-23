import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class _ActiveJob:
    job_id: str
    description: str
    started_at: float


class JobWatchdog:
    """Force-restarts the process if a job runs longer than `timeout_seconds`.

    This guards against native (Qt/QGIS) deadlocks that no Python-level
    timeout or exception handling can interrupt: the only reliable recovery
    is a hard process exit, left to the container's restart policy.
    """

    def __init__(
        self,
        timeout_seconds: float,
        worker_id: str,
        poll_interval: float = 1.0,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._worker_id = worker_id
        self._poll_interval = poll_interval
        self._lock = threading.Lock()
        self._active_job: Optional[_ActiveJob] = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="job-watchdog", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def job_started(self, job_id: str, description: str) -> None:
        with self._lock:
            self._active_job = _ActiveJob(job_id, description, time.monotonic())

    def job_finished(self) -> None:
        with self._lock:
            self._active_job = None

    def _run(self) -> None:
        while not self._stop_event.wait(self._poll_interval):
            with self._lock:
                job = self._active_job
            if job is None:
                continue
            elapsed = time.monotonic() - job.started_at
            if elapsed >= self._timeout_seconds:
                self._trigger(job, elapsed)

    def _trigger(self, job: _ActiveJob, elapsed: float) -> None:
        logging.error(
            "Watchdog: job %s on worker %s exceeded %.0fs (running for %.0fs) "
            "- forcing process restart. Job: %s",
            job.job_id,
            self._worker_id,
            self._timeout_seconds,
            elapsed,
            job.description,
        )
        logging.shutdown()
        os._exit(1)
