
#!/usr/bin/env bash
# Valheim server manager — manual control, resilient to power loss.
# Commands: start | stop | restart | status | logs | update | backup

set -eo pipefail

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

########################################
#               HELPERS                #
########################################

ensure_paths() { mkdir -p "${SAVEDIR}" "${LOG_DIR}" "${BACKUP_DIR}"; }

build_args() {
  local args=()
  args+=( -nographics -batchmode )
  args+=( -name "${SERVER_NAME}" -port "${PORT}" -world "${WORLD_NAME}" -password "${PASSWORD}" )
  args+=( -public "${PUBLIC}" -savedir "${SAVEDIR}" -logFile "${LOGFILE}" )
  args+=( -saveinterval "${SAVE_INTERVAL}" -backups "${BACKUPS_KEEP}" -backupshort "${BACKUP_SHORT}" -backuplong "${BACKUP_LONG}" )
  [[ "${CROSSPLAY}" == "true" ]] && args+=( -crossplay )
  [[ -n "${PRESET}" ]] && args+=( -preset "${PRESET}" )
  for m in "${MODIFIERS[@]}"; do
    local cat="${m%%=*}" val="${m#*=}"
    [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
  done
  for k in "${SETKEYS[@]}"; do
    [[ -n "${k}" ]] && args+=( -setkey "${k,,}" )
  done
  printf '%s\n' "${args[@]}"
}

is_running() { [[ -f "${PIDFILE}" ]] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null; }

latest_backup() { ls -1t "${BACKUP_DIR}"/world-"${WORLD_NAME}"-*.tar.gz 2>/dev/null | head -n 1; }

guard_world() {
  # If current world files are missing or zero-sized (common after power cut), restore the newest backup.
  local db="${SAVEDIR}/${WORLD_NAME}.db"
  local fwl="${SAVEDIR}/${WORLD_NAME}.fwl"
  if [[ ! -f "${db}" || ! -s "${db}" || ! -f "${fwl}" || ! -s "${fwl}" ]]; then
    local last; last="$(latest_backup || true)"
    if [[ -n "${last}" ]]; then
      echo "[guard] Damaged/missing world. Restoring from ${last}"
      tar -xzf "${last}" -C "${SAVEDIR}"
      echo "[guard] Restore complete."
    else
      echo "[guard] No backups found; starting with current files (if any)."
    fi
  fi
}

########################################
#               COMMANDS               #
########################################

start() {
  ensure_paths
  guard_world

  if is_running; then echo "Already running (PID $(cat "${PIDFILE}"))."; exit 0; fi

  # Enter server directory so ./linux64 resolves for Steam init
  cd "${SERVER_DIR}"

  # Steam runtime env (Linux): required for Steam backend init
  export templdpath="$LD_LIBRARY_PATH"
  export LD_LIBRARY_PATH="./linux64:$LD_LIBRARY_PATH"
  export SteamAppId=892970
  [[ -f "${SERVER_DIR}/steam_appid.txt" ]] || echo 892970 > "${SERVER_DIR}/steam_appid.txt"

  mapfile -t ARGS < <(build_args)
  echo "[start] Exec:" "${BINARY}" "${ARGS[@]}"
  "${BINARY}" "${ARGS[@]}" &
  echo $! > "${PIDFILE}"
  echo "[start] PID $(cat "${PIDFILE}"); logs: ${LOGFILE}"
}

stop() {
  if ! is_running; then echo "Server is not running."; exit 0; fi
  local pid; pid="$(cat "${PIDFILE}")"
  echo "[stop] SIGINT ${pid} (graceful)…"; kill -SIGINT "${pid}" 2>/dev/null || true
  for i in {1..60}; do
    if ! kill -0 "${pid}" 2>/dev/null; then echo "[stop] Stopped."; rm -f "${PIDFILE}"; return 0; fi
    sleep 1
  done
  echo "[stop] Timeout; SIGTERM…"; kill -SIGTERM "${pid}" 2>/dev/null || true
  sleep 5
  kill -0 "${pid}" 2>/dev/null && echo "[stop] Force SIGKILL…" && kill -9 "${pid}" 2>/dev/null || true
  rm -f "${PIDFILE}"
}

restart() { stop; sleep 2; start; }
status()  { is_running && echo "RUNNING (PID $(cat "${PIDFILE}"))" || echo "STOPPED"; }
logs()    { ensure_paths; echo "Tailing ${LOGFILE} (Ctrl+C to exit)…"; touch "${LOGFILE}"; tail -n 200 -F "${LOGFILE}"; }

update() {
  if [[ "${USE_STEAMCMD_UPDATE}" != "true" ]]; then echo "SteamCMD update disabled."; return 0; fi
  [[ -x "${STEAMCMD_BIN}" ]] || { echo "SteamCMD not found at ${STEAMCMD_BIN}"; exit 1; }
  is_running && { echo "[update] Stopping…"; stop; }
  echo "[update] Updating app 896660 to ${SERVER_DIR}…"
  "${STEAMCMD_BIN}" +login "${STEAM_LOGIN}" +force_install_dir "${SERVER_DIR}" +app_update 896660 validate +quit
  echo "[update] Done."
}

backup() {
  ensure_paths
  local ts; ts="$(date +"%Y-%m-%d_%H-%M-%S")"
  local out="${BACKUP_DIR}/world-${WORLD_NAME}-${ts}.tar.gz"
  echo "[backup] Creating ${out}…"
  tar -czf "${out}" -C "${SAVEDIR}" "${WORLD_NAME}.db" "${WORLD_NAME}.fwl"
  echo "[backup] OK."
}

usage() { echo "Usage: $0 {start|stop|restart|status|logs|update|backup}"; }

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  logs) logs ;;
  update) update ;;
  backup) backup ;;
  *) usage; exit 1 ;;
esac
