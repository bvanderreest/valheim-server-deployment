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


MASK = "****"


def _mask(key: str, value: str) -> str:
    if "password" in key.lower():
        return MASK
    return value


def _validate(changes: dict[str, str]) -> None:
    """Reject values that would break the server or lock everyone out.

    GET /config masks PASSWORD as "****". A UI that renders that into an input
    and posts the form back would set the real password TO "****" — nobody
    could join, and the cause would be invisible. Refuse the sentinel outright;
    a client that means "unchanged" must omit the key.
    """
    pw = changes.get("PASSWORD")
    if pw is not None:
        if pw == MASK:
            raise HTTPException(
                status_code=422,
                detail=f'PASSWORD cannot be set to "{MASK}" — that is the mask '
                       "returned by GET /config, not a value. Omit the key to "
                       "leave the password unchanged.",
            )
        # Valheim's own rules; violating them makes the server refuse to start.
        if len(pw) < 5:
            raise HTTPException(status_code=422, detail="PASSWORD must be at least 5 characters.")
        world = changes.get("WORLD_NAME") or _read_env(settings.script_dir / ".env").get("WORLD_NAME", "")
        if world and (pw in world or world in pw):
            raise HTTPException(
                status_code=422,
                detail="PASSWORD must not contain, or be contained in, the world name — "
                       "Valheim refuses to start.",
            )

    for key in ("PORT", "MAX_PLAYERS", "SAVE_INTERVAL", "BACKUPS_KEEP"):
        if key in changes:
            try:
                n = int(changes[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"{key} must be an integer.") from None
            if key == "PORT" and not (1024 <= n <= 65535):
                raise HTTPException(status_code=422, detail="PORT must be between 1024 and 65535.")
            if key != "PORT" and n < 1:
                raise HTTPException(status_code=422, detail=f"{key} must be 1 or greater.")


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

    _validate(body.changes)

    env_file = settings.script_dir / ".env"
    _write_env_atomic(env_file, body.changes)

    restart_required = bool(set(body.changes) & _RESTART_REQUIRED_KEYS)
    return ConfigUpdateResponse(
        applied={k: _mask(k, v) for k, v in body.changes.items()},
        restart_required=restart_required,
    )
