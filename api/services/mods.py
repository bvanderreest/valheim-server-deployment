"""
Mod management service — filesystem operations, inventory, download/install.

The inventory file (mods.json) in each plugins directory tracks metadata that
cannot be derived from the mod files alone (source URL, install timestamp).

Directory layout:
  <mod_dir>/              — active plugins (BepInEx/plugins/)
    <package_id>/         — one subdirectory per mod
      manifest.json       — Thunderstore manifest (name, version_number, …)
      mods.json           — inventory: {package_id: {name, version, source, installed_at}}
  <mod_disabled_dir>/     — inactive plugins (BepInEx/plugins_disabled/)
  <mod_trash_dir>/        — soft-deleted plugins (BepInEx/plugins_trash/)
"""

import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..models import ModInfo

_PACKAGE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_INVENTORY_FILE = "mods.json"


def validate_package_id(package_id: str) -> bool:
    return bool(_PACKAGE_ID_RE.match(package_id))


# ─── Inventory helpers ────────────────────────────────────────────────────────

def _read_inventory(base_dir: Path) -> dict:
    inv_file = base_dir / _INVENTORY_FILE
    if not inv_file.exists():
        return {}
    try:
        return json.loads(inv_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_inventory(base_dir: Path, inventory: dict) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    tmp = base_dir / ".mods.json.tmp"
    tmp.write_text(json.dumps(inventory, indent=2))
    tmp.replace(base_dir / _INVENTORY_FILE)


def _parse_manifest(plugin_dir: Path) -> dict:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


# ─── List ─────────────────────────────────────────────────────────────────────

def list_mods(mod_dir: Path, mod_disabled_dir: Path) -> list[ModInfo]:
    result: list[ModInfo] = []

    for enabled, base_dir in [(True, mod_dir), (False, mod_disabled_dir)]:
        if not base_dir.exists():
            continue
        inventory = _read_inventory(base_dir)
        for plugin_dir in sorted(base_dir.iterdir()):
            if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
                continue
            manifest = _parse_manifest(plugin_dir)
            inv_entry = inventory.get(plugin_dir.name, {})
            result.append(ModInfo(
                package_id=plugin_dir.name,
                name=manifest.get("name") or inv_entry.get("name") or plugin_dir.name,
                version=manifest.get("version_number") or inv_entry.get("version") or "unknown",
                enabled=enabled,
                description=manifest.get("description"),
                website_url=manifest.get("website_url"),
                installed_at=inv_entry.get("installed_at", ""),
                source=inv_entry.get("source"),
            ))

    return result


# ─── Install ──────────────────────────────────────────────────────────────────

def _check_zip_for_traversal(zip_path: Path) -> None:
    """Raise ValueError if any entry path would escape the extraction directory."""
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if ".." in name or name.startswith("/"):
                raise ValueError(f"Unsafe path in archive: {name!r}")


def _derive_package_id(url: str) -> str:
    """Derive a safe package_id from the URL filename."""
    path = urlparse(url).path
    name = Path(path).stem  # strip extension
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return name[:64] or "mod"


def install_mod(
    source_url: str,
    package_id: str,
    mod_dir: Path,
    allowed_sources: list[str],
    max_size_bytes: int = 100 * 1024 * 1024,
) -> ModInfo:
    """Download, validate, and extract a mod ZIP. Returns the installed ModInfo."""
    # Source URL allowlist (deny-by-default)
    parsed = urlparse(source_url)
    if parsed.hostname not in allowed_sources:
        raise ValueError(
            f"Source not allowed: {parsed.hostname!r}. "
            f"Allowed hosts: {allowed_sources}"
        )

    if not validate_package_id(package_id):
        raise ValueError(f"Invalid package_id: {package_id!r}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip = Path(tmpdir) / "mod.zip"

        # Stream download with size enforcement
        downloaded = 0
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            with client.stream("GET", source_url) as resp:
                resp.raise_for_status()
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > max_size_bytes:
                    raise ValueError(
                        f"Archive too large: {int(content_length) // 1024 // 1024}MB "
                        f"(limit {max_size_bytes // 1024 // 1024}MB)"
                    )
                with tmp_zip.open("wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        downloaded += len(chunk)
                        if downloaded > max_size_bytes:
                            raise ValueError(
                                f"Archive exceeded {max_size_bytes // 1024 // 1024}MB limit during download"
                            )
                        fh.write(chunk)

        if not zipfile.is_zipfile(tmp_zip):
            raise ValueError("Downloaded file is not a valid ZIP archive")

        # Reject archives containing path-traversal entries
        _check_zip_for_traversal(tmp_zip)

        # Read manifest before extraction
        manifest: dict = {}
        with zipfile.ZipFile(tmp_zip) as zf:
            try:
                manifest = json.loads(zf.read("manifest.json"))
            except (KeyError, json.JSONDecodeError):
                pass

        # Extract to a temp subdirectory, then move atomically into plugins/
        extract_dir = Path(tmpdir) / "extracted"
        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(extract_dir)

        dest = mod_dir / package_id
        if dest.exists():
            shutil.rmtree(dest)
        mod_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extract_dir), str(dest))

    installed_at = datetime.now(timezone.utc).isoformat()
    inventory = _read_inventory(mod_dir)
    inventory[package_id] = {
        "name": manifest.get("name", package_id),
        "version": manifest.get("version_number", "unknown"),
        "source": source_url,
        "installed_at": installed_at,
    }
    _write_inventory(mod_dir, inventory)

    return ModInfo(
        package_id=package_id,
        name=manifest.get("name", package_id),
        version=manifest.get("version_number", "unknown"),
        enabled=True,
        description=manifest.get("description"),
        website_url=manifest.get("website_url"),
        installed_at=installed_at,
        source=source_url,
    )


# ─── Delete ───────────────────────────────────────────────────────────────────

def delete_mod(
    package_id: str,
    mod_dir: Path,
    mod_disabled_dir: Path,
    mod_trash_dir: Path,
) -> str:
    """Move a mod (enabled or disabled) to trash. Returns the mod display name."""
    if not validate_package_id(package_id):
        raise ValueError(f"Invalid package_id: {package_id!r}")

    source = mod_dir / package_id
    inv_dir = mod_dir
    if not source.exists():
        source = mod_disabled_dir / package_id
        inv_dir = mod_disabled_dir
    if not source.exists():
        raise FileNotFoundError(f"Mod not found: {package_id!r}")

    mod_trash_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.move(str(source), str(mod_trash_dir / f"{package_id}_{ts}"))

    inventory = _read_inventory(inv_dir)
    name = inventory.pop(package_id, {}).get("name", package_id)
    _write_inventory(inv_dir, inventory)

    return name


# ─── Enable / Disable ─────────────────────────────────────────────────────────

def enable_mod(package_id: str, mod_dir: Path, mod_disabled_dir: Path) -> None:
    """Move a mod from plugins_disabled/ to plugins/."""
    if not validate_package_id(package_id):
        raise ValueError(f"Invalid package_id: {package_id!r}")

    source = mod_disabled_dir / package_id
    if not source.exists():
        if (mod_dir / package_id).exists():
            raise ValueError(f"Mod {package_id!r} is already enabled")
        raise FileNotFoundError(f"Mod not found: {package_id!r}")

    mod_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(mod_dir / package_id))

    # Migrate inventory entry
    disabled_inv = _read_inventory(mod_disabled_dir)
    enabled_inv = _read_inventory(mod_dir)
    entry = disabled_inv.pop(package_id, {})
    if entry:
        enabled_inv[package_id] = entry
    _write_inventory(mod_disabled_dir, disabled_inv)
    _write_inventory(mod_dir, enabled_inv)


def disable_mod(package_id: str, mod_dir: Path, mod_disabled_dir: Path) -> None:
    """Move a mod from plugins/ to plugins_disabled/."""
    if not validate_package_id(package_id):
        raise ValueError(f"Invalid package_id: {package_id!r}")

    source = mod_dir / package_id
    if not source.exists():
        if (mod_disabled_dir / package_id).exists():
            raise ValueError(f"Mod {package_id!r} is already disabled")
        raise FileNotFoundError(f"Mod not found: {package_id!r}")

    mod_disabled_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(mod_disabled_dir / package_id))

    # Migrate inventory entry
    enabled_inv = _read_inventory(mod_dir)
    disabled_inv = _read_inventory(mod_disabled_dir)
    entry = enabled_inv.pop(package_id, {})
    if entry:
        disabled_inv[package_id] = entry
    _write_inventory(mod_dir, disabled_inv)
    _write_inventory(mod_disabled_dir, enabled_inv)
