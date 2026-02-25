# 🛡 Valheim Dedicated Server Manager

A resilient, production-ready Bash management script for running a **Valheim Dedicated Server** on Linux. This project provides clean lifecycle management, SteamCMD updates, automatic world backups, crash recovery, and configurable gameplay modifiers --- split across four modular files for clean separation of configuration, helpers, and commands. Perfect for homelab operators and server administrators looking for a robust, easy-to-use solution to host your own Valheim server!

## 🚀 Key Features

- **🎮 Game Modifiers**: Advanced modifier system with 5 customization levels (basic, preset, standard, hardcore, custom)
- **⚡ Power Loss Resilience**: Automatic world corruption guard + restore
- **💾 Automated Backups**: Rotating world backups with automatic restoration
- **🔄 SteamCMD Updates**: Auto-update support for Valheim server (AppID 896660)
- **🌍 Crossplay Support**: Steam + Xbox cross-platform support
- **📊 Enhanced Monitoring**: Real-time player monitoring with A2S protocol support
- **🔧 Modular Design**: Clean separation of configuration, helpers, and commands
- **🛡 Production Ready**: Designed for high uptime and reliable operation

------------------------------------------------------------------------

## ✨ Features

-   ✅ Start / Stop / Restart / Status commands
-   📦 SteamCMD auto-update support (AppID 896660)
-   💾 Automated rotating world backups
-   ⚡ Power-loss world corruption guard + restore
-   🌍 Crossplay support (PlayFab relay)
-   📜 Log management
-   🛠 Fully configurable paths and settings
-   📊 Enhanced player monitoring with A2S protocol support

------------------------------------------------------------------------

## 📋 Prerequisites

Before using this management script, you must install:

-   Linux server (Ubuntu/Debian recommended)
-   SteamCMD
-   Valheim Dedicated Server (AppID 896660)

------------------------------------------------------------------------

# 🚀 Installing Valheim Dedicated Server

Official documentation:
https://valheim.fandom.com/wiki/Valheim_Dedicated_Server

## 1️⃣ Install SteamCMD

Ubuntu / Debian:

    sudo apt update
    sudo apt install steamcmd

Verify installation:

    steamcmd

------------------------------------------------------------------------

## 2️⃣ Install Valheim Dedicated Server

Launch SteamCMD:

    steamcmd

Inside SteamCMD:

    login anonymous
    force_install_dir /home/valheim/server
    app_update 896660 validate
    quit

------------------------------------------------------------------------

# ⚙️ Setup This Manager Script

## 📂 File Structure

This project consists of four modular files:

- **config.conf** — Core configuration (server name, ports, paths, backup, SteamCMD settings)
- **modifiers.conf** — Game modifiers and presets (easily customizable gameplay rules)
- **helpers.sh** — Reusable helper functions (ensure_paths, build_args, is_running, guard_world)
- **valheim-server-manager.sh** — Main script with commands (start, stop, restart, status, logs, update, backup)
- **valheim-monitor.sh** — Standalone monitoring script for external use

### Benefits of This Architecture
- **Easy Configuration** — Update settings in `config.conf` or `modifiers.conf` without touching script logic
- **Focused Files** — Game modifiers separated for easy experimentation and version control
- **Reusable Helpers** — Functions in `helpers.sh` can be sourced by other scripts if needed
- **Clean Separation** — Clear organization of concerns (config, modifiers, utilities, commands)
- **Maintainable** — Each file has a single, clear responsibility

## 📦 Deployment

1.  **Copy all files to your server:**

        config.conf
        modifiers.conf
        helpers.sh
        valheim-server-manager.sh
        valheim-monitor.sh

2.  **Create a `.env` file for client-side configurations:**

    Create a `.env` file in the same directory with your server settings. This file will feed into `config.conf` and provide defaults in case it doesn't exist.

    Copy the `.env.example` file to `.env` and customize it with your server settings:
    
    ```bash
    cp .env.example .env
    ```

    ```bash
    SERVER_NAME="My Valheim Server"
    WORLD_NAME="MyWorld"
    PASSWORD="serverpassword123"

    # Password Requirements:
    # - Minimum 5 characters
    # - Cannot contain or match the world name
    ```

3.  **Customize `config.conf` for your server setup:**

    The `config.conf` file now reads from `.env` with defaults. You can still customize it directly, but it's recommended to use `.env` for client-side configurations.

4.  **(Optional) Customize `modifiers.conf` for gameplay rules:**

    ```bash
    ## First, select your desired customization level
    DEFAULT_MODIFIER_GROUP="standard"  # or "basic", "preset", "hardcore", "custom"
    
    ## Then configure specific settings
    PRESET="Easy"  # or Normal, Hard, Hardcore, etc.
    MODIFIERS=( "Combat=hard" "Resources=less" ... )
    SETKEYS=( "nomap" ... )
    ```

