"""Job introspection — what an action is doing, while it does it.

`POST /server/{action}` now returns a `job_id`. These routes are how the
console follows it: a snapshot for a reload, and a stream for live progress.

There is deliberately no cancel endpoint. The actions worth watching are the
ones that must not be interrupted — killing SteamCMD mid-write or a world
migration mid-flight is the failure this whole change exists to prevent. A
genuinely wedged process is caught by the job's own hard limit.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..models import JobDetail, JobList, JobSummary
from ..services import jobs as jobsvc

router = APIRouter(tags=["jobs"])

# Same header set as /logs/stream: no caching anywhere, and X-Accel-Buffering
# off so nginx/NPMPlus does not hold the events in a buffer and deliver the
# whole update in one lump at the end — which looks exactly like a hang.
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-store",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/jobs", response_model=JobList)
async def list_jobs(limit: int = Query(10, ge=1, le=20)) -> JobList:
    return JobList(jobs=[JobSummary(**j.summary()) for j in jobsvc.recent(limit)])


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, tail: Optional[int] = Query(None, ge=1, le=4000)) -> JobDetail:
    job = jobsvc.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}. Jobs are kept in memory and do not survive an API restart.")
    return JobDetail(**job.detail(tail))


@router.get("/jobs/{job_id}/stream", include_in_schema=True)
async def stream_job(job_id: str, request: Request) -> StreamingResponse:
    """Server-sent events: every line as it is produced, then one `end`.

    A late subscriber gets the lines already emitted first, so a console opened
    mid-update still renders the whole story rather than joining halfway.
    """
    job = jobsvc.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No job {job_id}.")

    async def gen():
        q = job.subscribe()
        try:
            # Replay what has happened so far, then follow.
            snapshot = job.detail()
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
            if job.state != jobsvc.RUNNING:
                yield f"event: end\ndata: {json.dumps(job.summary())}\n\n"
                return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # A comment frame keeps the connection (and any proxy) alive
                    # through the quiet stretch of a long SteamCMD validate.
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {evt['type']}\ndata: {json.dumps(evt)}\n\n"
                if evt["type"] == "end":
                    return
        finally:
            # Without this every reload leaks a queue that the worker keeps
            # filling — the existing /logs/stream has exactly that bug.
            job.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)
