"""Read and write modifiers.conf — the gameplay configuration.

modifiers.conf is a bash file sourced by helpers.sh. Its values become
`-preset`, `-modifier` and `-setkey` arguments on the server process, so every
value written here is validated against a strict allow-list: unvalidated input
would be an argument-injection surface on a process launch.

Writes are surgical block replacements rather than a regeneration, because the
file carries extensive operator-facing comments that must survive a round trip.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── Allow-lists (the whole security model of this module) ────────────────────

PRESETS: tuple[str, ...] = (
    "casual", "easy", "normal", "hard", "hardcore", "immersive", "hammer",
)

# What each preset sets, so the UI can show a baseline and what overrides it.
PRESET_BASELINE: dict[str, dict[str, str]] = {
    "casual":    {"Combat": "veryeasy", "DeathPenalty": "casual",   "Resources": "muchmore", "Raids": "none", "Portals": "casual"},
    "easy":      {"Combat": "easy",     "DeathPenalty": "easy",     "Resources": "more",     "Raids": "less"},
    "normal":    {},
    "hard":      {"Combat": "hard",     "DeathPenalty": "hard",     "Resources": "less",     "Raids": "more", "Portals": "hard"},
    "hardcore":  {"Combat": "veryhard", "DeathPenalty": "hardcore", "Resources": "less",     "Raids": "more", "Portals": "veryhard"},
    "immersive": {"Combat": "hard",     "DeathPenalty": "hard",     "Resources": "less",     "Raids": "more", "Portals": "veryhard"},
    "hammer":    {"DeathPenalty": "casual", "Resources": "muchmore", "Raids": "none", "Portals": "casual"},
}

MODIFIER_OPTIONS: dict[str, tuple[str, ...]] = {
    "Combat":       ("veryeasy", "easy", "hard", "veryhard"),
    "DeathPenalty": ("casual", "veryeasy", "easy", "hard", "hardcore"),
    "Resources":    ("muchless", "less", "more", "muchmore", "most"),
    "Raids":        ("none", "muchless", "less", "more", "muchmore"),
    "Portals":      ("casual", "hard", "veryhard"),
}

TOGGLE_KEYS: tuple[str, ...] = (
    "nomap",
    "nobuildcost", "nocraftcost", "noworkbench",
    "allpiecesunlocked", "allrecipesunlocked", "dungeonbuild",
    "noportals", "nobossportals", "teleportall",
    "passivemobs", "playerevents",
    "deathkeepequip", "deathdeleteunequipped", "deathdeleteItems", "deathskillsreset",
    "fire", "worldlevellockedtools",
)

NUMERIC_KEYS: tuple[str, ...] = (
    "EnemyDamage", "PlayerDamage", "EventRate", "EnemyLevelUpRate",
    "EnemySpeedSize", "SkillGainRate", "SkillReductionRate", "StaminaRate",
    "StaminaRegenRate", "MoveStaminaRate", "AdrenalineRate", "WorldLevel",
)

NUMERIC_DEFAULT = 100
NUMERIC_MIN, NUMERIC_MAX = 0, 1000

# Setkeys are persisted INTO THE WORLD SAVE. These cannot be undone by simply
# turning the setting off again — the UI must say so before applying them.
IRREVERSIBLE_TOGGLES: frozenset[str] = frozenset({
    "allpiecesunlocked", "allrecipesunlocked",
    "deathdeleteItems", "deathdeleteunequipped", "deathskillsreset",
})

_MAX_BACKUPS = 10

# ─── Parsing ─────────────────────────────────────────────────────────────────

_ARRAY_RE_TMPL = r"^(?P<head>{name}=\()(?P<body>.*?)(?P<tail>^\))"


def _array_block(text: str, name: str) -> re.Match | None:
    return re.search(
        _ARRAY_RE_TMPL.format(name=re.escape(name)),
        text,
        re.DOTALL | re.MULTILINE,
    )


def _active_entries(body: str) -> list[str]:
    """Quoted entries in a bash array, ignoring commented-out lines."""
    out: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip any trailing inline comment before looking for the value.
        code = stripped.split("#", 1)[0]
        for m in re.finditer(r'"([^"]*)"', code):
            if m.group(1):
                out.append(m.group(1))
    return out


def _scalar(text: str, name: str, default: str = "") -> str:
    m = re.search(rf'^{re.escape(name)}=("?)(.*?)\1\s*$', text, re.MULTILINE)
    return m.group(2).strip() if m else default


def read_modifiers(path: Path) -> dict:
    """Parse modifiers.conf into a structured payload."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8")

    preset = _scalar(text, "PRESET")
    enable_modifiers = _scalar(text, "ENABLE_MODIFIERS", "true").lower() == "true"

    modifiers: dict[str, str] = {}
    m = _array_block(text, "MODIFIERS")
    if m:
        for entry in _active_entries(m.group("body")):
            cat, _, val = entry.partition("=")
            if cat in MODIFIER_OPTIONS:
                modifiers[cat] = val.lower()

    toggles: list[str] = []
    numeric: dict[str, int] = {}
    s = _array_block(text, "SETKEYS")
    if s:
        for entry in _active_entries(s.group("body")):
            key, sep, val = entry.partition("=")
            if sep:
                if key in NUMERIC_KEYS:
                    try:
                        numeric[key] = int(val)
                    except ValueError:
                        pass
            elif key in TOGGLE_KEYS:
                toggles.append(key)

    return {
        "preset": preset,
        "enable_modifiers": enable_modifiers,
        "modifiers": modifiers,
        "setkeys": {"toggles": toggles, "numeric": numeric},
        "config_file": str(path),
        # Everything here is a launch argument, so nothing takes effect until
        # the server process is restarted.
        "restart_required": True,
        "options": {
            "presets": list(PRESETS),
            "preset_baseline": PRESET_BASELINE,
            "modifiers": {k: list(v) for k, v in MODIFIER_OPTIONS.items()},
            "toggles": list(TOGGLE_KEYS),
            "numeric": list(NUMERIC_KEYS),
            "numeric_default": NUMERIC_DEFAULT,
            "numeric_range": [NUMERIC_MIN, NUMERIC_MAX],
            "irreversible_toggles": sorted(IRREVERSIBLE_TOGGLES),
        },
    }


