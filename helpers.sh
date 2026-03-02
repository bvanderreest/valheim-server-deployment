#!/usr/bin/env bash
# Valheim server manager — Helper functions

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

is_running() { [ -f "${PIDFILE}" ] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null; }

latest_backup() { ls -1t "${BACKUP_DIR}"/world-"${WORLD_NAME}"-*.tar.gz 2>/dev/null | head -n 1; }

guard_world() {
  # If current world files are missing or zero-sized (common after power cut), restore the newest backup.
  local db="${SAVEDIR}/${WORLD_NAME}.db"
  local fwl="${SAVEDIR}/${WORLD_NAME}.fwl"
  if [ ! -f "${db}" ] || [ ! -s "${db}" ] || [ ! -f "${fwl}" ] || [ ! -s "${fwl}" ]; then
    local last; last="$(latest_backup || true)"
    if [ -n "${last}" ]; then
      echo "[guard] Damaged/missing world. Restoring from ${last}"
      tar -xzf "${last}" -C "${SAVEDIR}"
      echo "[guard] Restore complete."
    else
      echo "[guard] No backups found; starting with current files (if any)."
    fi
  fi
}

get_uptime() {
  # Calculate uptime from PID start time
  if ! is_running; then echo "0"; return; fi
  local pid; pid="$(cat "${PIDFILE}" 2>/dev/null)"
  if [ -z "${pid}" ]; then echo "0"; return; fi
  local start_time; start_time="$(stat -c %Y /proc/${pid} 2>/dev/null || echo 0)"
  if [ "${start_time}" -eq 0 ]; then echo "0"; return; fi
  echo $(($(date +%s) - start_time))
}

format_uptime() {
  local seconds=$1
  local days=$((seconds / 86400))
  local hours=$(((seconds % 86400) / 3600))
  local mins=$(((seconds % 3600) / 60))
  if [ $days -gt 0 ]; then
    printf "%dd %dh %dm" "$days" "$hours" "$mins"
  elif [ $hours -gt 0 ]; then
    printf "%dh %dm" "$hours" "$mins"
  elif [ $mins -gt 0 ]; then
    printf "%dm" "$mins"
  else
    echo "0m"
  fi
}

count_connected_players() {
  # More accurate: track who connected and disconnected
  if [ ! -f "${LOGFILE}" ]; then echo "0"; return; fi
  local players=""
  while IFS= read -r line; do
    # Try to match the format with player names: "Player 'PlayerName' connected/disconnected"
    if echo "$line" | grep -q "Player '[^']*' connected"; then
      local player=$(echo "$line" | sed -n "s/.*Player '\([^']*\)'.*/\1/p")
      players="$players $player"
    elif echo "$line" | grep -q "Player '[^']*' disconnected"; then
      local player=$(echo "$line" | sed -n "s/.*Player '\([^']*\)'.*/\1/p")
      players=$(echo "$players" | sed "s/ $player//")
    fi
  done < "${LOGFILE}"
  echo "$players" | wc -w
}

get_server_ip() {
  # Try to get external IP address (common methods)
  # Check for common public IP detection services
  local ip
  ip=$(curl -s https://api.ipify.org 2>/dev/null) || ip=$(curl -s https://icanhazip.com 2>/dev/null) || ip=$(curl -s https://ident.me 2>/dev/null) || ip="unknown"
  echo "$ip"
}

get_server_info() {
  # Get server info for display
  local uptime
  uptime=$(get_uptime)
  local players
  players=$(count_connected_players)
  local status
  if is_running; then
    status="running"
  else
    status="stopped"
  fi
  echo "Status: $status"
  echo "Uptime: $(format_uptime $uptime)"
  echo "Players: $players"
}

get_join_code() {
  # Extract join code from server logs
  if [ ! -f "${LOGFILE}" ]; then
    echo ""
    return
  fi
  
  # Look for the line that contains the join code
  local join_code
  join_code=$(grep -oE "Session [^ ]+ with join code [0-9]+ and IP [0-9.]+:[0-9]+ is active" "${LOGFILE}" | tail -1 | grep -oE "[0-9]+$" 2>/dev/null || echo "")
  
  if [ -n "${join_code}" ]; then
    echo "${join_code}"
  else
    # Try alternative pattern for join code extraction
    join_code=$(grep -oE "join code [0-9]+" "${LOGFILE}" | tail -1 | grep -oE "[0-9]+$" 2>/dev/null || echo "")
    echo "${join_code}"
  fi
}

get_server_ip_from_logs() {
  # Extract server IP from logs
  if [ ! -f "${LOGFILE}" ]; then
    echo ""
    return
  fi
  
  # Look for the IP address in the logs
  local ip
  ip=$(grep -oE "Session [^ ]+ with join code [0-9]+ and IP [0-9.]+:[0-9]+ is active" "${LOGFILE}" | tail -1 | grep -oE "[0-9.]+:[0-9]+" | cut -d':' -f1 2>/dev/null || echo "")
  echo "${ip}"
}