# Valheim Dedicated Server Manager

> A production-ready Bash toolkit for running a Valheim dedicated server on Linux.
> Deploy, manage, back up, and monitor your server with a single script.

---

## What's Included

| File | Purpose |
|------|---------|
| `valheim-server-manager.sh` | Main script — all commands live here |
| `valheim-monitor.sh` | Standalone monitor with JSON output support |
| `config.conf` | Default settings (paths, ports, backups, SteamCMD) |
| `helpers.sh` | Shared functions used by the manager |
| `env.example` | Template for your `.env` file |
| `modifiers.example.conf` | Template for gameplay modifier settings |
| `api-manager.sh` | Process manager for the HTTP API (start/stop/restart/status) |
| `api/` | FastAPI application — exposes server status and commands over HTTP |

---

## Prerequisites

- Linux server — Ubuntu 22.04 / Debian 12 recommended
- `sudo` / root access (required for the `deploy` command only)
- ~1.5 GB free disk space for server files
- Internet access for SteamCMD downloads

---

## Quick Start

### Step 1 — Clone and configure

```bash
git clone <repo-url>
cd Valheim-Server-Deployment
cp env.example .env
```

Open `.env` and set your server identity:

```bash
SERVER_NAME="My Valheim Server"
WORLD_NAME="MyWorld"
PASSWORD="yourpassword"   # min 5 chars — must not contain the world name
```

### Step 2 — Deploy

```bash
sudo ./valheim-server-manager.sh deploy
```

This single command handles the full first-time setup:

- Enables 32-bit support (`dpkg --add-architecture i386`)
- Adds the multiverse repository and updates package lists
- Installs SteamCMD and required 32-bit libraries
- Downloads the Valheim dedicated server (AppID 896660, ~1 GB)
- Creates the `server/` directory and writes `SERVER_DIR` to your `.env`

### Step 3 — Start

```bash
./valheim-server-manager.sh start
```

Your server is now running. Players connect via: `<your-server-ip>:2456`

---

## Commands

```bash
./valheim-server-manager.sh <command>
```

| Command | Description |
|---------|-------------|
| `start` | Start the server in the background. Restores from backup if world files are missing or corrupt |
| `stop` | Gracefully stop the server (SIGINT → SIGTERM → SIGKILL) |
| `restart` | Stop then start |
| `stats` | Show live status, uptime, storage usage, and connection details |
| `logs` | Tail the live server log |
| `backup` | Create a timestamped world backup without stopping the server |
| `update` | Stop the server, pull the latest build via SteamCMD, then exit |
| `deploy` | Full first-time install: SteamCMD, dependencies, and server files |

---

## Configuration

### `.env` — Your server settings

Copy from `env.example`. This file is gitignored so passwords and paths stay local.

```bash
# Identity
SERVER_NAME="My Valheim Server"
WORLD_NAME="MyWorld"
PASSWORD="yourpassword"

# Networking
PORT=2456         # Valheim uses this port and PORT+1 (UDP)
PUBLIC=1          # 1 = listed on server browser, 0 = hidden (join by IP only)
CROSSPLAY=true    # Enables PlayFab relay for Steam + Xbox cross-platform play

# Paths
SERVER_DIR="/path/to/server"        # Set automatically by deploy
SAVEDIR="/srv/valheim/worlds"       # Where Valheim writes world saves
LOG_DIR="/srv/valheim/logs"
BACKUP_DIR="/srv/valheim/backups"

# Backups & autosave
SAVE_INTERVAL=300     # Flush world to disk every 5 minutes
BACKUPS_KEEP=12       # Number of rolling backups to retain
BACKUP_SHORT=900      # Time before first in-game backup (15 min)
BACKUP_LONG=3600      # Time between subsequent in-game backups (60 min)

# SteamCMD
USE_STEAMCMD_UPDATE=true
STEAMCMD_BIN="/usr/games/steamcmd"
```

> **Note:** Valheim stores world files inside a `worlds_local/` subfolder within `SAVEDIR`.
> The manager accounts for this automatically — set `SAVEDIR` to the parent directory.

### `modifiers.conf` — Gameplay rules

Controls combat difficulty, resource rates, raids, portals, and more.
Created automatically from `modifiers.example.conf` on first run and never overwritten by updates.

```bash
DEFAULT_MODIFIER_GROUP="standard"   # preset | basic | standard | hardcore | custom
PRESET="normal"                     # casual | easy | normal | hard | hardcore | immersive | hammer

BASIC_MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)
```

See [MODIFIERS.md](MODIFIERS.md) for the full modifier reference.

---

## Backups & Recovery

### Manual backup

```bash
./valheim-server-manager.sh backup
```

