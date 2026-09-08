"""Gameplay configuration: preset, difficulty modifiers and setkeys.

Separate from /config because these live in modifiers.conf rather than .env,
and because they are a different kind of setting: /config is server identity
and networking, this is how the game plays.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..config import settings
from ..services import modifiers as mod_service

router = APIRouter(tags=["modifiers"])


def _conf_path() -> Path:
    # modifiers.conf sits beside the manager scripts, not in the save dir.
    base = getattr(settings, "script_dir", None) or Path(__file__).resolve().parents[2]
    return Path(base) / "modifiers.conf"


@router.get("/modifiers")
async def get_modifiers(_: str = Depends(require_api_key)) -> dict:
    try:
        return mod_service.read_modifiers(_conf_path())
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"modifiers.conf not found at {_conf_path()}",
        ) from None


@router.patch("/modifiers")
async def patch_modifiers(payload: dict, _: str = Depends(require_api_key)) -> dict:
    changes = payload.get("changes", payload)
    try:
        return mod_service.write_modifiers(_conf_path(), changes)
    except mod_service.ValidationError as exc:
        # 422: the request was understood but the values are not acceptable.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"modifiers.conf not found at {_conf_path()}",
        ) from None
