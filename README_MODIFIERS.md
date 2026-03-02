# Valheim Server Modifiers - Complete Guide

## Overview

This document provides a comprehensive guide to all Valheim server modifiers and their effects on gameplay. Understanding these modifiers is crucial for creating the perfect server experience for your community.

## Preset Modifiers

Preset modifiers provide a quick way to set a baseline difficulty level for your server. When a preset is used, it sets default values for all category modifiers, which can then be overridden by individual modifiers.

### Available Presets

- **Normal**: Standard gameplay experience
- **Casual**: Balanced experience with moderate difficulty
- **Easy**: Reduced difficulty for new players
- **Hard**: Challenging gameplay with increased difficulty
- **Hardcore**: Most difficult setting with severe consequences
- **Immersive**: Enhanced immersion with unique gameplay elements
- **Hammer**: Similar to Casual but with no building costs

## Category Modifiers

Category modifiers allow fine-tuning of specific gameplay elements. These can override the default values set by presets.

### Combat

Controls the difficulty of combat encounters with enemies.

- **veryeasy**: Minimal combat challenge - enemies are very weak
- **easy**: Reduced combat difficulty - enemies are weak
- **hard**: Increased combat challenge - enemies are strong
- **veryhard**: Maximum combat challenge - enemies are extremely powerful

### Death Penalty

Determines the consequences of player death.

- **casual**: Standard death penalty - players lose some items and skills
- **veryeasy**: Minimal penalty - players lose few items and skills
- **easy**: Reduced penalty - players lose some items and skills
- **hard**: Increased penalty - players lose more items and skills
- **hardcore**: Severe penalty - players lose all items and skills

### Resources

Controls the amount of resources available in the world.

- **muchless**: Significantly reduced resources - very scarce materials
- **less**: Reduced resources - scarce materials
- **more**: Increased resources - abundant materials
- **muchmore**: Significantly increased resources - extremely abundant materials
- **most**: Maximum resources - unlimited materials

### Raids

Controls the frequency and occurrence of enemy raids on player bases.

- **none**: No enemy raids - bases are completely safe
- **muchless**: Very few raids - rare base attacks
- **less**: Few raids - occasional base attacks
- **more**: More raids - frequent base attacks
- **muchmore**: Very frequent raids - constant base attacks

### Portals

Controls the restrictions on using portals.

- **casual**: Standard portal restrictions - normal portal usage
- **hard**: Increased portal restrictions - limited portal usage
- **veryhard**: Maximum portal restrictions - very limited portal usage

## Boolean Feature Toggles

Boolean toggles enable or disable specific gameplay features.

### nobuildcost

- **Effect**: Removes building material costs
- **Impact**: Players can build without consuming resources
- **Use Case**: Creative mode, building-focused gameplay

### passivemobs

- **Effect**: Allows mobs to spawn in peace mode
- **Impact**: Mobs can spawn even when no players are nearby
- **Use Case**: Peaceful gameplay, reduced combat

### playerevents

- **Effect**: Enables player-triggered events
- **Impact**: Random events can occur based on player actions
- **Use Case**: Enhanced gameplay variety

### nomap

- **Effect**: Players don't see the full map
- **Impact**: Players can only see their immediate surroundings
- **Use Case**: Increased challenge, exploration focus

## Command Line Usage

### Basic Syntax

```
./valheim_server.sh -preset [preset_value] -modifier [modifier_name] [modifier_value] -setkey [toggle_value]
```

### Examples

#### Balanced Standard Experience
```
./valheim_server.sh -preset normal -modifier combat hard -modifier deathpenalty hard -modifier resources more -modifier raids less -modifier portals hard -setkey nobuildcost -setkey playerevents
```

#### Challenging Hardcore Experience
```
./valheim_server.sh -preset hardcore -modifier combat veryhard -modifier deathpenalty hardcore -modifier resources muchless -modifier raids muchmore -modifier portals veryhard -setkey passivemobs
```

#### Casual Building-Focused Experience
```
./valheim_server.sh -preset casual -modifier combat veryeasy -modifier deathpenalty casual -modifier resources most -modifier raids none -modifier portals casual -setkey nobuildcost -setkey nomap
```

## Best Practices

1. **Preset First**: Always specify presets before individual modifiers in command line arguments
2. **Consistency**: Ensure modifier values are consistent with the intended gameplay experience
3. **Testing**: Test configurations with a small group before deploying to a larger community
4. **Documentation**: Keep detailed records of your server configurations for future reference
5. **Backup**: Maintain backups of working configurations before making changes
6. **Iteration**: Start with a baseline configuration and gradually adjust modifiers to find the perfect balance

## Troubleshooting

If modifiers aren't applying correctly:

1. **Verify Preset Order**: Ensure presets are specified before individual modifiers
2. **Check Spelling**: Confirm all modifier values are spelled correctly
3. **Validate Values**: Ensure all values are valid for their respective categories
4. **Restart Server**: Confirm the server is restarted after configuration changes
5. **Check Logs**: Review server logs for any error messages related to modifiers

## Custom Configuration Examples

### Adventure-Focused Server
```
PRESET="hard"
MODIFIERS=(
  "Combat=hard"
  "DeathPenalty=hard"
  "Resources=less"
  "Raids=more"
  "Portals=hard"
)
SETKEYS=(
  "passivemobs"
)
```

### Creative Building Server
```
PRESET="casual"
MODIFIERS=(
  "Combat=veryeasy"
  "DeathPenalty=casual"
  "Resources=most"
  "Raids=none"
  "Portals=casual"
)
SETKEYS=(
  "nobuildcost"
  "nomap"
)
```

### Competitive PvP Server
```
PRESET="normal"
MODIFIERS=(
  "Combat=veryhard"
  "DeathPenalty=hardcore"
  "Resources=less"
  "Raids=none"
  "Portals=veryhard"
)
SETKEYS=(
  "playerevents"
)
```

This comprehensive guide should help you create the perfect Valheim server experience tailored to your community's preferences.