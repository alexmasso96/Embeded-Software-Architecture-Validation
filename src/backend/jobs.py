"""
Background job manager (plan §3.1) — one contract for every heavy operation.

    POST /api/jobs/{kind}          → 202 {"job_id"}
    GET  /api/jobs/{job_id}        → {"status","progress","message","result?","error?"}
    POST /api/jobs/{job_id}/cancel → sets the cancel event
    GET  /api/events               → SSE: job progress + db-changed + lock events

A handler is registered per kind as ``fn(params, progress, cancel_event) -> result``:
  * ``progress(message, percent=None)`` updates the job and emits a `job` SSE event
  * ``cancel_event`` is a threading.Event the handler should poll for cooperative cancel

Handlers run on a ThreadPoolExecutor. Inside this worker process threads are fine:
the GIL no longer matters to the UI (it lives in another process) and CPU-heavy
parsing is already GIL-free in Rust. Do NOT invent per-feature variations of this
contract — the uniformity is the AI-legibility win.
"""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .events import EventBus

logger = logging.getLogger(__name__)

# Handler signature: (params, progress_cb, cancel_event) -> result
Handler = Callable[[dict, "Callable[..., None]", threading.Event], Any]

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    kind: str
    status: str = STATUS_QUEUED
    progress: Optional[float] = None       # 0..100, or None when indeterminate
    message: str = ""
    result: Any = None
    error: Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        """The job's serialisable view (no cancel_event, no raw result objects)."""
        d = {
            "job_id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
        }
        # Expose result on success, and on cancellation when the handler
        # returned partial output before stopping.
        if self.result is not None and self.status in (STATUS_DONE, STATUS_CANCELLED):
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d


class JobManager:
    def __init__(self, bus: EventBus, max_workers: int = 4) -> None:
        self.bus = bus
        self.executor = ThreadPoolExecutor(max_workers=max_workers,
                                           thread_name_prefix="job")
        self.jobs: dict[str, Job] = {}
        self._handlers: dict[str, Handler] = {}
        self._lock = threading.Lock()

    # -- registration ---------------------------------------------------
    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def known_kinds(self) -> list[str]:
        return sorted(self._handlers)

    # -- lifecycle ------------------------------------------------------
    def start(self, kind: str, params: dict) -> Job:
        if kind not in self._handlers:
            raise KeyError(kind)
        job = Job(id=uuid.uuid4().hex, kind=kind)
        with self._lock:
            self.jobs[job.id] = job
        self._emit(job)
        self.executor.submit(self._run, job, self._handlers[kind], params or {})
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job is None:
            return False
        job.cancel_event.set()
        if job.status in (STATUS_QUEUED, STATUS_RUNNING):
            job.message = "Cancellation requested…"
            self._emit(job)
        return True

    def shutdown(self) -> None:
        for job in self.jobs.values():
            job.cancel_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    # -- internals ------------------------------------------------------
    def _run(self, job: Job, handler: Handler, params: dict) -> None:
        job.status = STATUS_RUNNING
        self._emit(job)

        def progress(message: str, percent: Optional[float] = None) -> None:
            job.message = message
            if percent is not None:
                job.progress = percent
            self._emit(job)

        try:
            job.result = handler(params, progress, job.cancel_event)
            job.status = STATUS_CANCELLED if job.cancel_event.is_set() else STATUS_DONE
            job.progress = 100.0 if job.status == STATUS_DONE else job.progress
        except JobCancelled:
            job.status = STATUS_CANCELLED
            job.message = "Cancelled."
        except Exception as e:  # noqa: BLE001 — surface every failure to the client
            logger.exception("Job %s (%s) failed", job.id, job.kind)
            job.status = STATUS_FAILED
            job.error = str(e)
        self._emit(job)

    def _emit(self, job: Job) -> None:
        self.bus.publish("job", job.public())


class JobCancelled(Exception):
    """Raise from a handler to mark the job cancelled rather than failed."""
