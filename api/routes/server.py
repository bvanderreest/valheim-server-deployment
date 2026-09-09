import os
import re
import socket
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..config import settings
from ..models import ActionResponse, ConnectionInfo, PlayerInfo, StatusResponse

router = APIRouter()


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _read_pid() -> Optional[int]:
    try:
        return int(settings.pidfile.read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _is_running() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # Signal 0: check process exists, sends nothing
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _get_uptime_seconds(pid: int) -> int:
    try:
        # /proc/<pid> mtime equals the process start time — mirrors helpers.sh get_uptime()
        start_time = Path(f"/proc/{pid}").stat().st_mtime
        return max(0, int(time.time() - start_time))
    except (OSError, FileNotFoundError):
        return 0


def _format_uptime(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    if secs:
        parts.append(f"{secs}s")
    return " ".join(parts) or "0s"


def _tail_log(n: int) -> list[str]:
    logfile = settings.logfile
    if not logfile.exists():
        return []
    try:
        with logfile.open("r", errors="replace") as f:
            return list(deque(f, maxlen=n))
    except OSError:
        return []


def _get_player_info() -> PlayerInfo:
    tail = _tail_log(2000)

    # Anchor to the last server start so we only count connections in the
    # current session — avoids treating historical log entries as live players
    start_idx = 0
    for i, line in enumerate(tail):
        if "Valheim version:" in line or "Game server connected" in line:
            start_idx = i
    session_lines = tail[start_idx:]

    connected = sum(1 for line in session_lines if "Server: New peer connected" in line)
    disconnected = sum(1 for line in session_lines if "RPC_Disconnect" in line)
    count = max(0, connected - disconnected)

    names: list[str] = []
    for line in session_lines:
        if "Got character ZDOID from" not in line:
            continue
        if " 0:0" in line:
            continue
        m = re.search(r"Got character ZDOID from (.+?) :", line)
        if m:
            names.append(m.group(1).strip())

    return PlayerInfo(count=count, max=settings.max_players, names=sorted(set(names)))


def _get_version() -> Optional[str]:
    logfile = settings.logfile
    if not logfile.exists():
        return None
    try:
        with logfile.open("r", errors="replace") as f:
            for line in f:
                m = re.search(r"Valheim version: (.+)", line)
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return None


# Valheim never logs "Join code: NNNNNN". VERIFIED against the live server
# 2026-09-08 — the real lines are:
#   Session "Lowood-AU" registered with join code 366974
#   Session "Lowood-AU" with join code 366974 and IP ... is active
# The old pattern matched neither, so join_code was always null.
_JOIN_CODE_RE = re.compile(r"join code[:\s]+([0-9A-Za-z]{4,16})", re.IGNORECASE)


def _rss_mb(pid: int | None) -> float | None:
    """Resident memory of the server process, in MB."""
    if not pid:
        return None
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    return None


def _save_seconds() -> float | None:
    """How long the last world save took. Valheim logs 'World saved ( 4637.014ms )'.

    This is the number that tells an operator whether saves are getting
    expensive as the world grows, so it is worth surfacing.
    """
    for line in reversed(_tail_log(400)):
        m = re.search(r"World saved \(\s*([0-9.]+)ms\s*\)", line)
        if m:
            try:
                return round(float(m.group(1)) / 1000, 2)
            except ValueError:
                return None
    return None


def _world_objects() -> int | None:
    """ZDO count from 'Saved 419858 ZDOs' — the real driver of save cost."""
    for line in reversed(_tail_log(400)):
        m = re.search(r"Saved (\d+) ZDOs", line)
        if m:
            return int(m.group(1))
    return None


def _world_bytes() -> int | None:
    """Size of the live world file, whatever the save layout."""
    world_dir = settings.savedir / "worlds_local"
    if not world_dir.is_dir():
        return None
    flat = world_dir / f"{settings.world_name}.db"
    if flat.is_file():
        return flat.stat().st_size
    chunked = world_dir / settings.world_name
    if chunked.is_dir():
        try:
            return sum(f.stat().st_size for f in chunked.rglob("*") if f.is_file())
        except OSError:
            return None
    return None


def _backups() -> list[dict]:
    """Manual tarballs, newest first. There is no dedicated backups endpoint,
    and a console cannot show backup AGE — the thing that actually matters —
    without this."""
    d = settings.backup_dir
    if not d or not Path(d).is_dir():
        return []
    out = []
    try:
        files = sorted(Path(d).glob("*.tar.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    except OSError:
        return []
    for f in files[:20]:
        try:
            st = f.stat()
        except OSError:
            continue
        out.append({
            "name": f.name,
            "bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                        .isoformat().replace("+00:00", "Z"),
        })
    return out


def _public_endpoint() -> str | None:
    """The address crossplay players actually connect to.

    With -crossplay the server registers a PUBLIC endpoint with PlayFab and
    logs it. _get_server_ip() returns the LAN address, which is correct for a
    Steam-direct connection on the same network and useless to anyone outside
    it. Prefer what the server told PlayFab.
    """
    for line in reversed(_tail_log(4000)):
        m = re.search(r"serverIP used to register the server:\s*([0-9.]+:[0-9]+)", line)
        if m:
            return m.group(1)
        m = re.search(r"Register PlayFab server .* with IP\s*([0-9.]+:[0-9]+)", line)
        if m:
            return m.group(1)
    return None


def _get_join_code() -> Optional[str]:
    # The code is issued once at startup, so a 200-line tail loses it as soon
    # as the server logs anything. Scan a much deeper window, and fall back to
    # the whole file if needed — the log is rotated on every start, so this
    # stays bounded in practice.
    for depth in (2000, 50000):
        matches = _JOIN_CODE_RE.findall("\n".join(_tail_log(depth)))
        if matches:
            return matches[-1]
    return None


def _get_last_save() -> Optional[str]:
    logfile = settings.logfile
    if not logfile.exists():
        return None
    last: Optional[str] = None
    try:
        with logfile.open("r", errors="replace") as f:
            for line in f:
                if "World saved" in line:
                    m = re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}", line)
                    if m:
                        last = m.group(0)
    except OSError:
        pass
    if last is None:
        return None
    try:
        # Valheim logs US format MM/DD/YYYY. Proven by archived entries like
        # "06/25/2026" — day 25 cannot be a month. Using %d/%m here silently
        # mis-parsed dates for day <= 12 and returned None for day > 12
        # (ValueError), so last_save was wrong or missing most of the month.
        # metrics.py already had this right; the two disagreed.
        dt = datetime.strptime(last, "%m/%d/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _get_server_ip() -> str:
    try:
        # Connect a UDP socket to a routable address (no data sent) to discover
        # the outbound interface IP — avoids returning 127.x.x.x loopback aliases
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _run_manager_command(command: str) -> None:
    """Run a valheim-server-manager.sh command in a background thread."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            [str(settings.manager_script), command],
            cwd=str(settings.script_dir),
            timeout=300,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("manager command %r exited %d: %s", command, result.returncode, result.stderr.strip())
    except subprocess.TimeoutExpired:
        logger.error("manager command %r timed out after 300s", command)
    except Exception as exc:
        logger.error("manager command %r raised: %s", command, exc)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/status", response_model=StatusResponse, response_model_by_alias=True)
async def get_status() -> StatusResponse:
    running = _is_running()
    pid = _read_pid() if running else None
    uptime_s = _get_uptime_seconds(pid) if pid else 0

    version = None
    join_code = None
    last_save = None
    players = PlayerInfo(count=0, max=settings.max_players, names=[])

    if running:
        version = _get_version()
        join_code = _get_join_code()
        last_save = _get_last_save()
        players = _get_player_info()

    ip = _get_server_ip()

    return StatusResponse(
        server_type=settings.server_type,
        server_label=settings.server_label,
        server_name=settings.server_name,
        world_name=settings.world_name,
        running=running,
        pid=pid,
        uptime_seconds=uptime_s,
        uptime_human=_format_uptime(uptime_s),
        version=version,
        players=players,
        connection=ConnectionInfo(
            ip=ip,
            port=settings.port,
            join_code=join_code,
            crossplay=settings.crossplay.lower() == "true",
            public=settings.public == "1",
        ),
        last_save=last_save,
        extras={
            "crossplay": settings.crossplay.lower() == "true",
            "public": settings.public == "1",
            # Everything below is what a console needs and cannot derive:
            # memory pressure, how expensive saves have become, how big the
            # world is, and — most importantly — how old the newest backup is.
            "rss_mb": _rss_mb(pid) if running else None,
            "save_seconds": _save_seconds() if running else None,
            "world_objects": _world_objects() if running else None,
            "world_bytes": _world_bytes(),
            "backups": _backups(),
            # What a crossplay player connects to, as registered with PlayFab.
            # connection.ip stays the LAN address for Steam-direct joins.
            "public_endpoint": _public_endpoint() if running else None,
        },
        deprecated={
            "ip": ip,
            "join_code": join_code,
            "player_count": players.count,
        },
    )


# Valid server control actions and their human-readable acceptance messages.
_VALID_ACTIONS: dict[str, str] = {
    "start":   "Start command accepted. Check /status for progress.",
    "stop":    "Stop command accepted. Server will shut down gracefully (up to 60s).",
    "restart": "Restart command accepted.",
    "backup":  "Backup command accepted.",
    "update":  "Update command accepted. Server will stop, update, and exit.",
}


@router.post("/server/{action}", status_code=202, response_model=ActionResponse)
async def server_action(action: str, background_tasks: BackgroundTasks) -> ActionResponse:
    if action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown action '{action}'. Valid actions: {list(_VALID_ACTIONS)}",
        )
    if action == "start" and _is_running():
        raise HTTPException(status_code=409, detail="Server is already running.")
    if action == "stop" and not _is_running():
        raise HTTPException(status_code=409, detail="Server is not running.")

    background_tasks.add_task(_run_manager_command, action)
    return ActionResponse(
        action=action,
        accepted=True,
        message=_VALID_ACTIONS[action],
    )


@router.get("/capabilities")
async def get_capabilities() -> dict:
    return {
        "server_type": settings.server_type,
        "capabilities": {
            "control": list(_VALID_ACTIONS),
            "config": True,
            "modifiers": True,
            "mods": True,
            "log_stream": True,
        },
    }
