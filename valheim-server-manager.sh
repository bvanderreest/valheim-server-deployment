#!/usr/bin/env bash
# Valheim server manager — manual control, resilient to power loss.
# Commands: start | stop | restart | stats | logs | update | backup | deploy

set -eo pipefail

# Source configuration and helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.conf"
source "${SCRIPT_DIR}/helpers.sh"

########################################
#               COMMANDS               #
######################################

start() {
  ensure_paths
  guard_world

  if is_running; then echo "Already running (PID $(cat "${PIDFILE}"))."; exit 0; fi

  # Enter server directory so ./linux64 resolves for Steam init
  cd "${SERVER_DIR}"

 # Verify server directory exists
 if [[ ! -d "${SERVER_DIR}" ]]; then
   echo "Error: Server directory does not exist: ${SERVER_DIR}"
   exit 1
 fi
 
 # Verify binary exists
 if [[ ! -x "${BINARY}" ]]; then
   echo "Error: Server binary not found or not executable: ${BINARY}"
   exit 1
 fi
 
 # Ensure Steam environment is properly initialized
 if [[ -z "${STEAM_RUNTIME}" ]]; then
   export STEAM_RUNTIME=1
 fi

  # Steam runtime env (Linux): required for Steam backend init
  export templdpath="$LD_LIBRARY_PATH"
  export LD_LIBRARY_PATH="./linux64:$LD_LIBRARY_PATH"
  export SteamAppId=892970
  
  # Ensure steam_appid.txt exists
  if [[ ! -f "${SERVER_DIR}/steam_appid.txt" ]]; then
    echo 892970 > "${SERVER_DIR}/steam_appid.txt"
    echo "[start] Created steam_appid.txt"
  fi
  
  # Additional Steam environment variables to prevent initialization errors
  export SteamGameServer=1
  export SteamGameServerInit=1
  export SteamNoLaunch=1
  export SteamPipe=1
  export SteamEnv=1
  
  mapfile -t ARGS < <(build_args)
  echo "[start] Starting, please use the Log command to view its status"
  echo "[start] Exec:" "${BINARY}" "${ARGS[@]}"
  "${BINARY}" "${ARGS[@]}" >> "${LOGFILE}" 2>&1 &
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
logs()    { ensure_paths; echo "Tailing ${LOGFILE} (Ctrl+C to exit)…"; touch "${LOGFILE}"; tail -n 200 -F "${LOGFILE}"; }

stats() {
  echo "═══════════════════════════════════════════════════════"
  echo "  Valheim Server Stats — ${SERVER_NAME}"
  echo "═══════════════════════════════════════════════════════"
  printf "\n"
  
  # Server status & uptime
  if is_running; then
    local pid; pid="$(cat "${PIDFILE}")"
    local uptime; uptime="$(get_uptime)"
    echo "Status:           RUNNING (PID ${pid})"
    echo "Uptime:           $(format_uptime "${uptime}")"
  else
    echo "Status:           STOPPED"
  fi
  
  printf "\n"
  echo "World:            ${WORLD_NAME}"
  echo "Connected:        $(count_connected_players) player(s)"
  
  # Additional server info if A2S is available
  if command -v a2s &> /dev/null; then
    echo "Server Info:"
    local server_name
    server_name=$(a2s info "${SERVER_IP}:${PORT}" 2>/dev/null | grep "name" | cut -d: -f2- | xargs || echo "N/A")
    echo "  Server Name:    ${server_name}"
    local max_players
    max_players=$(a2s info "${SERVER_IP}:${PORT}" 2>/dev/null | grep "maxplayers" | cut -d: -f2- | xargs || echo "N/A")
    echo "  Max Players:    ${max_players}"
  fi
  
  printf "\n"
  local join_code; join_code="$(get_join_code)"
  local server_ip; server_ip="$(get_server_ip_from_logs)"
  [[ -z "${server_ip}" ]] && server_ip="$(get_server_ip)"
  
  echo "Connect:"
  if [[ -n "${join_code}" ]]; then
    echo "  Join Code:      ${join_code}"
    echo "  Server:         ${server_ip}"
  else
    echo "  Server:         ${server_ip}"
    echo "  Port:           ${PORT}"
    echo "  (Join code appears after server starts)"
  fi
  echo "  Password:       ${PASSWORD}"
  
  printf "\n"
  echo "Configuration:"
  echo "  Public:         $([ "${PUBLIC}" -eq 1 ] && echo 'Yes' || echo 'No')"
  echo "  Crossplay:      ${CROSSPLAY}"
  
  printf "\n"
  echo "Storage:"
  [[ -f "${SAVEDIR}/${WORLD_NAME}.db" ]] && {
    local size; size="$(du -sh "${SAVEDIR}/${WORLD_NAME}.db" 2>/dev/null | cut -f1)"
    echo "  World DB:       ${size} (${SAVEDIR}/${WORLD_NAME}.db)"
  }
  [[ -d "${BACKUP_DIR}" ]] && {
    local backup_count; backup_count="$(ls -1 "${BACKUP_DIR}"/world-"${WORLD_NAME}"-*.tar.gz 2>/dev/null | wc -l)"
    echo "  Backups:        ${backup_count} file(s)"
  }
  
  printf "\n"
  echo "═══════════════════════════════════════════════════════"
}

update() {
  if [[ "${USE_STEAMCMD_UPDATE}" != "true" ]]; then echo "SteamCMD update disabled."; return 0; fi
  [[ -x "${STEAMCMD_BIN}" ]] || { echo "SteamCMD not found at ${STEAMCMD_BIN}"; exit 1; }
  is_running && { echo "[update] Stopping…"; stop; }
  echo "[update] Updating app 896660 to ${SERVER_DIR}…"
  "${STEAMCMD_BIN}" +login "${STEAM_LOGIN}" +force_install_dir "${SERVER_DIR}" +app_update 896660 validate +quit
  echo "[update] Done."
}

backup() {
  echo "[backup] Creating backup for world: $WORLD_NAME"
  
  # Check if server is running and stop it for clean backup
  if is_running; then
    echo "[backup] Server is running. Stopping for clean backup.."
    stop
    sleep 2  # Allow time for graceful shutdown
  fi
  
  # Validate backup directory exists
  mkdir -p "$BACKUP_DIR"
  
  # Check if world files exist
  if [[ ! -f "$SAVEDIR/$WORLD_NAME.db" ]] || [[ ! -f "$SAVEDIR/$WORLD_NAME.fwl" ]]; then
    echo "[backup] Warning: World files not found. This may be normal if world hasn't been created yet."
    return 1
  fi
  
  # Create timestamped backup
  local ts; ts="$(date +"%Y-%m-%d_%H-%M-%S")"
  local out="${BACKUP_DIR}/world-${WORLD_NAME}-${ts}.tar.gz"
  echo "[backup] Creating ${out}…"
  
  # Perform backup synchronously
  if tar -czf "$out" -C "$SAVEDIR" "$WORLD_NAME.db" "$WORLD_NAME.fwl"; then
    echo "[backup] OK. Backup completed successfully."
    
    # Clean up old backups (keep last 10)
    cd "$BACKUP_DIR"
    ls -t | grep "^world-$WORLD_NAME-" | tail -n +11 | xargs -r rm
  else
    echo "[backup] ERROR: Backup failed!"
    return 1
  fi
}

deploy() {
  echo "[deploy] Starting deployment of Valheim server..."
  
  # Check if we're running as root (required for system package installation)
  # Note: We don't necessarily need to be root, but we'll warn about it
  if [[ $EUID -ne 0 ]]; then
    echo "[deploy] Warning: This script should be run with sudo or as root to install system packages."
    echo "[deploy] If you encounter permission issues, please run with sudo."
  fi
  
  # Create server directory structure
  local server_dir="${SCRIPT_DIR}/server"
  echo "[deploy] Creating server directory at ${server_dir}"
  
  # Check if directory already exists
  if [[ -d "${server_dir}" ]]; then
    echo "[deploy] Warning: Server directory already exists at ${server_dir}"
    echo "[deploy] If you want to reinstall, please remove the directory first:"
    echo "[deploy]   rm -rf \"${server_dir}\""
    read -p "[deploy] Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "[deploy] Deployment cancelled."
      exit 0
    fi
  fi
  
  mkdir -p "${server_dir}"
  
  # Verify directory was created successfully
  if [[ ! -d "${server_dir}" ]]; then
    echo "[deploy] Error: Failed to create server directory at ${server_dir}"
    exit 1
  fi
  
  # Install required system packages
  echo "[deploy] Installing required system packages..."
  if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    apt-get update
    apt-get install -y lib32gcc-9-dev lib32stdc++6 lib32z1 steamcmd curl wget unzip
  elif command -v yum &> /dev/null; then
    # CentOS/RHEL/Fedora
    yum install -y glibc.i686 libstdc++.i686 zlib.i686 steamcmd curl wget unzip
  elif command -v dnf &> /dev/null; then
    # Fedora
    dnf install -y glibc.i686 libstdc++.i686 zlib.i686 steamcmd curl wget unzip
  else
    echo "[deploy] Warning: Could not detect package manager. Please install steamcmd manually."
  fi
  
  # Check if SteamCMD is installed and working
  if [[ ! -x "$(command -v steamcmd)" ]]; then
    echo "[deploy] Error: SteamCMD not found. Please install it manually or ensure your package manager worked correctly."
    echo "[deploy] You can try installing it manually with: sudo apt-get install steamcmd"
    exit 1
  fi
  
  # Test SteamCMD by running it with a simple command
  if ! steamcmd +quit 2>/dev/null; then
    echo "[deploy] Warning: SteamCMD test failed. Some functionality may be limited."
  fi
  
  # Install Valheim server using SteamCMD
  echo "[deploy] Installing Valheim server via SteamCMD..."
  
  # Ensure the directory is writable by current user for SteamCMD
  # Only change ownership if we're not already root (to avoid potential issues)
  if [[ $EUID -ne 0 ]]; then
    chown -R "$(whoami)" "${server_dir}"
  fi
  
  # Install Valheim server using SteamCMD with better error handling
  if ! steamcmd +login anonymous +force_install_dir "${server_dir}" +app_update 896660 validate +quit; then
    echo "[deploy] Error: Failed to install Valheim server via SteamCMD"
    exit 1
  fi
  
  # Verify installation
  if [[ ! -f "${server_dir}/valheim_server.x86_64" ]]; then
    echo "[deploy] Error: Valheim server binary not found after installation."
    echo "[deploy] This might be due to SteamCMD issues or network problems."
    echo "[deploy] Please check:"
    echo "[deploy]   1. Your internet connection"
    echo "[deploy]   2. SteamCMD installation"
    echo "[deploy]   3. Steam login credentials (if required)"
    exit 1
  fi
  
  # Verify the binary is executable
  if [[ ! -x "${server_dir}/valheim_server.x86_64" ]]; then
    echo "[deploy] Setting executable permissions on server binary..."
    chmod +x "${server_dir}/valheim_server.x86_64"
  fi
  
  # Set up environment variables for the server directory
  echo "[deploy] Setting up environment variables..."
  cat > "${SCRIPT_DIR}/.env" << EOF
SERVER_DIR="${server_dir}"
EOF
  
  # Ensure proper permissions on .env file
  chmod 600 "${SCRIPT_DIR}/.env"
  
  # Update config.conf to use the new server directory
  echo "[deploy] Updating configuration..."
  
  # Create a backup of the original config
  cp "${SCRIPT_DIR}/config.conf" "${SCRIPT_DIR}/config.conf.backup"
  
  # Update SERVER_DIR in config.conf
  sed -i "s|SERVER_DIR.*|SERVER_DIR=\"${server_dir}\"|" "${SCRIPT_DIR}/config.conf"
  
  echo "[deploy] Deployment complete!"
  echo "[deploy] Valheim server installed at: ${server_dir}"
  echo "[deploy] Configuration updated. Please review the .env file."
}

usage() { echo "Usage: $0 {start|stop|restart|stats|logs|update|backup|deploy}"; }

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  stats) stats ;;
  logs) logs ;;
  update) update ;;
  backup) backup ;;
  deploy) deploy ;;
  *) usage; exit 1 ;;
esac