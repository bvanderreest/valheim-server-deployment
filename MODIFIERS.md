# Valheim Server — Modifier Reference

Modifiers let you tune the gameplay experience without touching the server binary. This document covers every option available in `modifiers.conf` and how they combine at launch.

---

## How It Works

When the server starts, `build_args()` in `helpers.sh` assembles the launch arguments in this order:

1. **Preset** — emitted as `-preset <value>` (sets a named difficulty baseline)
2. **Modifiers** — each enabled array entry becomes `-modifier <category> <value>`, overriding only the listed categories
3. **Extra modifiers** — same as above, applied only when `ENABLE_EXTRA_MODIFIERS=true`
4. **Setkeys** — toggle and numeric world flags emitted as `-setkey <key>` or `-setkey <key> <value>`

---

## Quick Setup

`modifiers.conf` is created automatically from `modifiers.example.conf` on first run and is never overwritten by updates.

For most servers, `cp modifiers.example.conf modifiers.conf` is all that is needed. The defaults give a playable, slightly relaxed community server on top of the `normal` preset. Adjust `MODIFIERS` entries to taste.

---

## Preset Difficulty (`PRESET`)

Sets a named difficulty baseline. Individual `-modifier` flags applied after the preset override only the specific categories listed.

| Value | Combat | Death Penalty | Resources | Raids | Portals | Notes |
|-------|--------|---------------|-----------|-------|---------|-------|
| `casual` | veryeasy | casual | muchmore | none | casual | Minimal challenge |
| `easy` | easy | easy | more | less | — | Slightly relaxed |
| `normal` | — | — | — | — | — | Default Valheim |
| `hard` | hard | hard | less | more | hard | Tougher all-round |
| `hardcore` | veryhard | hardcore | less | more | veryhard | Permadeath |
| `immersive` | hard | hard | less | more | veryhard | No map, no portals |
| `hammer` | — | casual | muchmore | none | casual | Free build, creative |

Set `PRESET=""` to skip the preset entirely and define all modifier values yourself.

---

## Modifiers (`MODIFIERS`)

The 5 official vanilla `-modifier` categories. Active when `ENABLE_MODIFIERS=true`.

| Category | Valid Values |
|----------|-------------|
| `Combat` | `veryeasy` `easy` `hard` `veryhard` |
| `DeathPenalty` | `casual` `veryeasy` `easy` `hard` `hardcore` |
| `Resources` | `muchless` `less` `more` `muchmore` `most` |
| `Raids` | `none` `muchless` `less` `more` `muchmore` |
| `Portals` | `casual` `hard` `veryhard` |

`Portals=casual` allows all items including ores through portals. `Portals=hard` disables boss portals. `Portals=veryhard` disables all portals.

---

## Setkeys (`SETKEYS`)

World state flags and numeric tuning knobs. Written into the world save — some changes cannot be reversed without editing the world file directly.

### Toggle Keys

Uncomment the entry to enable — presence of the key activates the feature.

| Key | Effect |
|-----|--------|
| `nomap` | Removes the shared map for all players |
| `nobuildcost` | Building structures costs no materials |
| `nocraftcost` | Crafting items costs no materials |
| `noworkbench` | Craft and build anywhere without a workbench |
| `allpiecesunlocked` | All build pieces available from the start |
| `allrecipesunlocked` | All crafting recipes available from the start |
| `dungeonbuild` | Allow building inside dungeons (crypts, tombs, etc.) |
| `noportals` | Disable all portals entirely |
| `nobossportals` | Portals disabled while a boss event is active |
| `teleportall` | Block new portal construction; existing portals remain usable |
| `passivemobs` | All creatures passive unless provoked |
| `playerevents` | Raids triggered by player proximity, not on a global timer |
| `deathkeepequip` | Keep equipped items on death |
| `deathdeleteunequipped` | Delete only unequipped items on death |
| `deathdeleteItems` | Delete all items on death |
| `deathskillsreset` | Reset all skills to 0 on death |
| `fire` | Fire spreads and burns structures world-wide |
| `worldlevellockedtools` | Tool tier access gated by world progression level |

### Numeric Keys

Format: `"Key=value"` — becomes `-setkey Key value`. Vanilla default is always `100`.

| Key | Default | Effect |
|-----|---------|--------|
| `EnemyDamage` | 100 | Damage enemies deal to players (`200` = double, `50` = half) |
| `PlayerDamage` | 100 | Inversely scales creature HP (`200` = half HP / hits harder, `50` = double HP) |
| `EventRate` | 100 | Raid frequency (`0` = off, `200` = double rate) |
| `EnemyLevelUpRate` | 100 | Chance of starred enemies spawning |
| `EnemySpeedSize` | 100 | Enemy movement speed and physical size |
| `SkillGainRate` | 100 | Skill XP gain speed (`200` = double, `0` = frozen) |
| `SkillReductionRate` | 100 | Skill loss on death (`0` = no loss, `200` = double loss) |
| `StaminaRate` | 100 | Stamina consumption rate (`0` = unlimited) |
| `StaminaRegenRate` | 100 | Stamina regeneration speed |
| `MoveStaminaRate` | 100 | Stamina drain from movement specifically |
| `AdrenalineRate` | 100 | Adrenaline buildup rate |
| `WorldLevel` | 100 | World difficulty scaling level |

---

## Extra Modifiers (`EXTRA_MODIFIERS`)

Active when `ENABLE_EXTRA_MODIFIERS=true`. Applied in addition to `MODIFIERS`.

Intended for modded servers (ValheimPlus, Jotunn-based mods) that register additional `-modifier` categories beyond the vanilla 5, or for power users who want a secondary override layer kept separate from the main list.

Unrecognised categories are silently ignored by the base game but may produce warnings in the server log. Not needed for vanilla servers.

---

## Common Configurations

### Casual / community server

```bash
PRESET="easy"
ENABLE_MODIFIERS=true
MODIFIERS=(
    "Combat=veryeasy"
    "DeathPenalty=casual"
    "Resources=more"
    "Raids=none"
    "Portals=casual"
)
```

### Vanilla experience

```bash
PRESET="normal"
ENABLE_MODIFIERS=false
```

### Hardcore survival

```bash
PRESET="hard"
ENABLE_MODIFIERS=true
MODIFIERS=(
    "Combat=veryhard"
    "DeathPenalty=hardcore"
    "Resources=muchless"
    "Raids=more"
    "Portals=veryhard"
)
SETKEYS=(
    "nomap"
    "SkillReductionRate=200"
)
```

### Immersive roleplay

```bash
PRESET="immersive"
ENABLE_MODIFIERS=true
MODIFIERS=(
    "Combat=hard"
    "Resources=less"
)
SETKEYS=(
    "passivemobs"
    "playerevents"
    "dungeonbuild"
)
```

### Free build / creative

```bash
PRESET="hammer"
ENABLE_MODIFIERS=false
SETKEYS=(
    "nobuildcost"
    "nocraftcost"
    "allpiecesunlocked"
    "allrecipesunlocked"
)
```

---

## References

- [Valheim World Modifiers — Wiki](https://valheim.fandom.com/wiki/World_Modifiers)
- [Valheim Global Keys — Wiki](https://valheim.fandom.com/wiki/Global_Keys)
- [Official Dedicated Server Guide](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
