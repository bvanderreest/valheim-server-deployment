"""A timeline of what the server actually did, built from its own log.

Written after a real session exposed how much the log says and how little of it
reached anyone. During that session the server recorded a failed password
attempt, a join, a leave, eight saves with per-stage timings, and its own disk
headroom against its own stop-saving threshold. The console showed a player
count — and got that wrong.

Two rules this module follows, both learned the hard way here:

  * Prefer what the server STATES over what we can infer. The player count was
    derived by subtracting disconnect lines from connect lines, which broke the
    first time someone mistyped a password, because those two streams do not
    pair up. `now N player(s)` needs no arithmetic.

  * Never report a number whose meaning changed without saying so. 1.0's save
    "total" covers the write only; 0.221's covered everything. See logfmt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from . import logfmt

# A save is five stages, and the blocking work happens BEFORE stage 1. Naming
# them here keeps the API and the UI using the server's own words.
STAGE_LABELS = {
    1: "Cloud & backup checks",
    2: "Chunks writing",
    3: "DB2 writing",
    4: "FWL writing",
    5: "Done",
}


def _epoch(line: str) -> Optional[float]:
    m = logfmt.RE_TIMESTAMP.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(
            m.group(0), logfmt.TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _iso(epoch: Optional[float]) -> Optional[str]:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def parse(lines: list[str]) -> dict[str, Any]:
    """Fold a log into a timeline plus the current state it implies."""
    events: list[dict[str, Any]] = []
    disk: Optional[dict[str, Any]] = None
    saves: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}          # the save being assembled
    session: dict[str, Any] = {}
    # name -> when we first and last saw them, and whether they are on now.
    # Bounded by the tail we were given: this is "seen in the log we can read",
    # not "since the beginning of time", and the API says so.
    roster: dict[str, dict[str, Any]] = {}
    zdo_owner: dict[str, str] = {}          # zdo id -> name
    retries = 0
    last_ts: Optional[float] = None

    def add(kind: str, ts: Optional[float], **fields):
        events.append({"kind": kind, "at": _iso(ts), "epoch": ts, **fields})

    for line in lines:
        ts = _epoch(line)
        if ts is not None:
            last_ts = ts
        else:
            ts = last_ts                       # continuation lines carry no stamp

        if (m := logfmt.RE_AUTH_FAILED.search(line)):
            # The event that started all this. Somebody could not get in and
            # nothing anywhere said so.
            add("auth_failed", ts, peer=m.group(1))
            continue
        if (m := logfmt.RE_JOINED.search(line)):
            add("join", ts, server=m.group(1), players=int(m.group(2)))
            continue
        if (m := logfmt.RE_LEFT.search(line)):
            add("leave", ts, server=m.group(1), players=int(m.group(2)))
            continue
        if (m := logfmt.RE_ZDOID.search(line)):
            name = m.group(1).strip()
            zid = f"{m.group(2)}:{m.group(3)}"
            alive = zid != "0:0"
            r = roster.setdefault(name, {"name": name, "first_seen": _iso(ts),
                                         "last_seen": None, "active": False})
            r["last_seen"] = _iso(ts)
            r["active"] = alive
            if alive:
                zdo_owner[zid] = name
            add("character", ts, name=name, alive=alive)
            continue
        if (m := logfmt.RE_ZDO_ABANDONED.search(line)):
            # The real "they are gone" signal — the server's own player count
            # does not drop while it holds their socket for a reconnect.
            owner = zdo_owner.get(m.group(1))
            if owner and owner in roster:
                roster[owner]["active"] = False
                roster[owner]["last_seen"] = _iso(ts)
                add("leave_confirmed", ts, name=owner)
            continue
        if (m := logfmt.RE_DISK.search(line)):
            free, blocked, warn = (int(m.group(i)) for i in (1, 2, 3))
            state = "blocked" if free < blocked else "warning" if free < warn else "ok"
            disk = {"free_bytes": free, "blocked_below_bytes": blocked,
                    "warn_below_bytes": warn, "state": state, "at": _iso(ts)}
            continue
        if (m := logfmt.RE_PREPARE_CHUNKS.search(line)):
            cur = {"epoch": ts, "at": _iso(ts), "chunks": int(m.group(1)),
                   "dirty_chunks": int(m.group(2)),
                   "phases": [{"name": "Clone chunks", "ms": float(m.group(3)),
                               "blocking": True}]}
            continue
        if (m := logfmt.RE_PREPARE_ZDO.search(line)):
            cur.setdefault("phases", []).append(
                {"name": "Prepare ZDOs", "ms": float(m.group(1)), "blocking": True})
            continue
        if (m := logfmt.RE_SAVE_STAGE.search(line)):
            stage, ms = int(m.group(1)), float(m.group(3))
            if m.group(4):
                cur["save_number"] = int(m.group(4))
            if stage == 5:
                cur["total_ms"] = ms
                cur["blocking_ms"] = sum(p["ms"] for p in cur.get("phases", [])
                                         if p.get("blocking"))
                cur["at"] = cur.get("at") or _iso(ts)
                cur["epoch"] = cur.get("epoch") or ts
                saves.append(cur)
                add("save", ts, save_number=cur.get("save_number"),
                    total_ms=cur.get("total_ms"), blocking_ms=cur.get("blocking_ms"))
                cur = {}
            else:
                cur.setdefault("phases", []).append(
                    {"name": STAGE_LABELS[stage], "ms": ms, "blocking": False})
            continue
        if (m := logfmt.RE_SESSION_REGISTERED.search(line)):
            session.update(name=m.group(1), join_code=m.group(2))
            add("session_registered", ts, join_code=m.group(2))
            continue
        if (m := logfmt.RE_SESSION_ACTIVE.search(line)):
            session.update(name=m.group(1), join_code=m.group(2), public_addr=m.group(3))
            continue
        if logfmt.RE_JOINCODE_RETRY.search(line):
            retries += 1
            continue
        if (m := logfmt.RE_WORLD_LOAD.search(line)):
            add("world_load", ts, world=m.group(1), save_number=int(m.group(3)))
            continue

    # A save whose stage 1 was seen but whose stage 5 never arrived did not
    # finish. That is worth knowing and is invisible in any "last save" field.
    unfinished = bool(cur.get("phases"))

    return {
        "events": events,
        "disk": disk,
        "saves": saves,
        "last_save": saves[-1] if saves else None,
        "save_in_progress": unfinished,
        "session": session or None,
        "join_code_retries": retries,
        "auth_failures": [e for e in events if e["kind"] == "auth_failed"],
        # Active first, then most recently seen.
        "players": sorted(roster.values(),
                          key=lambda r: (not r["active"], r["last_seen"] or ""),
                          reverse=False),
    }
