"""Stall event HISTORY — the timeline behind /metrics.

`/metrics` answers "is it stalling right now". That is a snapshot, and a
snapshot cannot answer the question a geographically spread group actually
asks: *"I lagged at 20:42 — was that you, or me?"* For that you need the
history with timestamps, and the log already holds it. This module extracts it.

Two event kinds, and they are not equivalent:

  save  The blocking half of an autosave — `PrepareSave: clone` plus
        `ZDOExtraData.PrepareSave`. Scheduled, so its cadence is SAVE_INTERVAL,
        and it is the freeze the whole group feels at the same instant.
        The much larger `World saved ( Nms )` figure is mostly background I/O
        and is NOT what players experience; it is carried separately so the
        difference stays visible instead of being reported as a 4-second freeze.

  gc    Unity's periodic `UnloadUnusedAssets`. Roughly hourly, dominated by
        MarkObjects walking ~200k loaded objects, and NOT tunable server-side.

GC lines carry no timestamp — Unity writes them to stdout unprefixed. Each is
attributed to the most recent timestamped line above it, which on this log is
accurate to well under a minute. Those events are flagged `exact: false` so the
UI can say so rather than implying a precision we do not have.

Timestamps in the log are naive server-local `MM/DD/YYYY HH:MM:SS` (see the
log-formats reference: `09/08/2026` is 8 September). The API runs on the same
host as the server, so interpreting them in the process's local zone is
correct. Everything leaves here as an epoch, which has no such ambiguity.
"""

from __future__ import annotations

import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import settings
from . import findings as _findings

# Verbatim shapes, all confirmed against the running server's log:
#   09/09/2026 10:25:02: PrepareSave: clone done in 256ms
#   09/09/2026 10:25:03: PrepareSave: ZDOExtraData.PrepareSave done in 337 ms
#   09/09/2026 10:25:07: World saved ( 4404.237ms )
#   Unloading 1 unused Assets to reduce memory usage. Loaded Objects now: 206963.
#   Total: 660.936870 ms (FindLiveObjects: 39.809871 ms CreateObjectMapping: ...)
#   09/09/2026 10:55:13:  Connections 0 ZDOS:419858  sent:0 recv:0
_RE_TS = re.compile(r"^(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}):")
_RE_SAVE_CLONE = re.compile(r"PrepareSave: clone done in (\d+)ms")
_RE_SAVE_ZDO = re.compile(r"ZDOExtraData\.PrepareSave done in (\d+) ?ms")
_RE_SAVE_TOTAL = re.compile(r"World saved \(\s*([0-9.]+)ms\s*\)")
_RE_UNLOAD = re.compile(r"Loaded Objects now: (\d+)")
_RE_GC_TOTAL = re.compile(r"^Total: ([0-9.]+) ms \(FindLiveObjects")
_RE_CONN = re.compile(r"Connections (\d+) ZDOS:(\d+)\s+sent:(\d+) recv:(\d+)")
# Signals the first pass ignored, each of which answers a question prose cannot:
#   Saved N ZDOs      the workload behind a save — without it, "slower" and
#                     "bigger world" are indistinguishable
#   Available space   Valheim's own view of the volume it saves to
#   connected failed  THIS server losing the PlayFab relay. Not a player's link;
#                     the only part of the network path the log can see at all
_RE_SAVED_ZDOS = re.compile(r"Saved (\d+) ZDOs")
_RE_DISK = re.compile(r"Available space to current user: (\d+)\. Saving is blocked if below: (\d+) bytes")
_RE_RELAY_FAIL = re.compile(r"Game server connected failed")
_RE_LOGIN_RETRY = re.compile(r"Sending PlayFab login request \(attempt (\d+)\)")

# A `World saved` line belongs to the PrepareSave immediately before it. On the
# live server the gap is ~4s; anything beyond a minute is a different save (or a
# torn log) and is not attributed.
_SAVE_TOTAL_MAX_GAP_S = 60.0

MAX_TAIL_LINES = 20000


def _parse_ts(line: str) -> Optional[float]:
    m = _RE_TS.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%m/%d/%Y %H:%M:%S").timestamp()
    except ValueError:
        return None


def _tail_lines(n: int = MAX_TAIL_LINES) -> list[str]:
    try:
        with settings.logfile.open(errors="replace") as f:
            return list(deque(f, maxlen=n))
    except OSError:
        return []


def _rotated_logs(window_start: float) -> list[Path]:
    """Archived logs that could still hold part of the window, oldest first.

    A restart rotates the log, so reading only the current file means every
    restart silently shortens the window to nothing — and a trend needs hours.
    The archive name is the time it was ROTATED, i.e. when its content ends, so
    any archive rotated after the window opened may hold part of it.
    """
    out = []
    try:
        for f in settings.logfile.parent.glob("valheim-server-*.log"):
            m = re.match(r"valheim-server-(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.log$", f.name)
            if not m:
                continue
            try:
                ends = datetime(*(int(g) for g in m.groups())).timestamp()
            except ValueError:
                continue
            if ends >= window_start:
                out.append((ends, f))
    except OSError:
        return []
    return [f for _, f in sorted(out)]


