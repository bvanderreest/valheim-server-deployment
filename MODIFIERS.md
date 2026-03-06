# Valheim Server — Modifier Reference

Modifiers let you tune the gameplay experience without touching the server binary. This document covers every option available in `modifiers.conf` and how they combine at launch.

---

## How It Works

When the server starts, `build_args()` in `helpers.sh` assembles the launch arguments in this order:

1. **Group selection** — `DEFAULT_MODIFIER_GROUP` sets which modifier tiers are active
2. **Override resolution** — any explicit `ENABLE_*` flags in your `modifiers.conf` take precedence over the group
3. **Preset** — emitted as `-preset <value>` (sets a named difficulty baseline)
4. **Modifiers** — each enabled array entry becomes `-modifier <category> <value>`
5. **Setkeys** — each entry becomes `-setkey <key>` (boolean world flags)

---

## Quick Setup

`modifiers.conf` is created automatically from `modifiers.example.conf` on first run. It is never overwritten by updates, so your changes are safe.

For most servers, you only need to set two things:

```bash
DEFAULT_MODIFIER_GROUP="standard"
PRESET="normal"
```

Then adjust `BASIC_MODIFIERS` to taste.

---

## Modifier Groups (`DEFAULT_MODIFIER_GROUP`)

This single setting controls which tiers of modifiers are sent to the server.

| Value | What gets applied |
|-------|-------------------|
| `preset` | Preset only — no `-modifier` flags at all |
| `basic` | `BASIC_MODIFIERS` only |
| `standard` | `BASIC_MODIFIERS` (same as `basic` — the default) |
| `hardcore` | `BASIC_MODIFIERS` + `ADVANCED_MODIFIERS` + `EXPERT_MODIFIERS` |
| `custom` | `CUSTOM_MODIFIERS` only — you define the full list yourself |

You can also override individual tiers without changing the group:

```bash
DEFAULT_MODIFIER_GROUP="standard"
ENABLE_EXPERT_MODIFIERS=true   # add expert modifiers on top of the standard set
```

---

## Preset Difficulty (`PRESET`)

Sets a named difficulty baseline before any `-modifier` flags are applied. Think of it as the starting point that your modifiers then adjust.

| Value | Experience |
|-------|-----------|
| `casual` | Very easy — minimal challenge, forgiving death |
| `easy` | Reduced difficulty across the board |
| `normal` | Default Valheim — balanced challenge |
| `hard` | Increased enemy difficulty and fewer resources |
| `hardcore` | Permadeath-style penalties |
| `immersive` | No shared map, increased realism |
| `hammer` | Creative mode — no resource costs for building |

Set `PRESET=""` to skip the preset entirely and rely solely on modifiers.

---

## Basic Modifiers (`BASIC_MODIFIERS`)

The five official vanilla modifier categories. Each entry is passed to the server as `-modifier <Category> <value>`.

> These are the only modifier categories supported by the vanilla dedicated server.
> If you are running a modded server (ValheimPlus, Jotunn mods), see Advanced & Expert below.

### Categories and valid values

| Category | Values | Effect |
|----------|--------|--------|
| `Combat` | `veryeasy` `easy` _(default)_ `hard` `veryhard` | Enemy damage and aggression |
| `DeathPenalty` | `casual` `veryeasy` `easy` _(default)_ `hard` `hardcore` | What you lose on death |
| `Resources` | `muchless` `less` _(default)_ `more` `muchmore` `most` | Crafting/building material yield |
| `Raids` | `none` `muchless` `less` _(default)_ `more` `muchmore` | Frequency of enemy raids on your base |
| `Portals` | `casual` _(default)_ `hard` `veryhard` | Portal restrictions (item carry rules) |

### Example — relaxed community server

```bash
BASIC_MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)
```

### Example — challenging survival server

```bash
BASIC_MODIFIERS=(
    "Combat=hard"
    "DeathPenalty=hard"
    "Resources=less"
    "Raids=more"
    "Portals=hard"
)
```

---

## Advanced & Expert Modifiers

`ADVANCED_MODIFIERS` and `EXPERT_MODIFIERS` use the same `"Category=value"` format as basic modifiers but are intended for **modded servers** that register additional `-modifier` categories (e.g. ValheimPlus, Jotunn-based mods).

**Leave these arrays empty on a vanilla server** — unrecognised categories are ignored by the base game but may produce log warnings.

```bash
ADVANCED_MODIFIERS=()
EXPERT_MODIFIERS=()
```

These tiers are only active when `DEFAULT_MODIFIER_GROUP="hardcore"` or when you explicitly set `ENABLE_ADVANCED_MODIFIERS=true` in your config.

---

## Custom Modifiers (`CUSTOM_MODIFIERS`)

Active when `DEFAULT_MODIFIER_GROUP="custom"`. Replaces all other tiers — you define the complete modifier list from scratch. Useful when you want precise control with no inherited defaults.

```bash
DEFAULT_MODIFIER_GROUP="custom"

CUSTOM_MODIFIERS=(
    "Combat=hard"
    "DeathPenalty=casual"
    "Resources=less"
    "Raids=none"
    "Portals=veryhard"
)
```

---

## Setkeys (`SETKEYS`)

Boolean world flags passed as `-setkey <key>`. These are **drastic, world-altering changes** and are all commented out by default. Only enable what you intentionally want — some cannot be undone without editing the world save.

| Key | Effect |
|-----|--------|
| `nomap` | Removes the shared map — every player navigates without a minimap |
| `nobuildcost` | Building and crafting costs no materials |
| `nopassivemobs` | Disables passive creatures (deer, birds, fish) |
| `noevent` | Disables random world events and raids |
| `noenemy` | Disables all enemy spawning |
| `noitem` | Enemies drop no items |
| `noportal` | Disables all portal use — no fast travel |
| `noenemydrops` | Enemies drop no loot (separate from `noitem`) |

### Example — hardcore immersion run

```bash
SETKEYS=(
    "nomap"
    "noportal"
)
```

### Example — peaceful building server

```bash
SETKEYS=(
    "noevent"
    "noenemy"
    "nobuildcost"
)
```

---

## Tier Control Flags

These are set automatically by `DEFAULT_MODIFIER_GROUP` but can be overridden directly in `modifiers.conf`. Explicit values always win.

```bash
ENABLE_BASIC_MODIFIERS=true
ENABLE_ADVANCED_MODIFIERS=false
ENABLE_EXPERT_MODIFIERS=false
ENABLE_CUSTOM_MODIFIERS=false
```

---

## Common Configurations

### Casual / family-friendly

```bash
DEFAULT_MODIFIER_GROUP="standard"
PRESET="easy"
BASIC_MODIFIERS=(
    "Combat=veryeasy"
    "DeathPenalty=casual"
    "Resources=more"
    "Raids=none"
    "Portals=casual"
)
```

### Vanilla experience (no modifiers)

```bash
DEFAULT_MODIFIER_GROUP="preset"
PRESET="normal"
```

### Hardcore survival

```bash
DEFAULT_MODIFIER_GROUP="standard"
PRESET="hard"
BASIC_MODIFIERS=(
    "Combat=veryhard"
    "DeathPenalty=hardcore"
    "Resources=muchless"
    "Raids=more"
    "Portals=veryhard"
)
SETKEYS=(
    "nomap"
)
```

---

## References

- [Valheim World Modifiers — Wiki](https://valheim.fandom.com/wiki/World_Modifiers)
- [Valheim Global Keys — Wiki](https://valheim.fandom.com/wiki/Global_Keys)
- [Official Dedicated Server Guide](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
