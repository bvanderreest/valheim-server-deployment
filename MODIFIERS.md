# Enhanced Valheim Server Modifiers System

This document explains the enhanced modifier system implemented in the Valheim server manager. The system provides a tiered approach to configuring world modifiers, allowing server administrators to choose from basic, advanced, and expert options.

## Improved UI/UX Structure

The configuration has been restructured to provide a better user experience:
1. **First, select your customization level** - Choose from preset, standard, hardcore, or custom
2. **Then configure specific settings** - Modify presets, modifiers, and setkeys as needed

This upfront selection makes it easier to understand what configuration options are available before diving into details.

## Overview

The enhanced modifier system separates modifiers into three tiers:
1. **Basic Modifiers** - Core gameplay settings that most server admins want to control
2. **Advanced Modifiers** - More granular control over gameplay mechanics
3. **Expert Modifiers** - Maximum customization options for experienced admins

## Configuration File Structure

The `modifiers.conf` file has been split into two files for better version control:

1. **modifiers-base.conf** - Contains base modifier definitions that should be updated with new releases
2. **modifiers-user.conf** - Contains user-specific settings that should NOT be updated with new releases

The `modifiers-base.conf` file contains all modifier settings organized by tier:

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

## Improved Configuration Structure

The `modifiers.conf` file has been restructured for better usability:

### 1. Customization Level Selection
```bash
# Select your desired level of customization upfront
# This determines which modifier tiers will be active
# Options: "preset", "standard", "hardcore", "custom"
DEFAULT_MODIFIER_GROUP="standard"
```

### 2. Functional Implementation
The `DEFAULT_MODIFIER_GROUP` setting is now fully functional and automatically configures the appropriate modifier tiers:
- **preset**: Only uses the preset configuration without additional modifiers
- **standard**: Enables basic and advanced modifiers for balanced gameplay
- **hardcore**: Enables all modifier tiers for maximum challenge
- **basic**: Enables only basic modifiers (overwrites presets)
- **custom**: Enables custom modifiers only

### 2. Preset Difficulty
```bash
# Choose a preset base (case-insensitive): casual | easy | normal | hard | hardcore | immersive | hammer
# Presets provide a quick way to set multiple modifiers at once
PRESET="normal"
```

### 3. Boolean Setkeys
```bash
# Boolean setkeys that act as toggles for various features
# These are used with the -setkey flag and are typically simple on/off switches
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

### 4. Modifier Tiers (Automatically Configured)
The following modifier tiers are defined but automatically controlled by the DEFAULT_MODIFIER_GROUP setting:

#### Basic Modifiers
```bash
BASIC_MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)
```

#### Advanced Modifiers
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

#### Expert Modifiers
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

### 5. Custom Modifiers
```bash
CUSTOM_MODIFIERS=(
    # Example custom modifiers - uncomment and modify as needed
    # "CustomEnemyDamage=150"
    # "CustomResourceRate=120"
    # "CustomStaminaRegenRate=80"
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

### Basic Configuration
```bash
# Enable only basic modifiers (overwrites presets)
DEFAULT_MODIFIER_GROUP="basic"
PRESET="normal"  # This will be overwritten by basic level
MODIFIERS=( "Combat=hard" "Resources=more" )
SETKEYS=( "nomap" "nobuildcost" )
```

### Standard Configuration
```bash
# Enable basic and advanced modifiers
DEFAULT_MODIFIER_GROUP="standard"
PRESET="normal"
MODIFIERS=( "Combat=hard" "Resources=more" "EnemyLevelUpRate=120" )
SETKEYS=( "nomap" "nobuildcost" )
```

### Hardcore Configuration
```bash
# Enable all modifier tiers for maximum challenge
DEFAULT_MODIFIER_GROUP="hardcore"
PRESET="hardcore"
MODIFIERS=( "Combat=hard" "Resources=more" "EnemyLevelUpRate=120" "EnemySpeedSize=150" )
SETKEYS=( "nomap" "nobuildcost" "noenemy" )
```

### Custom Configuration
```bash
# Use custom modifiers only
DEFAULT_MODIFIER_GROUP="custom"
PRESET="normal"
MODIFIERS=( "CustomEnemyDamage=150" "CustomResourceRate=120" )
SETKEYS=( "nomap" "nobuildcost" )
```

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

### Preset Configuration
```bash
# Enable only the preset without additional modifiers
ENABLE_BASIC_MODIFIERS=false
ENABLE_ADVANCED_MODIFIERS=false
ENABLE_EXPERT_MODIFIERS=false
ENABLE_CUSTOM_MODIFIERS=false
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

## Modifier Groups

The system supports the following modifier groups for easy configuration:

- **basic**: Basic modifiers only (overwrites presets)
- **standard**: Basic + Advanced modifiers
- **hardcore**: Basic + Advanced + Expert modifiers
- **custom**: Custom modifiers only
- **preset**: Pure preset only (no additional modifiers)

## Customization Levels

The new configuration structure allows you to select your desired level of customization upfront:

1. **basic** - Basic modifiers only (overwrites presets)
2. **preset** - Only the base preset configuration, no additional modifiers
3. **standard** - Basic + Advanced modifiers for balanced gameplay
4. **hardcore** - Basic + Advanced + Expert modifiers for maximum challenge
5. **custom** - Custom modifiers only, allowing for unique server experiences

This upfront selection makes it easier to understand what configuration options are available before diving into specific settings.

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
6. **Use Pure Preset**: For a clean preset-only configuration, set `DEFAULT_MODIFIER_GROUP="preset"`

## Using the "Preset" Modifier Group

The "preset" modifier group allows you to use only the preset configuration without any additional modifiers (basic, advanced, or expert). To use this option:

1. Set `DEFAULT_MODIFIER_GROUP="preset"` in `modifiers.conf`

## Improved Configuration Structure

The configuration has been restructured to provide a better user experience:
1. **First, select your customization level** - Choose from preset, standard, hardcore, or custom
2. **Then configure specific settings** - Modify presets, modifiers, and setkeys as needed

This upfront selection makes it easier to understand what configuration options are available before diving into details.

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