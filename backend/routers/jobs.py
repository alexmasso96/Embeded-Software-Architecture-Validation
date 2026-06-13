"""
Job + event-stream router (plan §3.1).

    POST /api/jobs/{kind}          → 202 {"job_id", ...}
    GET  /api/jobs/{job_id}        → job snapshot
    POST /api/jobs/{job_id}/cancel → request cancellation
    GET  /api/jobs                 → registered job kinds
    GET  /api/events               → single SSE stream (job/db-changed/lock events)
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sse_starlette.sse import EventSourceResponse

from ..deps import get_bus, get_jobs
from ..events import EventBus
from ..jobs import JobManager
from ..security import require_token

router = APIRouter(prefix="/api", tags=["jobs"],
                   dependencies=[Depends(require_token)])


@router.get("/jobs")
def list_kinds(jobs: JobManager = Depends(get_jobs)) -> dict:
    return {"kinds": jobs.known_kinds()}


@router.post("/jobs/{kind}", status_code=status.HTTP_202_ACCEPTED)
async def start_job(kind: str, request: Request,
                    jobs: JobManager = Depends(get_jobs)) -> dict:
    # Body is optional; accept an empty/no body as {}.
    try:
        params = await request.json()
    except Exception:
        params = {}
    if not isinstance(params, dict):
        raise HTTPException(status_code=422, detail="Job params must be a JSON object.")
    try:
        job = jobs.start(kind, params)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown job kind: {kind}")
    return job.public()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, jobs: JobManager = Depends(get_jobs)) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return job.public()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, jobs: JobManager = Depends(get_jobs)) -> dict:
    if not jobs.cancel(job_id):
        raise HTTPException(status_code=404, detail="No such job.")
    return {"job_id": job_id, "cancelling": True}


@router.get("/events")
async def events(request: Request, bus: EventBus = Depends(get_bus)) -> Response:
    """Single SSE stream. Each message is ``event: <type>`` + JSON ``data``.

    A periodic comment ping keeps proxies from closing an idle stream and lets
    us notice client disconnects promptly.
    """
    queue = bus.subscribe()

    async def generator():
        try:
            yield {"event": "ready", "data": "{}"}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": event["type"], "data": json.dumps(event["data"])}
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(generator())