def _lines_covering(window_start: float, budget: int = MAX_TAIL_LINES) -> list[str]:
    """Current log plus whatever archives are needed to reach back to the window.

    Reads newest-first and stops at the line budget, so a 24 h window on a
    chatty server costs the same as a 1 h one.
    """
    files = _rotated_logs(window_start) + [settings.logfile]
    chunks: list[list[str]] = []
    remaining = budget
    for f in reversed(files):
        if remaining <= 0:
            break
        try:
            with f.open(errors="replace") as fh:
                got = list(deque(fh, maxlen=remaining))
        except OSError:
            continue
        chunks.append(got)
        remaining -= len(got)
    out: list[str] = []
    for c in reversed(chunks):
        out.extend(c)
    return out


def parse_events(lines: list[str]) -> tuple[list[dict], dict, tuple[Optional[float], Optional[float]]]:
    """Return (events, context, (first_ts, last_ts)) — the event view only."""
    p = parse_all(lines)
    return p["events"], p["context"], (p["first_ts"], p["last_ts"])


def parse_all(lines: list[str]) -> dict:
    """Events plus the signal series the findings are computed from.

    Returns events, and three time series that answer questions the events
    cannot on their own: `disk` (free space, so "is the volume filling"),
    `net` (byte counters and player count), and `incidents` (this server
    losing the PlayFab relay).
    """
    events: list[dict] = []
    disk: list[dict] = []
    net: list[dict] = []
    incidents: list[dict] = []
    context: dict = {
        "world_zdos": None,
        "loaded_objects": None,
        "players": None,
        "net_sent_bytes": None,
        "net_recv_bytes": None,
    }
    last_ts: Optional[float] = None
    first_ts: Optional[float] = None
    clone_ms: Optional[int] = None
    clone_ts: Optional[float] = None
    pending_objects: Optional[int] = None

    for line in lines:
        ts = _parse_ts(line)
        if ts is not None:
            last_ts = ts
            if first_ts is None:
                first_ts = ts

        if (m := _RE_SAVE_CLONE.search(line)):
            clone_ms = int(m.group(1))
            clone_ts = ts if ts is not None else last_ts
            continue

        if (m := _RE_SAVE_ZDO.search(line)):
            zdo_ms = int(m.group(1))
            if clone_ms is not None:
                # Both halves of one PrepareSave. THIS is the frozen window.
                events.append({
                    "kind": "save",
                    "epoch": clone_ts if clone_ts is not None else (ts or last_ts),
                    "ms": float(clone_ms + zdo_ms),
                    "exact": True,
                    "total_ms": None,
                    "objects": None,
                    # The workload this stall was doing. Without it, "the save
                    # got slower" and "the world got bigger" look identical.
                    "zdos": None,
                })
            clone_ms = clone_ts = None
            continue

        if (m := _RE_SAVE_TOTAL.search(line)):
            total = float(m.group(1))
            when = ts if ts is not None else last_ts
            for ev in reversed(events):
                if ev["kind"] != "save":
                    continue
                if ev["total_ms"] is None and ev["epoch"] is not None and when is not None \
                        and 0 <= when - ev["epoch"] <= _SAVE_TOTAL_MAX_GAP_S:
                    ev["total_ms"] = total
                break
            continue

        if (m := _RE_SAVED_ZDOS.search(line)):
            for ev in reversed(events):
                if ev["kind"] == "save":
                    if ev.get("zdos") is None:
                        ev["zdos"] = int(m.group(1))
                    break
            continue

        if (m := _RE_DISK.search(line)):
            when = ts if ts is not None else last_ts
            if when is not None:
                disk.append({"epoch": when, "free": int(m.group(1)),
                             "block_below": int(m.group(2))})
            continue

        if _RE_RELAY_FAIL.search(line):
            when = ts if ts is not None else last_ts
            if when is not None:
                incidents.append({"epoch": when, "kind": "relay-lost"})
            continue

        if (m := _RE_LOGIN_RETRY.search(line)):
            # Attempt 1 is the normal path. Anything past it is a retry.
            if int(m.group(1)) > 1:
                when = ts if ts is not None else last_ts
                if when is not None:
                    incidents.append({"epoch": when, "kind": "playfab-retry"})
            continue

        if (m := _RE_UNLOAD.search(line)):
            pending_objects = int(m.group(1))
            context["loaded_objects"] = pending_objects
            continue

        if (m := _RE_GC_TOTAL.match(line)):
            # No timestamp of its own — attributed to the last one seen above.
            events.append({
                "kind": "gc",
                "epoch": last_ts,
                "ms": float(m.group(1)),
                "exact": False,
                "total_ms": None,
                "objects": pending_objects,
            })
            pending_objects = None
            continue

        if (m := _RE_CONN.search(line)):
            context["players"] = int(m.group(1))
            context["world_zdos"] = int(m.group(2))
            context["net_sent_bytes"] = int(m.group(3))
            context["net_recv_bytes"] = int(m.group(4))
            when = ts if ts is not None else last_ts
            if when is not None:
                net.append({"epoch": when, "players": int(m.group(1)),
                            "sent": int(m.group(3)), "recv": int(m.group(4))})

    # An event before the first timestamped line has nothing to place it on.
    # Dropping it is right: an event with no time cannot go on a timeline, and
    # inventing one would put a fake mark under a real player complaint.
    events = [e for e in events if e["epoch"] is not None]
    return {"events": events, "disk": disk, "net": net, "incidents": incidents,
            "context": context, "first_ts": first_ts, "last_ts": last_ts}


