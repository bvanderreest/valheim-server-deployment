# Project Spec — Valheim Dedicated Server Manager

## Overview

A production-ready toolkit for deploying, managing, and monitoring a Valheim dedicated server on a Linux VM. The project is split into two layers: a **Bash management layer** that wraps the Valheim server process, and a **Python HTTP API layer** that exposes control and status to external consumers (dashboards, scripts, automations).

The system is designed for self-hosted homelab environments where a small group of friends runs a persistent Valheim world. It prioritises resilience (world corruption recovery, dependency pre-flight, graceful shutdown), operational simplicity (single-script deploy, one command to start/stop/backup), and extensibility (the API is designed to slot into a multi-game-server dashboard alongside other game servers).

---

## Who It's For

**Primary operator:** A technically capable homelab owner who manages the server via SSH and a centralised dashboard. They want a reliable, low-maintenance server that survives VM reboots, power cuts, and OS upgrades without manual intervention.

**End users:** A small group of friends (Steam and Xbox crossplay). They connect via join code or direct IP and have no visibility into the server infrastructure.

---

## Main Feature Areas

### 1. Server Lifecycle Management (`valheim-server-manager.sh`)

The main entry point for all operations. Commands:

| Command | Behaviour |
|---------|-----------|
| `deploy` | One-shot first-time install: enables i386, installs SteamCMD + all required system libraries (including PlayFab Party dependencies), downloads Valheim server via SteamCMD, writes `SERVER_DIR` to `.env` |
| `start` | Runs pre-flight checks, then launches the server as a background process. Tracks startup milestones with an interactive progress bar. Restores world from backup if files are missing or corrupt |
| `stop` | Graceful shutdown via SIGINT → SIGTERM → SIGKILL with a 60-second window |
| `restart` | Stop + start |
| `update` | Stops the server, pulls the latest build via SteamCMD, exits cleanly |
| `backup` | Archives `.db` and `.fwl` world files into a timestamped `.tar.gz`. Safe while the server is running |
| `stats` | Displays live status: running state, uptime, player count + names, join code, version, world size, backup count |
| `logs` | Tails the live server log |

### 2. Pre-flight Dependency Checking

Runs before every server start. Executes `ldd` against the server binary (`valheim_server.x86_64`) and every `.so` in the Plugins directory. If any shared library is unresolved (e.g. after an OS upgrade removes or renames a package), the start aborts with a clear list of what is missing and which binary needs it — before the server process is ever launched.

Displayed as the first completed stage in the startup progress bar.

### 3. World Resilience & Backup

- **Corruption guard:** On `start`, verifies that `.db` and `.fwl` world files exist and are non-empty. If either is missing or zero-sized (common after power loss or forced shutdown), automatically restores from the most recent backup before launching.
- **Manual backups:** `backup` command creates timestamped archives. Rolling retention controlled by `BACKUPS_KEEP`.
- **In-game auto-backups:** The server's native backup flags (`-saveinterval`, `-backups`, `-backupshort`, `-backuplong`) are passed at launch and configurable via `.env`.
- **Automated scheduling:** `backup-automation.sh` is designed to be called by cron — backs up whether the server is running or stopped, then prunes old archives.

### 4. Configuration System

Three-layer configuration resolved at runtime:

1. **`config.conf`** — Auto-detects paths (SteamCMD, server directory, `steamclient.so`). Sets safe defaults for all variables.
2. **`.env`** — User-specific overrides: server identity, passwords, paths, networking, backup intervals. Gitignored.
3. **`modifiers.conf`** — Gameplay rule overrides (combat difficulty, resources, raids, portals, presets, setkeys, custom args). Created from `modifiers.example.conf` on first run; never overwritten by updates.

### 5. Crossplay / PlayFab Relay

When `CROSSPLAY=true`, the server is launched with `-crossplay`, routing connections through PlayFab's relay network so Steam and Xbox players can join the same world via a 6-character join code. PlayFab Party requires `libpulse-mainloop-glib0` (and related PulseAudio libs) on Linux — the deploy command installs these, and the pre-flight check verifies them on every start.

### 6. HTTP Management API (`api/`)

An optional FastAPI application exposing server status and control over HTTP. Designed to be consumed by a centralised multi-game-server dashboard.

**Endpoints:**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Uptime check — returns server identity |
| GET | `/status` | Key | Full status: running, players, uptime, version, join code, last save |
| POST | `/server/start` | Key | Start server (202 async) |
| POST | `/server/stop` | Key | Stop server (202 async) |
| POST | `/server/restart` | Key | Restart server (202 async) |
| POST | `/server/backup` | Key | Trigger backup (202 async) |
| GET | `/logs?lines=N` | Key | Last N log lines (1–5000) |
| GET | `/logs/stream` | Key | Live log tail via Server-Sent Events |

**Security:** API key auth via `X-API-Key` header. Rate-limited (5 failed attempts per IP per 15 minutes → 429). Binds to `127.0.0.1` only; HTTPS handled by an nginx reverse proxy. Disabled by default (`API_ENABLED=false`).

**Process management:** `api-manager.sh` handles start/stop/restart/status of the API process. Alternatively, a `systemd` unit file is provided.

### 7. Standalone Monitor (`valheim-monitor.sh`)

Lightweight script outputting server state as plain text or JSON. Intended for integration with external monitoring tools or cron-based alerting.

---

## Technical Constraints

### Runtime Environment
- **OS:** Ubuntu 22.04 / Debian 12 (apt-based). The `deploy` command is apt-specific; yum/dnf paths exist but are less tested.
- **Architecture:** x86_64 Linux only. Requires 32-bit support (`dpkg --add-architecture i386`) for SteamCMD.
- **Shell:** Bash 4+. Uses `mapfile`, associative arrays, and process substitution.
- **Python:** 3.11+ for the API layer.

### Steam / Valheim
- Valheim dedicated server is Steam AppID **896660**, installed anonymously via SteamCMD.
- Server binary: `valheim_server.x86_64`. Requires `LD_LIBRARY_PATH` to include `./linux64` for Steam backend init.
- `steam_appid.txt` (containing `892970`) must exist in the server directory.
- PlayFab crossplay requires `libpulse0`, `libpulse-mainloop-glib0`, and `pulseaudio-utils`.

### Networking
- Valheim uses **UDP 2456** (and 2457) for game connections.
- PlayFab relay requires outbound UDP to PlayFab cloud endpoints.
- API binds to loopback only; port configurable via `API_PORT` (default 8080).

### Process Model
- The Valheim server runs as a background process; PID is written to `PIDFILE`.
- The API runs single-worker only — the in-memory rate limiter in `auth.py` is not process-safe. A Redis-backed store would be needed for multi-worker deployments.
- All control commands (`start`, `stop`, etc.) are designed to run as a non-root user. Only `deploy` requires root (for package installation).

### Data Layout
```
/srv/valheim/
├── worlds/worlds_local/   # Valheim writes .db and .fwl here
├── logs/                  # Server log output
├── backups/               # Timestamped .tar.gz archives
└── valheim.pid            # PID file
```

### Multi-Server Dashboard Integration
The API response schema (`StatusResponse`, `ActionResponse`) is intentionally generic — `server_type` and `server_label` fields identify the instance. Only `api/config.py` and `api/routes/server.py` (log-parsing patterns) need updating to adapt this for another game server. All endpoint shapes remain identical so a single dashboard can consume multiple game servers uniformly.