Creates `world-<WORLD_NAME>-<timestamp>.tar.gz` in `BACKUP_DIR`. The server keeps running — Valheim flushes saves on `SAVE_INTERVAL` so live backups are safe.

### Automatic in-game backups

The server's built-in backup flags are passed at startup:

```
-saveinterval 300    # flush world to disk every 5 min
-backups 12          # keep 12 rolling backups
-backupshort 900     # first backup after 15 min of uptime
-backuplong 3600     # subsequent backups every 60 min
```

Tune these values in `.env` with `SAVE_INTERVAL`, `BACKUPS_KEEP`, `BACKUP_SHORT`, and `BACKUP_LONG`.

### Corruption guard

On `start`, the manager checks that the world `.db` and `.fwl` files exist and are non-empty. If they are missing or zero-sized — common after a power cut or forced shutdown — it automatically restores from the most recent backup before launching the server.

---

## Monitoring

```bash
./valheim-server-manager.sh stats
```

Displays live status, uptime, world size, backup count, and connection details.

The standalone monitor script also supports JSON output for dashboards or external tools:

```bash
./valheim-monitor.sh monitor json
```

---

## Management API

An optional HTTP API built with FastAPI exposes server status and control commands over a secure REST interface. It is designed to integrate with a centralised web dashboard that manages multiple game servers (Valheim, 7 Days to Die, etc.).

### Endpoints at a glance

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Uptime check — returns server identity |
| GET | `/status` | Key | Full status: running state, players, uptime, version, join code |
| POST | `/server/start` | Key | Start the server |
| POST | `/server/stop` | Key | Stop the server |
| POST | `/server/restart` | Key | Restart the server |
| POST | `/server/backup` | Key | Trigger a live backup |
| GET | `/logs?lines=100` | Key | Recent log lines |
| GET | `/logs/stream` | Key | Live log tail via Server-Sent Events |

All authenticated endpoints require an `X-API-Key` header. The API will not start unless `API_ENABLED=true` is set in `.env`.

### Quick setup

```bash
# Install dependencies
python3 -m venv .venv && .venv/bin/pip install -r api/requirements.txt

# Generate an API key and add it to .env
python3 -c "import secrets; print(secrets.token_hex(32))"
# In .env: set API_KEYS="<key>" and API_ENABLED=true

# Start the API
./api-manager.sh start
./api-manager.sh status
```

See [api/README.md](api/README.md) for full configuration, nginx HTTPS setup, systemd service, and multi-server dashboard integration.

---

## Recommended Directory Layout

```
/srv/valheim/
├── worlds/           # World save files (SAVEDIR)
│   └── worlds_local/ # Valheim writes saves here automatically
├── logs/             # Server log output (LOG_DIR)
├── backups/          # Timestamped backup archives (BACKUP_DIR)
└── valheim.pid       # PID file
```

Set up the directories and a dedicated service account:

```bash
sudo useradd -r -m -U -d /srv/valheim valheim
sudo mkdir -p /srv/valheim/{worlds,logs,backups}
sudo chown -R valheim:valheim /srv/valheim
sudo chmod -R 755 /srv/valheim
```

---

## Crossplay (Steam + Xbox)

Enable in `.env`:

```bash
CROSSPLAY=true
```

This adds `-crossplay` to the server launch arguments, routing connections through the PlayFab relay so Steam and Xbox players can join the same server.

---

## Updates

```bash
./valheim-server-manager.sh update
```

Stops the server, downloads the latest Valheim build via SteamCMD, then exits cleanly. Run `start` afterwards to bring the server back up. Requires `USE_STEAMCMD_UPDATE=true` in `.env`.

---

## Security Recommendations

- **Use a dedicated user.** Run day-to-day operations as a non-root `valheim` user. Only `deploy` requires root.
- **Open the right ports.** Valheim needs UDP **2456** and **2457** open in your firewall.
- **Keep `.env` private.** It's already in `.gitignore`. Never commit passwords or paths.
- **Choose a strong password.** Minimum 5 characters. Must not contain or match `WORLD_NAME`.
- **API is opt-in.** The Management API is disabled by default (`API_ENABLED=false`). Only enable it when you have set a strong `API_KEYS` value and have HTTPS in place via a reverse proxy.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Missing configuration` from SteamCMD | SteamCMD hasn't initialized itself yet | Re-run `deploy` — it now runs SteamCMD's self-update first |
| `World files not found` on backup | `SAVEDIR` points to wrong path | Confirm files are in `$SAVEDIR/worlds_local/` |
| Server not visible in browser | `PUBLIC=0` or firewall blocking UDP 2456–2457 | Set `PUBLIC=1` and check firewall rules |
| Players can't connect across platforms | Crossplay not enabled | Set `CROSSPLAY=true` in `.env` and restart |

---

## License

MIT — Copyright (c) 2024 Valheim Server Manager

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
