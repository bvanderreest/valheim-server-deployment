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
  rotate_log
  guard_world

  if is_running; then echo "Already running (PID $(cat "${PIDFILE}"))."; exit 0; fi

  # Verify server directory and binary exist before attempting to cd
  if [[ ! -d "${SERVER_DIR}" ]]; then
    echo "Error: Server directory does not exist: ${SERVER_DIR}"
    exit 1
  fi

  if [[ ! -x "${BINARY}" ]]; then
    echo "Error: Server binary not found or not executable: ${BINARY}"
    exit 1
  fi

  # Enter server directory so ./linux64 resolves for Steam init
  cd "${SERVER_DIR}"

  # Ensure Steam environment is properly initialized
  if [[ -z "${STEAM_RUNTIME}" ]]; then
    export STEAM_RUNTIME=1
  fi

  # Steam runtime env (Linux): required for Steam backend init
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
    local gss; gss="$(get_game_server_status)"
    echo "Status:           RUNNING (PID ${pid})"
    echo "Uptime:           $(format_uptime "${uptime}")"
    [[ -n "${gss}" ]] && echo "Steam:            ${gss}"
  else
    echo "Status:           STOPPED"
  fi

  printf "\n"
  local version; version="$(get_valheim_version)"
  echo "World:            ${WORLD_NAME}"
  [[ -n "${version}" ]] && echo "Version:          ${version}"

  local player_count; player_count="$(count_connected_players)"
  echo "Players:          ${player_count} connected"
  if [[ "${player_count}" -gt 0 ]]; then
    local names; names="$(get_connected_player_names)"
    if [[ -n "${names}" ]]; then
      while IFS= read -r name; do
        echo "  - ${name}"
      done <<< "${names}"
    fi
  fi

  local last_save; last_save="$(get_last_save)"
  [[ -n "${last_save}" ]] && echo "Last Save:        ${last_save}"

  printf "\n"
  echo "Connect:"
  local join_code; join_code="$(get_join_code)"
  [[ -n "${join_code}" ]] && echo "  Join Code:      ${join_code}"
  echo "  Server:         $(get_server_ip):${PORT}"
  echo "  Password:       ${PASSWORD}"

  printf "\n"
  echo "Configuration:"
  echo "  Public:         $([[ "${PUBLIC}" == "1" ]] && echo 'Yes' || echo 'No')"
  echo "  Crossplay:      ${CROSSPLAY}"

  printf "\n"
  echo "Storage:"
  [[ -f "${SAVEDIR}/worlds_local/${WORLD_NAME}.db" ]] && {
    local size; size="$(du -sh "${SAVEDIR}/worlds_local/${WORLD_NAME}.db" 2>/dev/null | cut -f1)"
    echo "  World DB:       ${size} (${SAVEDIR}/worlds_local/${WORLD_NAME}.db)"
  }
  [[ -d "${BACKUP_DIR}" ]] && {
    local backup_count; backup_count="$(ls -1 "${BACKUP_DIR}"/world-"${WORLD_NAME}"-*.tar.gz 2>/dev/null | wc -l)"
    echo "  Backups:        ${backup_count} file(s)"
  }

  printf "\n"
  echo "═══════════════════════════════════════════════════════"
}

check_steam_connectivity() {
  local endpoints=(
    "api.steampowered.com:443"
    "steamcdn-a.akamaihd.net:443"
    "steamcontent.com:443"
    "cm.steampowered.com:27017"
  )
  local reachable=0
  local failed=()

  echo "[update] Checking Steam connectivity..."
  for endpoint in "${endpoints[@]}"; do
    local host="${endpoint%%:*}"
    local port="${endpoint##*:}"
    if curl --silent --max-time 5 --output /dev/null "https://${host}" 2>/dev/null \
       || (echo >/dev/tcp/"${host}"/"${port}") 2>/dev/null; then
      (( reachable++ ))
    else
      failed+=("${endpoint}")
    fi
  done

  if [[ ${reachable} -eq 0 ]]; then
    echo "[update] Error: Cannot reach any Steam endpoint. Check your network and outbound firewall rules (TCP/UDP 27015-27030, TCP 80/443)."
    return 1
  fi

  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "[update] Warning: Some Steam endpoints unreachable: ${failed[*]}"
    echo "[update] Proceeding — ${reachable}/${#endpoints[@]} endpoints reachable."
  else
    echo "[update] Steam connectivity OK (${reachable}/${#endpoints[@]} endpoints reachable)."
  fi
  return 0
}

update() {
  if [[ "${USE_STEAMCMD_UPDATE}" != "true" ]]; then echo "SteamCMD update disabled."; return 0; fi
  [[ -x "${STEAMCMD_BIN}" ]] || { echo "SteamCMD not found at ${STEAMCMD_BIN}"; exit 1; }
  is_running && { echo "[update] Stopping…"; stop; }

  # Remove stale Steam lock files that cause "didn't shutdown cleanly" timeouts
  rm -f "${HOME}/.steam/steam.pid" "${HOME}/.local/share/Steam/steam.pid" 2>/dev/null

  check_steam_connectivity || exit 1

  echo "[update] Updating app 896660 to ${SERVER_DIR}…"
  if ! "${STEAMCMD_BIN}" +force_install_dir "${SERVER_DIR}" +login "${STEAM_LOGIN}" +app_update 896660 validate +quit; then
    echo "[update] Error: SteamCMD failed. Check your network and that ports TCP/UDP 27015-27030 and TCP 80/443 are open outbound."
    exit 1
  fi
  echo "[update] Done."
}

