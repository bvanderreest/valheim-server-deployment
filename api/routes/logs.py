import asyncio
from collections import deque

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
        return LogsResponse(lines=[], total_lines=0, logfile=str(logfile))

    with logfile.open("r", errors="replace") as f:
        content = list(deque((line.rstrip() for line in f), maxlen=lines))

    return LogsResponse(lines=content, total_lines=len(content), logfile=str(logfile))


@router.get("/logs/stream")
async def stream_logs() -> StreamingResponse:
    """
    Server-Sent Events stream of the live server log.
    Connect with: curl -N -H "X-API-Key: <key>" http://host:8080/logs/stream
    NOTE: If behind nginx, ensure 'proxy_buffering off' is set.
    """

    async def event_generator():
        logfile = settings.logfile
        if not logfile.exists():
            yield "data: Log file not found\n\n"
            return

        with logfile.open("r", errors="replace") as f:
            f.seek(0, 2)  # Jump to end of file — only stream new lines
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
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
