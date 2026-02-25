# Valheim Server Modifier Configuration System - Refactoring Plan

## Current Issues

The current modifier configuration system in `modifiers.conf` has several problems that lead to Git conflicts when pulling new releases:

1. **Mixed Base and User Configuration**: The same file contains both base system settings and user-specific customizations
2. **Version Control Conflicts**: When new releases update `modifiers.conf`, user customizations cause merge conflicts
3. **No Clear Separation**: Users are expected to modify the base file directly, which is not sustainable

## Proposed Solution

### 1. File Structure Changes

Create a new layered configuration approach:

#### Base Configuration File (`modifiers-base.conf`)
- Contains all base modifier definitions that should be updated with new releases
- Includes: BASIC_MODIFIERS, ADVANCED_MODIFIERS, EXPERT_MODIFIERS, CUSTOM_MODIFIERS, SETKEYS, and default settings
- This file will be updated with new releases and should be included in version control

#### User Configuration File (`modifiers-user.conf`)
- Contains only user-specific settings that should NOT be updated with new releases
- Includes: DEFAULT_MODIFIER_GROUP, PRESET, and any customizations
- This file will NOT be included in version control (added to .gitignore)

### 2. Implementation Approach

#### Step 1: Create `modifiers-base.conf`
- Extract all base modifier definitions from current `modifiers.conf`
- Keep the same structure but separate from user configurations

#### Step 2: Modify `helpers.sh` 
- Update the sourcing logic to load both base and user configuration files
- Implement proper merging of configurations where user settings override base settings
- Maintain backward compatibility

#### Step 3: Update Documentation
- Update README.md to explain the new configuration approach
- Document how users should create and use `modifiers-user.conf`
- Provide examples of typical user configurations

### 3. Migration Strategy

1. **For existing users**: Create a migration script or guide to help users transition
2. **Backward compatibility**: Ensure the system works with existing `modifiers.conf` files
3. **Gradual adoption**: Users can gradually move to the new system

### 4. Benefits

- **No more Git conflicts**: Base system updates won't interfere with user customizations
- **Cleaner version control**: Only user-specific configurations are committed
- **Easier maintenance**: System updates can be pulled without conflicts
- **Better user experience**: Clear separation of concerns

## Technical Implementation Details

### In `helpers.sh`:
1. Source `modifiers-base.conf` first (always required)
2. Source `modifiers-user.conf` second (optional, will be created by user)
3. Merge configurations with user settings taking precedence
4. Maintain all existing functionality

### In `config.conf`:
1. Update the sourcing to include the new base file
2. Keep the same interface for the rest of the system

## Example User Configuration (`modifiers-user.conf`)

```bash
# User-specific modifier settings
DEFAULT_MODIFIER_GROUP="standard"
PRESET="normal"

# Example customizations
# You can override any base setting here
# ENABLE_BASIC_MODIFIERS=true
# ENABLE_ADVANCED_MODIFIERS=true
# ENABLE_EXPERT_MODIFIERS=false
# ENABLE_CUSTOM_MODIFIERS=false
```

## Migration Process

1. Users should create `modifiers-user.conf` with their current settings
2. Update `config.conf` to source both files
3. Test that everything works as expected
4. Remove old `modifiers.conf` from version control (if desired)
5. Add `modifiers-user.conf` to `.gitignore` (if not already there)