backup() {
  echo "[backup] Creating backup for world: $WORLD_NAME"

  # Valheim stores world files in a worlds_local subdirectory
  local world_dir="${SAVEDIR}/worlds_local"

  # Validate backup directory exists
  mkdir -p "$BACKUP_DIR"

  # Check if world files exist
  if [[ ! -f "$world_dir/$WORLD_NAME.db" ]] || [[ ! -f "$world_dir/$WORLD_NAME.fwl" ]]; then
    echo "[backup] Warning: World files not found at ${world_dir}. This may be normal if world hasn't been created yet."
    return 1
  fi

  # Create timestamped backup
  local ts; ts="$(date +"%Y-%m-%d_%H-%M-%S")"
  local out="${BACKUP_DIR}/world-${WORLD_NAME}-${ts}.tar.gz"
  echo "[backup] Creating ${out}…"

  # Perform backup synchronously
  if tar -czf "$out" -C "$world_dir" "$WORLD_NAME.db" "$WORLD_NAME.fwl"; then
    echo "[backup] OK. Backup completed successfully."
    
    # Clean up old backups, keeping the most recent BACKUPS_KEEP
    find "${BACKUP_DIR}" -maxdepth 1 -name "world-${WORLD_NAME}-*.tar.gz" \
      | sort -r | tail -n +$((BACKUPS_KEEP + 1)) | xargs -r rm --
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
    # Debian/Ubuntu — steamcmd requires i386 and the multiverse repository
    dpkg --add-architecture i386
    add-apt-repository -y multiverse
    apt-get update
    apt-get install -y lib32gcc-s1 lib32stdc++6 steamcmd curl wget unzip
  elif command -v yum &> /dev/null; then
    # CentOS/RHEL/Fedora
    yum install -y glibc.i686 libstdc++.i686 zlib.i686 steamcmd curl wget unzip
  elif command -v dnf &> /dev/null; then
    # Fedora
    dnf install -y glibc.i686 libstdc++.i686 zlib.i686 steamcmd curl wget unzip
  else
    echo "[deploy] Warning: Could not detect package manager. Please install steamcmd manually."
  fi
  
  # Check if SteamCMD is installed — apt installs it to /usr/games/steamcmd which may not be in PATH
  local steamcmd_bin
  steamcmd_bin="$(command -v steamcmd 2>/dev/null || echo "")"
  if [[ -z "${steamcmd_bin}" && -x "/usr/games/steamcmd" ]]; then
    steamcmd_bin="/usr/games/steamcmd"
  fi
  if [[ -z "${steamcmd_bin}" ]]; then
    echo "[deploy] Error: SteamCMD not found. Please install it manually or ensure your package manager worked correctly."
    echo "[deploy] You can try installing it manually with:"
    echo "[deploy]   sudo dpkg --add-architecture i386"
    echo "[deploy]   sudo add-apt-repository multiverse"
    echo "[deploy]   sudo apt-get update && sudo apt-get install steamcmd"
    exit 1
  fi
  echo "[deploy] Found SteamCMD at: ${steamcmd_bin}"

  # Initialize/self-update SteamCMD before downloading the app.
  # Running +quit lets SteamCMD download its own package files; without this
  # the subsequent app_update fails with "Missing configuration".
  echo "[deploy] Initializing SteamCMD (self-update)..."
  if ! "${steamcmd_bin}" +quit; then
    echo "[deploy] Error: SteamCMD failed to initialize. Check your network connection and SteamCMD installation."
    exit 1
  fi
  
  # Install Valheim server using SteamCMD
  echo "[deploy] Installing Valheim server via SteamCMD..."
  
  # Ensure the directory is writable by current user for SteamCMD
  # Only change ownership if we're not already root (to avoid potential issues)
  if [[ $EUID -ne 0 ]]; then
    chown -R "$(whoami)" "${server_dir}"
  fi
  
  # Install Valheim server using SteamCMD with better error handling
  if ! "${steamcmd_bin}" +login anonymous +force_install_dir "${server_dir}" +app_update 896660 validate +quit; then
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
  
  # Set SERVER_DIR in .env, preserving any other settings the user has configured
  echo "[deploy] Setting up environment variables..."
  local env_file="${SCRIPT_DIR}/.env"
  if [[ -f "${env_file}" ]] && grep -q "^SERVER_DIR=" "${env_file}"; then
    sed -i "s|^SERVER_DIR=.*|SERVER_DIR=\"${server_dir}\"|" "${env_file}"
  else
    echo "SERVER_DIR=\"${server_dir}\"" >> "${env_file}"
  fi
  chmod 600 "${env_file}"
  
  echo "[deploy] Deployment complete!"
  echo "[deploy] Valheim server installed at: ${server_dir}"
  echo "[deploy] Configuration updated. Please review the .env file."
}

usage() {
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║          Valheim Server Manager — Command Reference       ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo ""
  echo "  Usage: $0 <command>"
  echo ""
  echo "  ── Server Lifecycle ────────────────────────────────────────"
  echo "  start      Start the Valheim server (background process)"
  echo "  stop       Gracefully stop the running server"
  echo "  restart    Stop and start the server"
  echo ""
  echo "  ── Monitoring ──────────────────────────────────────────────"
  echo "  stats      Show server status, config, and storage info"
  echo "  logs       Tail the live server log output"
  echo ""
  echo "  ── Maintenance ─────────────────────────────────────────────"
  echo "  backup     Archive world files to \$BACKUP_DIR"
  echo "  update     Pull the latest Valheim server build via SteamCMD"
  echo "  deploy     Install SteamCMD, dependencies, and server files"
  echo ""
  echo "  ── Examples ────────────────────────────────────────────────"
  echo "  sudo $0 deploy     # First-time install"
  echo "  $0 start           # Start the server"
  echo "  $0 stats           # Check status and storage"
  echo "  $0 backup          # Manual world backup"
  echo ""
}

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