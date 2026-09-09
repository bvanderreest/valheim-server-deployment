"""GET /performance — when the world froze, and for how long.

`/metrics` reports the last stall. This reports every stall in a window, with
timestamps, so a lag complaint can be checked against the server rather than
argued about. The framing that makes it useful:

  * The server stalled at the reported minute  -> that is the server. The panel
    says which kind, and a save stall has a fix (SAVE_INTERVAL) while a GC pause
    does not.
  * The server did NOT stall                   -> the freeze was not here. For a
    group split across continents that is the answer the argument needs, and
    without this endpoint nobody could give it.

The endpoint is deliberately cheap: one tail of the log, no state, no history
store. Everything it reports is already on disk.
"""

from fastapi import APIRouter, Query

from ..models import PerformanceResponse
from ..services import performance as svc

router = APIRouter(tags=["performance"])


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance(
    hours: float = Query(
        6.0,
        ge=0.25,
        le=48.0,
        description="How far back to look. Bounded by what the current log file covers; "
        "a restart rotates the log, so a fresh server reports a short observed_hours.",
    ),
) -> PerformanceResponse:
    return PerformanceResponse(**svc.collect(hours))
