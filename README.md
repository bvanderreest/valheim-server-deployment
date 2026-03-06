# 🛡 Valheim Dedicated Server Manager

A resilient, production-ready Bash management script for running a **Valheim Dedicated Server** on Linux. Handles the full server lifecycle — deployment, updates, backups, crash recovery, and configurable gameplay modifiers — split across modular files for clean separation of configuration, helpers, and commands. Perfect for homelab operators and server administrators who want a robust, easy-to-use solution.

## 🚀 Key Features

- **⚡ One-Command Deploy**: Install the server and all dependencies with a single command
- **🎮 Game Modifiers**: Tiered modifier system (basic, standard, hardcore, custom, preset)
- **⚡ Power Loss Resilience**: Automatic world corruption guard + restore on startup
- **💾 Live Backups**: Rotating world backups without stopping the server
- **🔄 SteamCMD Updates**: Auto-update support for Valheim server (AppID 896660)
- **🌍 Crossplay Support**: Steam + Xbox cross-platform via PlayFab relay
- **📊 Server Stats**: Real-time status, uptime, player count, and connect info
- **🔧 Modular Design**: Config, helpers, and commands cleanly separated

------------------------------------------------------------------------

## 📋 Prerequisites

- Linux server (Ubuntu/Debian recommended)
- `sudo` / root access (required for `deploy`)
- Internet access (SteamCMD downloads ~1 GB of server files)

------------------------------------------------------------------------

## 🚀 Quick Start

### 1️ — Clone and configure

```bash
git clone <repo-url>
cd Valheim-Server-Deployment
cp env.example .env
```

Edit `.env` with your server settings:

```bash
SERVER_NAME="My Valheim Server"
WORLD_NAME="MyWorld"
PASSWORD="serverpassword123"   # min 5 chars, cannot contain the world name
```

### 2️ — Deploy

```bash
sudo ./valheim-server-manager.sh deploy
```

This single command:
- Enables 32-bit support (`dpkg --add-architecture i386`)
- Adds the multiverse repository
- Installs SteamCMD and required libraries
- Downloads the Valheim dedicated server via SteamCMD (AppID 896660)
- Sets up the `server/` directory and writes your `SERVER_DIR` to `.env`

### 3️ — Start

```bash
./valheim-server-manager.sh start
```

------------------------------------------------------------------------

## 📂 File Structure

```
Valheim-Server-Deployment/
├── valheim-server-manager.sh   # Main script — all commands live here
├── valheim-monitor.sh          # Standalone monitoring script (text or JSON output)
├── config.conf                 # Core config: paths, ports, SteamCMD, backup settings
├── helpers.sh                  # Shared functions: build_args, guard_world, backups, etc.
├── modifiers.example.conf      # Modifier template — copy to modifiers.conf to customise
├── modifiers.conf              # Your modifier settings (not overwritten on update)
├── env.example                 # Environment variable template
├── .env                        # Your local settings (gitignored)
└── server/                     # Valheim server files (created by deploy)
```

------------------------------------------------------------------------

## ⚙️ Configuration

### `.env` — Your server identity

Created from `env.example`. Override any `config.conf` default here. Gitignored so your passwords stay safe.

```bash
SERVER_NAME="My Valheim Server"
WORLD_NAME="MyWorld"
PASSWORD="serverpassword123"
PORT=2456
PUBLIC=1
CROSSPLAY=true
STEAMCMD_BIN="/usr/games/steamcmd"
SAVEDIR="/srv/valheim/worlds"
LOG_DIR="/srv/valheim/logs"
BACKUP_DIR="/srv/valheim/backups"
```

### `modifiers.conf` — Gameplay rules

Created automatically from `modifiers.example.conf` on first run. Customise without worrying about it being overwritten.

```bash
# Pick your tier: preset | basic | standard | hardcore | custom
DEFAULT_MODIFIER_GROUP="standard"

# Baseline preset: casual | easy | normal | hard | hardcore | immersive | hammer
PRESET="normal"

# The 5 official vanilla modifier categories
BASIC_MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)
```

