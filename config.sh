#!/usr/bin/env bash
# Valheim server manager — Configuration file

########################################
#               CONFIG                 #
########################################

# Identity
SERVER_NAME="Lowood-AU"
WORLD_NAME="CrowsNest"
PASSWORD="c4mpusTime"            # >=5 chars; cannot equal/contain world name

# Networking
PORT=2456                        # Valheim uses PORT and PORT+1
PUBLIC=1                         # 1 listed; 0 hidden (join via IP)
CROSSPLAY=true                   # true => -crossplay (PlayFab relay)

# Install paths
SERVER_DIR="/home/vdrvalheim/snap/steam/common/.local/share/Steam/steamapps/common/Valheim dedicated server"
BINARY="${SERVER_DIR}/valheim_server.x86_64"

# Data & logs
SAVEDIR="/srv/valheim/worlds"
LOG_DIR="/srv/valheim/logs"
LOGFILE="${LOG_DIR}/valheim-server.log"
PIDFILE="/srv/valheim/valheim.pid"
BACKUP_DIR="/srv/valheim/backups"

# Resilience: frequent autosaves + server-managed rotating backups (official flags)
SAVE_INTERVAL=300                 # 5 min autosave (official default is 1800)  # see guide
BACKUPS_KEEP=12                   # keep more rolling backups
BACKUP_SHORT=900                  # 15 min between first backups
BACKUP_LONG=3600                  # 60 min between subsequent backups

# Modifiers (official): preset first, then category overrides
PRESET=""                   # Normal|Casual|Easy|Hard|Hardcore|Immersive|Hammer or "" to skip
# Category modifiers: Combat, DeathPenalty, Resources, Raids, Portals
MODIFIERS=(
  "Combat=normal"
  "DeathPenalty=hard"
  "Resources=more"
  "Raids=none"
  "Portals=normal"
)
# Checkbox keys: nobuildcost|playerevents|passivemobs|nomap
SETKEYS=(
  # "nomap"
)

# SteamCMD update (AppID 896660). Switch to your Steam login if anonymous ever fails.
USE_STEAMCMD_UPDATE=true
STEAMCMD_BIN="/usr/games/steamcmd"
STEAM_LOGIN="anonymous"
