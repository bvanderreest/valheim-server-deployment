# Valheim Server Modifier System

This document describes how gameplay modifiers are configured for the Valheim dedicated server.

---

## How It Works

Modifiers are built by `build_args()` in `helpers.sh` and passed to the server binary at launch. The process is:

1. `set_modifier_group` sets `ENABLE_*` flags based on `DEFAULT_MODIFIER_GROUP`
2. `modifiers.conf` is sourced — any explicit `ENABLE_*` lines in your file override the group defaults
3. Enabled modifier arrays are iterated and emitted as `-modifier <category> <value>` flags
4. `SETKEYS` entries are emitted as `-setkey <key>` flags
5. `PRESET` is emitted as `-preset <value>` if set

---

## Configuration File

**`modifiers.conf`** is your live config. It is created automatically from `modifiers.example.conf` on first run and is never overwritten by updates.

---

## Customisation Levels (`DEFAULT_MODIFIER_GROUP`)

Set this once at the top of `modifiers.conf` to control which tiers are active:

| Value | Active tiers |
|-------|-------------|
| `preset` | Preset only — no `-modifier` flags |
| `basic` | `BASIC_MODIFIERS` only |
| `standard` | `BASIC_MODIFIERS` (default) |
| `hardcore` | `BASIC_MODIFIERS` + `ADVANCED_MODIFIERS` + `EXPERT_MODIFIERS` |
| `custom` | `CUSTOM_MODIFIERS` only |

You can also override individual `ENABLE_*` flags directly in `modifiers.conf` — they take precedence over the group:

```bash
DEFAULT_MODIFIER_GROUP="standard"
ENABLE_EXPERT_MODIFIERS=true   # overrides the group — expert modifiers will also fire
```

---

## Preset Difficulty (`PRESET`)

Passed as `-preset <value>`. Sets a named difficulty baseline before any `-modifier` flags are applied.

Valid values (case-insensitive):

| Value | Description |
|-------|-------------|
| `casual` | Very easy — minimal challenge |
| `easy` | Reduced difficulty |
| `normal` | Default Valheim experience |
| `hard` | Increased challenge |
| `hardcore` | Permadeath-style penalties |
| `immersive` | No map, increased realism |
| `hammer` | Creative mode — no resource costs |

Set `PRESET=""` to skip the preset entirely.

---

## Basic Modifiers (`BASIC_MODIFIERS`)

These are the **5 official vanilla `-modifier` categories**. Each entry becomes `-modifier <category> <value>`.

> **These are the only modifier categories supported by the vanilla dedicated server.**

### Valid categories and values

| Category | Valid values |
|----------|-------------|
| `Combat` | `veryeasy` `easy` `hard` `veryhard` |
| `DeathPenalty` | `casual` `veryeasy` `easy` `hard` `hardcore` |
| `Resources` | `muchless` `less` `more` `muchmore` `most` |
| `Raids` | `none` `muchless` `less` `more` `muchmore` |
| `Portals` | `casual` `hard` `veryhard` |

### Example

```bash
BASIC_MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)
```

---

## Advanced & Expert Modifiers

`ADVANCED_MODIFIERS` and `EXPERT_MODIFIERS` follow the same `"Category=value"` format as basic modifiers, but are **not used by the vanilla server**. They are reserved for modded servers (e.g. ValheimPlus, Jotunn-based mods) that register additional `-modifier` categories.

Leave these arrays empty if you are running a vanilla server.

---

## Custom Modifiers (`CUSTOM_MODIFIERS`)

Active when `DEFAULT_MODIFIER_GROUP="custom"`. Replaces all other tiers — you define the full modifier list yourself. Same format as basic modifiers.

```bash
CUSTOM_MODIFIERS=(
    "Combat=hard"
    "Resources=less"
)
```

---

## Setkeys (`SETKEYS`)

Passed as `-setkey <key>`. These are boolean world flags — drastic changes that are all **commented out by default**. Only enable what you intentionally want.

| Key | Effect |
|-----|--------|
| `nomap` | Removes the shared map from all players |
| `nobuildcost` | Building requires no materials |
| `nopassivemobs` | Disables passive creatures (deer, birds, fish, etc.) |
| `noevent` | Disables random world events (raids, etc.) |
| `noenemy` | Disables all enemy spawning |
| `noitem` | Disables item drops from enemies |
| `noportal` | Disables all portal use |
| `noenemydrops` | Disables loot drops from enemies |

### Example (enabling just nomap)

```bash
SETKEYS=(
    "nomap"
    # "noportal"
)
```

---

## Tier Control Flags

These are set automatically by `DEFAULT_MODIFIER_GROUP`, but can be overridden manually in `modifiers.conf`:

```bash
ENABLE_BASIC_MODIFIERS=true
ENABLE_ADVANCED_MODIFIERS=false
ENABLE_EXPERT_MODIFIERS=false
ENABLE_CUSTOM_MODIFIERS=false
```

Explicit values in `modifiers.conf` always take precedence over the group default.

---

## References

- [Valheim World Modifiers Wiki](https://valheim.fandom.com/wiki/World_Modifiers)
- [Valheim Global Keys Wiki](https://valheim.fandom.com/wiki/Global_Keys)
- [Valheim Dedicated Server Guide](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
