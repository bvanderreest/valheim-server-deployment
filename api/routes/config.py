import fcntl
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..config import settings
from ..models import ConfigResponse, ConfigUpdateRequest, ConfigUpdateResponse

router = APIRouter(tags=["config"])

# Keys that are never returned or written via the API (deny-by-default).
_EXCLUDED_KEYS: frozenset[str] = frozenset({
    "API_KEYS", "API_ENABLED", "API_HOST", "API_PORT", "CORS_ORIGINS", "LOG_DIR",
})

# Keys that operators may change via PATCH /config.
_EDITABLE_KEYS: frozenset[str] = frozenset({
    "SERVER_NAME", "WORLD_NAME", "PASSWORD", "PORT", "PUBLIC", "CROSSPLAY",
    "MAX_PLAYERS", "SAVE_INTERVAL", "BACKUPS_KEEP",
})

# A change to any of these requires a server restart to take effect.
_RESTART_REQUIRED_KEYS: frozenset[str] = frozenset({
    "SERVER_NAME", "WORLD_NAME", "PASSWORD", "PORT", "PUBLIC", "CROSSPLAY",
})

_MAX_BACKUPS = 10


def _mask(key: str, value: str) -> str:
    if "password" in key.lower():
        return "****"
    return value


def _read_env(env_file: Path) -> dict[str, str]:
    """Read .env, returning only non-excluded key-value pairs."""
    if not env_file.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw_val = stripped.partition("=")
        key = key.strip()
        if key in _EXCLUDED_KEYS:
            continue
        result[key] = raw_val.strip().strip('"').strip("'")
    return result


def _write_env_atomic(env_file: Path, updates: dict[str, str]) -> None:
    """Apply updates to env_file atomically with file locking and rolling backup."""
    existing_lines: list[str] = []
    if env_file.exists():
        existing_lines = env_file.read_text().splitlines(keepends=True)

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.partition("=")[0].strip()
        if key in updates:
            new_lines.append(f'{key}="{updates[key]}"\n')
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Append keys not already present in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f'{key}="{value}"\n')

    # Rolling backup (keep most recent _MAX_BACKUPS)
    if env_file.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = env_file.parent / f".env.bak.{ts}"
        shutil.copy2(env_file, backup)
        old_backups = sorted(env_file.parent.glob(".env.bak.*"))
        for old in old_backups[:-_MAX_BACKUPS]:
            old.unlink(missing_ok=True)

    # Atomic write: write to temp then rename
    tmp = env_file.parent / ".env.tmp"
    with tmp.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.writelines(new_lines)
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)
    tmp.replace(env_file)


@router.get("/config", response_model=ConfigResponse)
async def get_config(_: str = Depends(require_api_key)) -> ConfigResponse:
    env_file = settings.script_dir / ".env"
    raw = _read_env(env_file)
    masked = {k: _mask(k, v) for k, v in raw.items()}
    return ConfigResponse(
        server_type=settings.server_type,
        server_label=settings.server_label,
        config=masked,
        config_file=str(env_file),
        editable_keys=sorted(_EDITABLE_KEYS),
    )


@router.patch("/config", response_model=ConfigUpdateResponse)
async def patch_config(
    body: ConfigUpdateRequest,
    _: str = Depends(require_api_key),
) -> ConfigUpdateResponse:
    invalid = set(body.changes) - _EDITABLE_KEYS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or non-editable key(s): {sorted(invalid)}. "
                   f"Allowed keys: {sorted(_EDITABLE_KEYS)}",
        )

    env_file = settings.script_dir / ".env"
    _write_env_atomic(env_file, body.changes)

    restart_required = bool(set(body.changes) & _RESTART_REQUIRED_KEYS)
    return ConfigUpdateResponse(
        applied=body.changes,
        restart_required=restart_required,
    )
