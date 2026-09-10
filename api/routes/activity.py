"""GET /activity — what the server has been doing, from its own log.

Added after a real session in which the log recorded a refused login, a join, a
leave held open by a socket, eight staged saves and the server's own disk
threshold — and a human watching the console saw none of it.

Deliberately read-only and deliberately cheap: it folds the same tail the rest
of the API already reads. Nothing here polls the game.
"""

from collections import deque
from typing import Any, Literal, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..services.events import parse

router = APIRouter(tags=["activity"])

# Enough to span several hours of a quiet server without reading the whole file.
_TAIL_LINES = 4000


class Disk(BaseModel):
    """The server's OWN thresholds, not ours.

    Valheim states both on every save and stops saving below `blocked_below_bytes`.
    Guessing a percentage here would invent a threshold the server does not use.
    """
    free_bytes: int
    blocked_below_bytes: int
    warn_below_bytes: int
    state: Literal["ok", "warning", "blocked"]
    at: Optional[str] = None


class Phase(BaseModel):
    name: str
    ms: float
    blocking: bool = Field(
        description="True if this phase freezes the main thread. Players feel "
                    "blocking phases; the write phases they do not.")


class Save(BaseModel):
    at: Optional[str] = None
    save_number: Optional[int] = None
    total_ms: Optional[float] = None
    blocking_ms: Optional[float] = None
    chunks: Optional[int] = None
    dirty_chunks: Optional[int] = None
    phases: list[Phase] = []


class Event(BaseModel):
    kind: str
    at: Optional[str] = None
    # Deliberately loose: an event's payload depends on its kind, and pinning
    # every shape here would make adding one a breaking change.
    model_config = {"extra": "allow"}


class Player(BaseModel):
    """Bounded by the log tail we can read, not "since the world began"."""
    name: str
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    active: bool = False


class ActivityResponse(BaseModel):
    events: list[Event]
    players: list[Player] = []
    disk: Optional[Disk] = None
    last_save: Optional[Save] = None
    save_in_progress: bool = False
    auth_failures: list[Event] = []
    join_code_retries: int = 0
    session: Optional[dict[str, Any]] = None


def _tail(n: int) -> list[str]:
    try:
        with settings.logfile.open(errors="replace") as f:
            return list(deque(f, maxlen=n))
    except OSError:
        return []


@router.get("/activity", response_model=ActivityResponse)
async def activity(limit: int = Query(60, ge=1, le=500)) -> ActivityResponse:
    d = parse(_tail(_TAIL_LINES))
    d["events"] = d["events"][-limit:]
    return ActivityResponse(**d)