# ─── Validation ──────────────────────────────────────────────────────────────

class ValidationError(ValueError):
    """Raised with an operator-readable message; surfaced as HTTP 422."""


def validate_changes(changes: dict) -> dict:
    """Validate a PATCH payload. Returns the normalised subset to apply."""
    out: dict = {}

    if "preset" in changes:
        preset = (changes["preset"] or "").strip().lower()
        if preset and preset not in PRESETS:
            raise ValidationError(
                f"Unknown preset {preset!r}. Valid: {', '.join(PRESETS)} (or empty for none)."
            )
        out["preset"] = preset

    if "modifiers" in changes:
        mods = changes["modifiers"] or {}
        if not isinstance(mods, dict):
            raise ValidationError("modifiers must be an object of category -> value.")
        clean: dict[str, str] = {}
        for cat, val in mods.items():
            if cat not in MODIFIER_OPTIONS:
                raise ValidationError(
                    f"Unknown modifier category {cat!r}. Valid: {', '.join(MODIFIER_OPTIONS)}."
                )
            if val in (None, ""):
                continue  # clearing an override back to the preset default
            v = str(val).strip().lower()
            if v not in MODIFIER_OPTIONS[cat]:
                raise ValidationError(
                    f"Invalid value {val!r} for {cat}. Valid: {', '.join(MODIFIER_OPTIONS[cat])}."
                )
            clean[cat] = v
        out["modifiers"] = clean

    if "setkeys" in changes:
        sk = changes["setkeys"] or {}
        if not isinstance(sk, dict):
            raise ValidationError("setkeys must be an object with 'toggles' and/or 'numeric'.")
        clean_sk: dict = {}

        if "toggles" in sk:
            toggles = sk["toggles"] or []
            if not isinstance(toggles, list):
                raise ValidationError("setkeys.toggles must be a list.")
            for t in toggles:
                if t not in TOGGLE_KEYS:
                    raise ValidationError(
                        f"Unknown setkey toggle {t!r}. Valid: {', '.join(TOGGLE_KEYS)}."
                    )
            clean_sk["toggles"] = sorted(set(toggles), key=TOGGLE_KEYS.index)

        if "numeric" in sk:
            nums = sk["numeric"] or {}
            if not isinstance(nums, dict):
                raise ValidationError("setkeys.numeric must be an object of key -> int.")
            clean_nums: dict[str, int] = {}
            for k, v in nums.items():
                if k not in NUMERIC_KEYS:
                    raise ValidationError(
                        f"Unknown numeric setkey {k!r}. Valid: {', '.join(NUMERIC_KEYS)}."
                    )
                try:
                    iv = int(v)
                except (TypeError, ValueError):
                    raise ValidationError(f"{k} must be an integer, got {v!r}.") from None
                if not (NUMERIC_MIN <= iv <= NUMERIC_MAX):
                    raise ValidationError(
                        f"{k}={iv} out of range {NUMERIC_MIN}-{NUMERIC_MAX} (100 = vanilla)."
                    )
                clean_nums[k] = iv
            clean_sk["numeric"] = clean_nums

        out["setkeys"] = clean_sk

    if not out:
        raise ValidationError("No recognised fields to change.")
    return out


