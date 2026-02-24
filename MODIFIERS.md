# Enhanced Valheim Server Modifiers System

This document explains the enhanced modifier system implemented in the Valheim server manager. The system provides a tiered approach to configuring world modifiers, allowing server administrators to choose from basic, advanced, and expert options.

## Overview

The enhanced modifier system separates modifiers into three tiers:
1. **Basic Modifiers** - Core gameplay settings that most server admins want to control
2. **Advanced Modifiers** - More granular control over gameplay mechanics
3. **Expert Modifiers** - Maximum customization options for experienced admins

## Configuration File Structure

The `modifiers.conf` file contains all modifier settings organized by tier:

### Preset Difficulty
```bash
# Choose a preset base (case-insensitive)
PRESET="normal"
```

### Basic Modifiers
```bash
BASIC_MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)
```

### Advanced Modifiers
```bash
ADVANCED_MODIFIERS=(
    "EnemyLevelUpRate=100"
    "ResourceRate=100"
    "StaminaRegenRate=100"
    "PlayerDamage=100"
    "EnemyDamage=100"
    "PlayerHealth=100"
    "EnemyHealth=100"
    "DungeonBuild=0"
)
```

### Expert Modifiers
```bash
EXPERT_MODIFIERS=(
    "EnemySpeedSize=100"
    "WorldLevelLockedTools=0"
    "NoStaminaRegen=0"
    "NoFoodRegen=0"
    "NoToolDurability=0"
    "NoFireplaceFuel=0"
    "NoBuildingCost=0"
    "NoCraftingCost=0"
    "NoCookingCost=0"
    "NoFishingCost=0"
    "NoSmithingCost=0"
    "NoWoodcuttingCost=0"
    "NoMiningCost=0"
    "NoHuntingCost=0"
    "NoFarmingCost=0"
    "NoAlchemyCost=0"
    "NoConstructionCost=0"
    "NoRepairCost=0"
    "NoRepairTime=0"
    "NoCraftingTime=0"
    "NoCookingTime=0"
    "NoFishingTime=0"
    "NoSmithingTime=0"
    "NoWoodcuttingTime=0"
    "NoMiningTime=0"
    "NoHuntingTime=0"
    "NoFarmingTime=0"
    "NoAlchemyTime=0"
    "NoConstructionTime=0"
    "NoRepairTime=0"
)
```

### Boolean Setkeys
```bash
SETKEYS=(
    "nomap"
    "nobuildcost"
    "nopassivemobs"
    "noevent"
    "noenemy"
    "noitem"
    "noportal"
    "noenemydrops"
)
```

## Tier Control

Each modifier tier can be enabled or disabled using these variables:
```bash
ENABLE_BASIC_MODIFIERS=true
ENABLE_ADVANCED_MODIFIERS=false
ENABLE_EXPERT_MODIFIERS=false
ENABLE_CUSTOM_MODIFIERS=false
```

## Usage Examples

### Standard Configuration
```bash
# Enable basic and advanced modifiers only
ENABLE_BASIC_MODIFIERS=true
ENABLE_ADVANCED_MODIFIERS=true
ENABLE_EXPERT_MODIFIERS=false
ENABLE_CUSTOM_MODIFIERS=false
```

### Hardcore Configuration
```bash
# Enable all modifier tiers
ENABLE_BASIC_MODIFIERS=true
ENABLE_ADVANCED_MODIFIERS=true
ENABLE_EXPERT_MODIFIERS=true
ENABLE_CUSTOM_MODIFIERS=false
```

### Custom Configuration
```bash
# Enable only custom modifiers
ENABLE_BASIC_MODIFIERS=false
ENABLE_ADVANCED_MODIFIERS=false
ENABLE_EXPERT_MODIFIERS=false
ENABLE_CUSTOM_MODIFIERS=true
```

## Available Modifier Categories

### Basic Categories
- **Combat**: veryeasy, easy, hard, veryhard
- **DeathPenalty**: casual, veryeasy, easy, hard, hardcore
- **Resources**: muchless, less, more, muchmore, most
- **Raids**: none, muchless, less, more, muchmore
- **Portals**: casual, hard, veryhard

