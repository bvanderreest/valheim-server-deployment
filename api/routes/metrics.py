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
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..routes.server import _get_uptime_seconds, _is_running, _read_pid, _get_player_info

router = APIRouter(tags=["metrics"])


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
    world_name = settings.world_name
    for candidate in [
        Path("/srv/valheim/worlds/worlds_local") / f"{world_name}.db",
        settings.script_dir / "worlds" / "worlds_local" / f"{world_name}.db",
    ]:
        if candidate.exists():
            return candidate.stat().st_size
    return 0


def _last_save_age_seconds() -> float:
    logfile = settings.logfile
    if not logfile.exists():
        return -1
    try:
        last_save_line = None
        with logfile.open() as f:
            for line in f:
                if "World saved" in line:
                    last_save_line = line
        if not last_save_line:
            return -1
        m = re.match(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}):", last_save_line)
        if not m:
            return -1
        ts = datetime.strptime(m.group(1), "%m/%d/%Y %H:%M:%S")
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
    return "\n".join(blocks) + "\n"