# ─── Writing ─────────────────────────────────────────────────────────────────

def _render_modifiers_body(mods: dict[str, str]) -> str:
    if not mods:
        return "\n"
    lines = [f'    "{cat}={mods[cat]}"' for cat in MODIFIER_OPTIONS if cat in mods]
    return "\n" + "\n".join(lines) + "\n"


def _render_setkeys_body(toggles: list[str], numeric: dict[str, int]) -> str:
    lines: list[str] = []
    if toggles:
        lines.append("    # --- Toggles (written into the world save) ---")
        lines += [f'    "{t}"' for t in toggles]
    if numeric:
        if lines:
            lines.append("")
        lines.append("    # --- Numeric (100 = vanilla default) ---")
        lines += [f'    "{k}={numeric[k]}"' for k in NUMERIC_KEYS if k in numeric]
    if not lines:
        return "\n    # (none set)\n"
    return "\n" + "\n".join(lines) + "\n"


def _replace_array(text: str, name: str, body: str) -> str:
    m = _array_block(text, name)
    if not m:
        raise ValidationError(f"{name}=( ... ) block not found in modifiers.conf")
    return text[:m.start("body")] + body + text[m.end("body"):]


def _rotate_backups(path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak-{ts}"))
    backups = sorted(path.parent.glob(path.name + ".bak-*"))
    for old in backups[:-_MAX_BACKUPS]:
        old.unlink(missing_ok=True)


def write_modifiers(path: Path, changes: dict) -> dict:
    """Apply validated changes atomically, preserving the file's comments."""
    clean = validate_changes(changes)
    if not path.exists():
        raise FileNotFoundError(str(path))

    text = path.read_text(encoding="utf-8")
    current = read_modifiers(path)

    if "preset" in clean:
        new_preset = clean["preset"]
        if re.search(r"^PRESET=", text, re.MULTILINE):
            text = re.sub(r"^PRESET=.*$", f'PRESET="{new_preset}"', text, count=1, flags=re.MULTILINE)
        else:
            text = f'PRESET="{new_preset}"\n' + text

    if "modifiers" in clean:
        mods = clean["modifiers"]
        text = _replace_array(text, "MODIFIERS", _render_modifiers_body(mods))
        # An empty override set would otherwise leave ENABLE_MODIFIERS=true with
        # nothing to apply, which reads as a bug to the next person.
        enable = "true" if mods else "false"
        text = re.sub(r"^ENABLE_MODIFIERS=.*$", f"ENABLE_MODIFIERS={enable}",
                      text, count=1, flags=re.MULTILINE)

    if "setkeys" in clean:
        sk = clean["setkeys"]
        toggles = sk.get("toggles", current["setkeys"]["toggles"])
        numeric = sk.get("numeric", current["setkeys"]["numeric"])
        text = _replace_array(text, "SETKEYS", _render_setkeys_body(toggles, numeric))

    _rotate_backups(path)

    # Atomic replace: write a temp file in the same directory, fsync, rename.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".modifiers.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    applied = read_modifiers(path)
    warnings = [
        f"{t} is written into the world save and cannot be undone by turning it off"
        for t in applied["setkeys"]["toggles"] if t in IRREVERSIBLE_TOGGLES
    ]
    return {"applied": applied, "restart_required": True, "warnings": warnings}
