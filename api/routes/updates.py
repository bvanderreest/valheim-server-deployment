"""Is there a Valheim server update waiting?

Answers the question an operator actually has — "do I need to run update?" —
by comparing the installed Steam build id against what the public branch is
serving. Without this the console can only tell you what you are running, not
whether it is current.
"""
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..config import settings

router = APIRouter(tags=["updates"])

STEAM_APP_ID = "896660"  # Valheim Dedicated Server
_STEAMCMD_API = f"https://api.steamcmd.net/v1/info/{STEAM_APP_ID}"

# Steam is a third party and this is polled by a UI. Cache so an open console
# does not hammer it, and so a Steam outage degrades to stale-but-useful
# rather than to an error.
_CACHE_TTL = 300
_cache: dict = {"at": 0.0, "data": None}


def _installed_buildid() -> Optional[str]:
    """Read the build id Steam recorded for the local install."""
    acf = Path(settings.server_dir) / "steamapps" / f"appmanifest_{STEAM_APP_ID}.acf"
    try:
        text = acf.read_text(errors="replace")
    except OSError:
        return None
    m = re.search(r'"buildid"\s+"(\d+)"', text)
    return m.group(1) if m else None


async def _remote_branches() -> dict:
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.get(_STEAMCMD_API)
        r.raise_for_status()
        data = r.json()
    return (
        data.get("data", {})
        .get(STEAM_APP_ID, {})
        .get("depots", {})
        .get("branches", {})
    )


@router.get("/updates")
async def check_updates(_: str = Depends(require_api_key)) -> dict:
    installed = _installed_buildid()

    now = time.time()
    if _cache["data"] is not None and now - _cache["at"] < _CACHE_TTL:
        branches = _cache["data"]
        cached = True
    else:
        try:
            branches = await _remote_branches()
            _cache.update(at=now, data=branches)
            cached = False
        except Exception as exc:
            # Steam being unreachable must not read as "no update available" —
            # that is the failure mode that lets a server sit stale for weeks.
            if _cache["data"] is not None:
                branches = _cache["data"]
                cached = True
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not reach the Steam build API: {exc}",
                ) from None

    public = branches.get("public", {})
    available = public.get("buildid")

    # Rollback targets, newest first — these are what `rollback` can pin to.
    rollback = [
        {
            "branch": name,
            "buildid": b.get("buildid"),
            "description": (b.get("description") or "").strip(),
            "password_required": str(b.get("pwdrequired", "0")) == "1",
        }
        for name, b in sorted(branches.items())
        if name != "public"
    ]

    return {
        "app_id": STEAM_APP_ID,
        "installed_buildid": installed,
        "available_buildid": available,
        # None rather than False when we cannot tell — "unknown" and "current"
        # are different answers and the UI must not conflate them.
        "update_available": (
            None if (installed is None or available is None) else installed != available
        ),
        "branch": "public",
        "public_updated_at": public.get("timeupdated"),
        "rollback_branches": rollback,
        "cached": cached,
        "checked_at": int(_cache["at"]) or int(now),
    }
