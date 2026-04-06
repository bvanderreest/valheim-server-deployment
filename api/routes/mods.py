import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key
from ..config import settings
from ..models import ModActionResponse, ModInstallRequest, ModInstallResponse, ModsResponse
from ..services import mods as mod_service

router = APIRouter(tags=["mods"])

_PACKAGE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _validate_pkg(package_id: str) -> None:
    if not _PACKAGE_ID_RE.match(package_id):
        raise HTTPException(status_code=400, detail=f"Invalid package_id: {package_id!r}")


def _derive_package_id(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).stem
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return name[:64] or "mod"


@router.get("/mods", response_model=ModsResponse)
async def get_mods(_: str = Depends(require_api_key)) -> ModsResponse:
    mod_list = mod_service.list_mods(settings.mod_dir, settings.mod_disabled_dir)
    return ModsResponse(
        mods=mod_list,
        count=len(mod_list),
        mod_dir=str(settings.mod_dir),
    )


@router.post("/mods/install", response_model=ModInstallResponse, status_code=201)
async def install_mod(
    body: ModInstallRequest,
    _: str = Depends(require_api_key),
) -> ModInstallResponse:
    package_id = body.package_id or _derive_package_id(body.source_url)
    if not _PACKAGE_ID_RE.match(package_id):
        raise HTTPException(status_code=400, detail=f"Invalid package_id: {package_id!r}")

    try:
        mod_info = mod_service.install_mod(
            source_url=body.source_url,
            package_id=package_id,
            mod_dir=settings.mod_dir,
            allowed_sources=settings.mod_allowed_sources_list,
            max_size_bytes=settings.mod_max_size_mb * 1024 * 1024,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Install failed: {exc}") from exc

    return ModInstallResponse(
        package_id=mod_info.package_id,
        name=mod_info.name,
        version=mod_info.version,
        installed=True,
        message=f"Installed {mod_info.name} v{mod_info.version}",
    )


@router.delete("/mods/{package_id}", response_model=ModActionResponse)
async def delete_mod(
    package_id: str,
    _: str = Depends(require_api_key),
) -> ModActionResponse:
    _validate_pkg(package_id)
    try:
        name = mod_service.delete_mod(
            package_id,
            settings.mod_dir,
            settings.mod_disabled_dir,
            settings.mod_trash_dir,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModActionResponse(
        package_id=package_id,
        action="deleted",
        success=True,
        message=f"Moved {name!r} to trash",
    )


@router.post("/mods/{package_id}/enable", response_model=ModActionResponse)
async def enable_mod(
    package_id: str,
    _: str = Depends(require_api_key),
) -> ModActionResponse:
    _validate_pkg(package_id)
    try:
        mod_service.enable_mod(package_id, settings.mod_dir, settings.mod_disabled_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModActionResponse(
        package_id=package_id,
        action="enabled",
        success=True,
        message=f"Mod {package_id!r} enabled",
    )


@router.post("/mods/{package_id}/disable", response_model=ModActionResponse)
async def disable_mod(
    package_id: str,
    _: str = Depends(require_api_key),
) -> ModActionResponse:
    _validate_pkg(package_id)
    try:
        mod_service.disable_mod(package_id, settings.mod_dir, settings.mod_disabled_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ModActionResponse(
        package_id=package_id,
        action="disabled",
        success=True,
        message=f"Mod {package_id!r} disabled",
    )
