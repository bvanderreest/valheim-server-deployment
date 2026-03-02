# 🛡 Valheim Dedicated Server Manager

A resilient, production-ready Bash management script for running a
**Valheim Dedicated Server** on Linux.

This project provides clean lifecycle management, SteamCMD updates,
automatic world backups, crash recovery, and configurable gameplay
modifiers --- split across four modular files for clean separation
of configuration, helpers, and commands.

------------------------------------------------------------------------

## ✨ Features

-   ✅ Start / Stop / Restart / Status commands
-   📦 SteamCMD auto-update support (AppID 896660)
-   💾 Automated rotating world backups
-   ⚡ Power-loss world corruption guard + restore
-   🌍 Crossplay support (PlayFab relay)
-   📜 Log management
-   🛠 Fully configurable paths and settings

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

### Benefits of This Architecture
- **Easy Configuration** — Update settings in `config.conf` or `modifiers.conf` without touching script logic
- **Focused Files** — Game modifiers separated for easy experimentation and version control
- **Reusable Helpers** — Functions in `helpers.sh` can be sourced by other scripts if needed
- **Clean Separation** — Clear organization of concerns (config, modifiers, utilities, commands)
- **Maintainable** — Each file has a single, clear responsibility

## 📦 Deployment

1.  Copy all four files to your server:

        config.conf
        modifiers.conf
        helpers.sh
        valheim-server-manager.sh

2.  Customize `config.conf` for your server setup:

    SERVER_NAME="Your Server Name"
    WORLD_NAME="YourWorld"
    PASSWORD="YourPassword"

    **Password Requirements:**
    - Minimum 5 characters
    - Cannot contain or match the world name

3.  (Optional) Customize `modifiers.conf` for gameplay rules:

    PRESET="Easy"  # or Normal, Hard, Hardcore, etc.
    MODIFIERS=( "Combat=hard" "Resources=less" ... )
    SETKEYS=( "nomap" ... )

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

    chmod +x valheim-server-manager.sh config.conf helpers.sh modifiers.conf

------------------------------------------------------------------------

# 🎮 Usage

    ./valheim-server-manager.sh start
    ./valheim-server-manager.sh stop
    ./valheim-server-manager.sh restart
    ./valheim-server-manager.sh status
    ./valheim-server-manager.sh logs
    ./valheim-server-manager.sh update
    ./valheim-server-manager.sh backup

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

MIT (or your preferred license)

------------------------------------------------------------------------

# 🙌 Built For Homelab Operators

Designed for self-hosted environments requiring:

-   High uptime
-   Backup resilience
-   Simple operational control