For detailed information about the enhanced modifier system, please refer to the [MODIFIERS.md](MODIFIERS.md) file.

## New "Preset" Modifier Group

A new "preset" modifier group has been added that allows you to use only the preset configuration without any additional modifiers (basic, advanced, or expert). To use this option:

1. Set `DEFAULT_MODIFIER_GROUP="preset"` in `modifiers.conf`
2. Or manually configure the following settings:
   - `ENABLE_BASIC_MODIFIERS=false`
   - `ENABLE_ADVANCED_MODIFIERS=false`
   - `ENABLE_EXPERT_MODIFIERS=false`
   - `ENABLE_CUSTOM_MODIFIERS=false`

## Important Paths

All paths are configured in `config.conf`. Adjust as needed:

    SERVER_DIR="/path/to/valheim"
    SAVEDIR="/srv/valheim/worlds"
    LOG_DIR="/srv/valheim/logs"
    BACKUP_DIR="/srv/valheim/backups"

### Server Directory Configuration

The `SERVER_DIR` can be configured for different installation methods:

- **Standard Steam Installation:** `/home/steam/valheim/valheim_server`
- **Snap Installation:** `/home/vdrvalheim/snap/steam/common/.local/share/Steam/steamapps/common/Valheim dedicated server`
- **Custom Installation:** Specify your own path

The script will use the path defined in `SERVER_DIR` or default to `/home/steam/valheim/valheim_server` if not set.

## Make Executable

On Linux systems, make the script executable:
    
    chmod +x valheim-server-manager.sh

## Enhanced Monitoring

The server manager now supports enhanced player monitoring:
- Uses A2S protocol for real-time accurate player counts
- Falls back to log parsing when A2S is not available
- Includes additional server information in stats output
- Provides a standalone monitoring script `valheim-monitor.sh` for external use

To use A2S protocol, install the python-valve package:
```
pip install python-valve
```

The monitoring script can be used externally:
```
./valheim-monitor.sh monitor json
```

------------------------------------------------------------------------

# 🎮 Usage

```bash
./valheim-server-manager.sh start
./valheim-server-manager.sh stop
./valheim-server-manager.sh restart
./valheim-server-manager.sh stats
./valheim-server-manager.sh logs
./valheim-server-manager.sh update
./valheim-server-manager.sh backup
```

------------------------------------------------------------------------

# 🔄 Automatic Updates

If enabled in `config.conf`:

    USE_STEAMCMD_UPDATE=true

Run:

    ./valheim-server-manager.sh update

This will: - Stop server - Update via SteamCMD - Validate installation

------------------------------------------------------------------------

# 💾 Backup & Recovery

### Automatic Backups

Uses official server flags:

-   -backups
-   -backupshort
-   -backuplong
-   -saveinterval

Backups stored as:

    world-<WORLD_NAME>-<timestamp>.tar.gz

### Corruption Guard

On start:

-   Checks for missing or zero-sized `.db` / `.fwl`
-   Restores most recent backup automatically

Designed for resilience after: - Power loss - VM crashes - Forced
shutdowns

------------------------------------------------------------------------

# 🌍 Crossplay Support

Enable in `config.conf`:

    CROSSPLAY=true

Adds:

    -crossplay

Allows Steam + Xbox cross-platform support.

------------------------------------------------------------------------

# 📁 Recommended Directory Structure

    /srv/valheim/
    ├── worlds/
    ├── logs/
    ├── backups/
    └── valheim.pid

------------------------------------------------------------------------

# 🔐 Security Recommendations

-   Run under dedicated `valheim` user
-   Do not run as root
-   Open ports 2456 and 2457
-   Use firewall rules appropriately

------------------------------------------------------------------------

# 📜 License

MIT License

Copyright (c) 2024 Valheim Server Manager

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

# 🛡 Security & Version Control

Sensitive configuration data should never be committed to version control. The `.env` file is automatically excluded from Git by the included `.gitignore` file. Always create your own `.env` file with your specific server settings and keep it private.

------------------------------------------------------------------------

# 🙌 Built For Homelab Operators

Designed for self-hosted environments requiring:

-   High uptime
-   Backup resilience
-   Simple operational control

## 🌟 Why Choose This Manager?

This Valheim server manager stands out because it combines:

- **Production-Ready Stability**: Built with resilience in mind, including automatic corruption recovery
- **Modular Architecture**: Clean separation of concerns makes customization easy
- **Comprehensive Features**: Everything you need in one package - updates, backups, monitoring, and more
- **Easy Deployment**: Simple setup process with clear documentation
- **Flexible Gameplay**: Advanced modifier system with 5 customization levels to suit any playstyle

Perfect for both casual players wanting to host their own server and experienced administrators looking for a reliable solution.