> **Note on modifier tiers:** `BASIC_MODIFIERS` maps to the 5 vanilla `-modifier` categories. `ADVANCED_MODIFIERS` and `EXPERT_MODIFIERS` are reserved for modded servers (e.g. ValheimPlus). `SETKEYS` are game-world toggles like `nomap` or `noevent` — all commented out by default since they're drastic changes.

See [MODIFIERS.md](MODIFIERS.md) for full details.

------------------------------------------------------------------------

## 🎮 Usage

```bash
./valheim-server-manager.sh <command>
```

| Command   | Description |
|-----------|-------------|
| `deploy`  | Install SteamCMD, dependencies, and download the Valheim server |
| `start`   | Start the server (restores from backup if world files are missing/corrupt) |
| `stop`    | Gracefully stop the server (SIGINT → SIGTERM → SIGKILL) |
| `restart` | Stop then start |
| `stats`   | Show server status, uptime, player count, and connection info |
| `logs`    | Tail the server log live |
| `update`  | Stop server, update via SteamCMD, restart |
| `backup`  | Create a timestamped world backup (server stays running) |

------------------------------------------------------------------------

## 🔄 Updates

```bash
./valheim-server-manager.sh update
```

Stops the server, pulls the latest Valheim server build via SteamCMD, then exits (run `start` to bring it back up). Requires `USE_STEAMCMD_UPDATE=true` in `.env`.

------------------------------------------------------------------------

## 💾 Backup & Recovery

### Manual backup

```bash
./valheim-server-manager.sh backup
```

Creates `world-<WORLD_NAME>-<timestamp>.tar.gz` in `BACKUP_DIR`. The server stays running — Valheim flushes saves on `SAVE_INTERVAL` so live backups are safe.

### Automatic in-game backups

The server's built-in backup flags are passed on start:

```
-saveinterval 300    # flush world to disk every 5 min
-backups 12          # keep 12 rolling backups
-backupshort 900     # first backup after 15 min
-backuplong 3600     # subsequent backups every 60 min
```

### Corruption guard

On `start`, the manager checks whether the world `.db` and `.fwl` files exist and are non-empty. If they're missing or zero-sized (common after a power cut or forced shutdown), it automatically restores from the most recent backup before launching.

------------------------------------------------------------------------

## 🌍 Crossplay

Enable in `.env`:

```bash
CROSSPLAY=true
```

Adds `-crossplay` to the server launch args, enabling the PlayFab relay for Steam + Xbox cross-platform play.

------------------------------------------------------------------------

## 📊 Monitoring

```bash
./valheim-server-manager.sh stats
```

Shows live status, uptime, player count, join code (when available), connection details, world size, and backup count.

The standalone monitor script supports JSON output for integration with external tools:

```bash
./valheim-monitor.sh monitor json
```

------------------------------------------------------------------------

## 📁 Recommended Directory Layout

```
/srv/valheim/
├── worlds/       # world save files (SAVEDIR)
├── logs/         # server log (LOG_DIR)
├── backups/      # timestamped tarballs (BACKUP_DIR)
└── valheim.pid   # PID file (PIDFILE)
```

### Directory permissions

```bash
sudo mkdir -p /srv/valheim/{worlds,logs,backups}
sudo useradd -r -m -U -d /srv/valheim valheim
sudo chown -R valheim:valheim /srv/valheim
sudo chmod -R 755 /srv/valheim
```

------------------------------------------------------------------------

## 🔐 Security Recommendations

- Run under a dedicated `valheim` user — do not run as root for day-to-day operation (`deploy` is the exception)
- Open UDP ports **2456** and **2457** in your firewall
- Keep `.env` out of version control (already in `.gitignore`)
- Use a strong password (minimum 5 characters, must not contain or match the world name)

------------------------------------------------------------------------

## 🙌 Built For Homelab Operators

Designed for self-hosted environments that need:

- High uptime with automatic crash + corruption recovery
- Simple operational control without babysitting
- Flexible gameplay configuration for your community

------------------------------------------------------------------------

## 📜 License

MIT License — Copyright (c) 2024 Valheim Server Manager

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
