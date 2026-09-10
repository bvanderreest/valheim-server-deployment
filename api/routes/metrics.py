"""
GET /metrics — Prometheus text format (unauthenticated, like /health).

Exposes:
  valheim_server_running         gauge 0/1
  valheim_server_uptime_seconds  gauge
  valheim_players_connected      gauge
  valheim_backup_count           gauge
  valheim_world_size_bytes       gauge
  valheim_last_save_age_seconds  gauge
"""

import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..services import logfmt
from ..routes.server import (
    _get_player_info,
    _get_uptime_seconds,
    _is_running,
    _read_pid,
)
from ..routes.server import _world_bytes as _status_world_bytes

router = APIRouter(tags=["metrics"])


# ── Main-thread stalls ────────────────────────────────────────────────────────
# These are what a player actually FEELS. Everything else about server health is
# academic if the world freezes. Two independent sources, both from the log:
#
#   save stall  PrepareSave clone + ZDOExtraData — the blocking part of a save.
#               The rest of the ~4s "World saved" figure is background I/O.
#   GC pause    Unity's periodic Resources.UnloadUnusedAssets(). Runs roughly
#               hourly, dominated by MarkObjects scanning ~200k loaded objects,
#               and typically frees almost nothing. Not tunable server-side.
#
# The point of exposing both: when a player reports lag at a given minute, you
# can say whether the SERVER stalled then. If it did not, the problem is the
# player's network — which is the question a geographically spread group always
# ends up asking.

_RE_SAVE_CLONE = re.compile(r"PrepareSave: clone done in (\d+)ms")
_RE_SAVE_ZDO = re.compile(r"ZDOExtraData\.PrepareSave done in (\d+) ?ms")
_RE_GC_TOTAL = re.compile(r"^Total: ([0-9.]+) ms \(FindLiveObjects")
_RE_LOADED = re.compile(r"Loaded Objects now: (\d+)")
_RE_CONN = re.compile(r"Connections (\d+) ZDOS:(\d+)\s+sent:(\d+) recv:(\d+)")


def _tail_lines(n: int = 3000) -> list[str]:
    try:
        with settings.logfile.open(errors="replace") as f:
            return deque(f, maxlen=n)
    except OSError:
        return []


def _stall_metrics() -> dict[str, float]:
    """Last observed value for each stall/traffic signal. -1 means not seen."""
    out = {
        "save_stall_seconds": -1.0,
        "save_duration_seconds": -1.0,
        "gc_pause_seconds": -1.0,
        "loaded_objects": -1.0,
        "world_zdos": -1.0,
        "net_sent_bytes": -1.0,
        "net_recv_bytes": -1.0,
    }
    clone = zdo = None
    for line in _tail_lines():
        if (m := _RE_SAVE_CLONE.search(line)):
            clone = int(m.group(1))
        elif (m := _RE_SAVE_ZDO.search(line)):
            zdo = int(m.group(1))
            if clone is not None:
                # Both halves of one PrepareSave; this is the frozen window.
                out["save_stall_seconds"] = (clone + zdo) / 1000
        elif (ms := logfmt.save_total_ms(line)) is not None:
            out["save_duration_seconds"] = ms / 1000
        elif (m := _RE_GC_TOTAL.match(line)):
            out["gc_pause_seconds"] = float(m.group(1)) / 1000
        elif (m := _RE_LOADED.search(line)):
            out["loaded_objects"] = float(m.group(1))
        elif (m := _RE_CONN.search(line)):
            out["world_zdos"] = float(m.group(2))
            out["net_sent_bytes"] = float(m.group(3))
            out["net_recv_bytes"] = float(m.group(4))
    return out


def _rss_bytes(pid: int | None) -> int:
    if not pid:
        return -1
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return -1


def _gauge(name: str, value: float | int, help_text: str = "") -> str:
    lines = []
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name} {value}")
    return "\n".join(lines)


def _backup_count() -> int:
    backup_dir = settings.script_dir / "backups"
    if not backup_dir.is_dir():
        return 0
    return sum(1 for _ in backup_dir.glob("world-*.tar.gz"))


def _world_size_bytes() -> int:
    """Delegates to the /status implementation — deliberately not a second one.

    This used to carry its own copy: two hardcoded paths, both ending in
    `<World>.db`. Valheim 1.0 moved the world into a `<World>/` directory of
    .chunk files, so the flat file stopped existing and this reported 0 while
    /status — which was layout-aware — correctly reported 12,962,792 bytes.
    Two implementations of one question will always drift; the fix is to have
    one.
    """
    return _status_world_bytes() or 0


def _last_save_age_seconds() -> float:
    logfile = settings.logfile
    if not logfile.exists():
        return -1
    try:
        last_save_line = None
        with logfile.open() as f:
            for line in f:
                if logfmt.is_save_done(line):
                    last_save_line = line
        if not last_save_line:
            return -1
        m = logfmt.RE_TIMESTAMP.search(last_save_line)
        if not m:
            return -1
        ts = datetime.strptime(m.group(0), logfmt.TIMESTAMP_FORMAT)
        return time.time() - ts.timestamp()
    except Exception:
        return -1


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def get_metrics() -> str:
    running = _is_running()
    pid = _read_pid() if running else None
    uptime = _get_uptime_seconds(pid) if pid is not None else 0
    players = _get_player_info().count if running else 0

    blocks = [
        _gauge("valheim_server_running", 1 if running else 0, "1 if the Valheim server process is running"),
        _gauge("valheim_server_uptime_seconds", uptime, "Seconds since the server process started"),
        _gauge("valheim_players_connected", players, "Number of players currently connected"),
        _gauge("valheim_backup_count", _backup_count(), "Number of world backup archives on disk"),
        _gauge("valheim_world_size_bytes", _world_size_bytes(), "Size of the world .db file in bytes"),
        _gauge("valheim_last_save_age_seconds", _last_save_age_seconds(), "Seconds since last world save (-1 if unknown)"),
    ]

    # Stall + traffic signals. All -1 when not yet observed, never 0 — zero is a
    # legitimate value for several of these and would read as "no stall" rather
    # than "no data", which is the failure mode that makes a dashboard lie.
    st = _stall_metrics()
    blocks += [
        _gauge("valheim_save_stall_seconds", st["save_stall_seconds"],
               "Main-thread freeze during the last save (PrepareSave clone + ZDOExtraData). This is the part players feel."),
        _gauge("valheim_save_duration_seconds", st["save_duration_seconds"],
               "Total wall time of the last world save, most of which is background I/O"),
        _gauge("valheim_gc_pause_seconds", st["gc_pause_seconds"],
               "Last Unity UnloadUnusedAssets pause. Runs roughly hourly and blocks the main thread."),
        _gauge("valheim_loaded_objects", st["loaded_objects"],
               "Unity objects resident. Drives GC pause length."),
        _gauge("valheim_world_zdos", st["world_zdos"],
               "ZDOs in the world. Drives save cost."),
        _gauge("valheim_net_sent_bytes", st["net_sent_bytes"], "Bytes sent, from the periodic Connections line"),
        _gauge("valheim_net_recv_bytes", st["net_recv_bytes"], "Bytes received, from the periodic Connections line"),
        _gauge("valheim_process_rss_bytes", _rss_bytes(pid), "Resident memory of the server process (-1 if unknown)"),
    ]
    return "\n".join(blocks) + "\n"
