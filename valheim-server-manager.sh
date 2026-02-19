
#!/usr/bin/env bash
# Valheim server manager — manual control, resilient to power loss.
# Commands: start | stop | restart | status | logs | update | backup

set -eo pipefail

# Source configuration and helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.conf"
source "${SCRIPT_DIR}/helpers.sh"

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
  ensure_paths
  local ts; ts="$(date +"%Y-%m-%d_%H-%M-%S")"
  local out="${BACKUP_DIR}/world-${WORLD_NAME}-${ts}.tar.gz"
  echo "[backup] Creating ${out}…"
  
  # Create backup asynchronously with progress tracking
  {
    # Get file sizes for progress tracking
    local db_size=0
    local fwl_size=0
    if [[ -f "${SAVEDIR}/${WORLD_NAME}.db" ]]; then
      db_size=$(stat -c %s "${SAVEDIR}/${WORLD_NAME}.db" 2>/dev/null || echo 0)
    fi
    if [[ -f "${SAVEDIR}/${WORLD_NAME}.fwl" ]]; then
      fwl_size=$(stat -c %s "${SAVEDIR}/${WORLD_NAME}.fwl" 2>/dev/null || echo 0)
    fi
    local total_size=$((db_size + fwl_size))
    
    # Create backup with progress indication
    if [[ $total_size -gt 0 ]]; then
      # Use tar with progress indication using pv if available
      if command -v pv &>/dev/null; then
        # If pv is available, show progress
        tar -czf - -C "${SAVEDIR}" "${WORLD_NAME}.db" "${WORLD_NAME}.fwl" | pv -s $total_size > "${out}"
      else
        # Fallback to basic tar with simple progress indication
        echo "[backup] Backup in progress (no progress indicator available)..."
        tar -czf "${out}" -C "${SAVEDIR}" "${WORLD_NAME}.db" "${WORLD_NAME}.fwl"
      fi
    else
      tar -czf "${out}" -C "${SAVEDIR}" "${WORLD_NAME}.db" "${WORLD_NAME}.fwl"
    fi
    echo "[backup] OK."
  } &
  
  # Show that backup is running in background
  echo "[backup] Backup started in background (PID: $!)."
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