def _pct(sorted_vals: list[float], q: float) -> Optional[float]:
    """Nearest-rank percentile. Small n here; no dependency worth adding."""
    if not sorted_vals:
        return None
    idx = max(0, min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def summarise(events: list[dict], kind: str, span_hours: float) -> dict:
    vals = sorted(e["ms"] for e in events if e["kind"] == kind)
    picked = [e for e in events if e["kind"] == kind]
    return {
        "count": len(vals),
        # per_hour is None, not 0, when the log covers no measurable span —
        # "we cannot say" and "it never happens" are different claims.
        "per_hour": round(len(vals) / span_hours, 2) if span_hours > 0 else None,
        "p50_ms": _pct(vals, 0.50),
        "p95_ms": _pct(vals, 0.95),
        "max_ms": vals[-1] if vals else None,
        "total_ms": round(sum(vals), 1),
        "last_epoch": picked[-1]["epoch"] if picked else None,
    }


def _now() -> float:
    """Wall clock, as a seam.

    Not an abstraction for its own sake: every window in this module is
    relative to "now", so a test that cannot pin the clock is a test that
    passes on the day it is written and fails the next. One already did —
    test_endpoint_answers_under_v1 used a hardcoded log dated the previous day
    against a 24 h window, and went red the moment the date rolled over.
    """
    return time.time()


def collect(window_hours: float, now: Optional[float] = None) -> dict:
    """Stall history for the last `window_hours`, from the live log."""
    now = now if now is not None else _now()
    lines = _lines_covering(now - window_hours * 3600)
    parsed = parse_all(lines)
    events, context = parsed["events"], parsed["context"]
    first_ts, last_ts = parsed["first_ts"], parsed["last_ts"]

    cutoff = now - window_hours * 3600
    in_window = [e for e in events if e["epoch"] >= cutoff]

    # The span we can honestly divide by is the part of the window the log
    # actually covers — not the window we were asked for. A server restarted
    # ten minutes ago has not been quiet for six hours; it has been observed
    # for ten minutes, and a rate computed over six would understate it 36x.
    covered_from = max(cutoff, first_ts) if first_ts is not None else None
    covered_to = last_ts
    span_hours = 0.0
    if covered_from is not None and covered_to is not None and covered_to > covered_from:
        span_hours = (covered_to - covered_from) / 3600

    save = summarise(in_window, "save", span_hours)
    gc = summarise(in_window, "gc", span_hours)
    blocked_ms = save["total_ms"] + gc["total_ms"]

    # The findings are the point of the endpoint: numbers become a judgement
    # about hardware, network or configuration, each carrying the evidence that
    # produced it. Everything below the cutoff is dropped first so a finding
    # never quotes data from outside the window it claims to describe.
    _in = lambda rows: [r for r in rows if r["epoch"] >= cutoff]
    findings = _findings.compute(
        saves=[e for e in in_window if e["kind"] == "save"],
        gcs=[e for e in in_window if e["kind"] == "gc"],
        disk=_in(parsed["disk"]), net=_in(parsed["net"]),
        incidents=_in(parsed["incidents"]),
        span_hours=span_hours, interval_s=settings.save_interval,
    )

    return {
        "generated_at": now,
        "window_hours": window_hours,
        "log_file": str(settings.logfile),
        "log_covers_from": covered_from,
        "log_covers_to": covered_to,
        "observed_hours": round(span_hours, 3),
        "truncated": len(lines) >= MAX_TAIL_LINES,
        "events": in_window,
        "save": save,
        "gc": gc,
        "blocked_ms": round(blocked_ms, 1),
        "blocked_ms_per_hour": round(blocked_ms / span_hours, 1) if span_hours > 0 else None,
        "blocked_pct": round(100 * blocked_ms / (span_hours * 3600_000), 4) if span_hours > 0 else None,
        "save_interval_s": settings.save_interval,
        "context": context,
        "findings": findings,
        "log_files_read": len(_rotated_logs(cutoff)) + 1,
    }
