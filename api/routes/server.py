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
    connected = sum(1 for line in tail if "Server: New peer connected" in line)
    disconnected = sum(1 for line in tail if "RPC_Disconnect" in line)
    count = max(0, connected - disconnected)

    names: list[str] = []
    for line in tail:
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


def _get_join_code() -> Optional[str]:
    tail = _tail_log(200)
    matches = [line for line in tail if re.search(r"Join code: [0-9a-zA-Z]{6}", line)]
    if not matches:
        return None
    m = re.search(r"Join code: ([0-9a-zA-Z]{6})", matches[-1])
    return m.group(1) if m else None


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
        dt = datetime.strptime(last, "%d/%m/%Y %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _get_server_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
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

@router.get("/status", response_model=StatusResponse)
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
            ip=_get_server_ip(),
            port=settings.port,
            join_code=join_code,
            crossplay=settings.crossplay.lower() == "true",
            public=settings.public == "1",
        ),
        last_save=last_save,
    )


@router.post("/server/start", status_code=202, response_model=ActionResponse)
async def start_server(background_tasks: BackgroundTasks) -> ActionResponse:
    if _is_running():
        raise HTTPException(status_code=409, detail="Server is already running.")
    background_tasks.add_task(_run_manager_command, "start")
    return ActionResponse(
        accepted=True,
        message="Start command accepted. Check /status for progress.",
    )


@router.post("/server/stop", status_code=202, response_model=ActionResponse)
async def stop_server(background_tasks: BackgroundTasks) -> ActionResponse:
    if not _is_running():
        raise HTTPException(status_code=409, detail="Server is not running.")
    background_tasks.add_task(_run_manager_command, "stop")
    return ActionResponse(
        accepted=True,
        message="Stop command accepted. Server will shut down gracefully (up to 60s).",
    )


@router.post("/server/restart", status_code=202, response_model=ActionResponse)
async def restart_server(background_tasks: BackgroundTasks) -> ActionResponse:
    background_tasks.add_task(_run_manager_command, "restart")
    return ActionResponse(accepted=True, message="Restart command accepted.")


@router.post("/server/backup", status_code=202, response_model=ActionResponse)
async def backup_server(background_tasks: BackgroundTasks) -> ActionResponse:
    background_tasks.add_task(_run_manager_command, "backup")
    return ActionResponse(accepted=True, message="Backup command accepted.")


@router.get("/capabilities")
async def get_capabilities() -> dict:
    return {
        "server_type": settings.server_type,
        "capabilities": {
            "control": ["start", "stop", "restart", "backup"],
            "config": False,
            "mods": False,
            "log_stream": True,
        },
    }
