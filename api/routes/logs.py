import asyncio
import json
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..config import settings
from ..models import LogsResponse

router = APIRouter()


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    lines: int = Query(default=100, ge=1, le=5000, description="Number of log lines to return"),
) -> LogsResponse:
    logfile = settings.logfile
    if not logfile.exists():
        return LogsResponse(lines=[], count=0, log_file=str(logfile))

    with logfile.open("r", errors="replace") as f:
        content = list(deque((line.rstrip() for line in f), maxlen=lines))

    return LogsResponse(lines=content, count=len(content), log_file=str(logfile))


@router.get("/logs/stream")
async def stream_logs() -> StreamingResponse:
    """
    Server-Sent Events stream of the live server log.
    Each event is a JSON object: {"line": "...", "timestamp": "..."}
    Connect with: curl -N -H "X-API-Key: <key>" http://host:8080/logs/stream
    NOTE: If behind nginx, ensure 'proxy_buffering off' is set.
    """

    async def event_generator():
        logfile = settings.logfile
        if not logfile.exists():
            payload = json.dumps({"line": "Log file not found", "timestamp": _now_iso()})
            yield f"data: {payload}\n\n"
            return

        with logfile.open("r", errors="replace") as f:
            f.seek(0, 2)  # Jump to end — only stream new lines
            while True:
                line = f.readline()
                if line:
                    payload = json.dumps({
                        "line": line.rstrip(),
                        "timestamp": _now_iso(),
                    })
                    yield f"data: {payload}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Prevent nginx from buffering the SSE stream
        },
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