### Advanced Categories
- **EnemyLevelUpRate**: Percentage multiplier for enemy level ups
- **ResourceRate**: Percentage multiplier for resource drops
- **StaminaRegenRate**: Percentage multiplier for stamina regeneration
- **PlayerDamage**: Percentage multiplier for player damage
- **EnemyDamage**: Percentage multiplier for enemy damage
- **PlayerHealth**: Percentage multiplier for player health
- **EnemyHealth**: Percentage multiplier for enemy health
- **DungeonBuild**: Enable building in dungeons (0 or 1)

### Expert Categories
- **EnemySpeedSize**: Percentage multiplier for enemy speed and size
- **WorldLevelLockedTools**: Lock tools to world level (0 or 1)
- **NoStaminaRegen**: Disable stamina regeneration (0 or 1)
- **NoFoodRegen**: Disable food regeneration (0 or 1)
- **NoToolDurability**: Disable tool durability (0 or 1)
- **NoFireplaceFuel**: Disable fireplace fuel consumption (0 or 1)
- **NoBuildingCost**: Disable building costs (0 or 1)
- **NoCraftingCost**: Disable crafting costs (0 or 1)
- **NoCookingCost**: Disable cooking costs (0 or 1)
- **NoFishingCost**: Disable fishing costs (0 or 1)
- **NoSmithingCost**: Disable smithing costs (0 or 1)
- **NoWoodcuttingCost**: Disable woodcutting costs (0 or 1)
- **NoMiningCost**: Disable mining costs (0 or 1)
- **NoHuntingCost**: Disable hunting costs (0 or 1)
- **NoFarmingCost**: Disable farming costs (0 or 1)
- **NoAlchemyCost**: Disable alchemy costs (0 or 1)
- **NoConstructionCost**: Disable construction costs (0 or 1)
- **NoRepairCost**: Disable repair costs (0 or 1)
- **NoRepairTime**: Disable repair time (0 or 1)
- **NoCraftingTime**: Disable crafting time (0 or 1)
- **NoCookingTime**: Disable cooking time (0 or 1)
- **NoFishingTime**: Disable fishing time (0 or 1)
- **NoSmithingTime**: Disable smithing time (0 or 1)
- **NoWoodcuttingTime**: Disable woodcutting time (0 or 1)
- **NoMiningTime**: Disable mining time (0 or 1)
- **NoHuntingTime**: Disable hunting time (0 or 1)
- **NoFarmingTime**: Disable farming time (0 or 1)
- **NoAlchemyTime**: Disable alchemy time (0 or 1)
- **NoConstructionTime**: Disable construction time (0 or 1)
- **NoRepairTime**: Disable repair time (0 or 1)

## Setkey Options

Boolean setkeys that act as toggles for various features:
- **nomap**: Disable map display
- **nobuildcost**: Disable building costs
- **nopassivemobs**: Disable passive mobs
- **noevent**: Disable events
- **noenemy**: Disable enemies
- **noitem**: Disable items
- **noportal**: Disable portals
- **noenemydrops**: Disable enemy drops

## Best Practices

1. **Start Simple**: Begin with basic modifiers and add advanced options as needed
2. **Test Thoroughly**: Always test new modifier combinations in a development environment
3. **Document Changes**: Keep track of modifier combinations that work well for your community
4. **Consider Balance**: Be mindful of how modifier combinations affect gameplay balance
5. **Use Presets**: Leverage the preset system for quick baseline configurations

## Troubleshooting

### Common Issues
1. **Modifier Not Working**: Ensure the modifier tier is enabled in `ENABLE_*_MODIFIERS`
2. **Syntax Errors**: Check that all modifier values are properly formatted
3. **Conflicting Modifiers**: Some modifiers may conflict with each other

### Debugging
Use the in-game console with `setkey` commands to test individual modifiers:
```
setkey nomap
setkey nobuildcost
```

## References

- [Valheim World Modifiers Wiki](https://valheim.fandom.com/wiki/World_Modifiers)
- [Valheim Global Keys](https://valheim.fandom.com/wiki/Global_Keys)
- [Valheim Dedicated Server Manual](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)