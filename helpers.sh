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

get_uptime() {
  # Calculate uptime from PID start time
  if ! is_running; then echo "0"; return; fi
  local pid; pid="$(cat "${PIDFILE}" 2>/dev/null)"
  if [[ -z "${pid}" ]]; then echo "0"; return; fi
  local start_time; start_time="$(stat -c %Y /proc/${pid} 2>/dev/null || echo 0)"
  if [[ "${start_time}" -eq 0 ]]; then echo "0"; return; fi
  echo $(($(date +%s) - start_time))
}

format_uptime() {
  local seconds=$1
  local days=$((seconds / 86400))
  local hours=$(((seconds % 86400) / 3600))
  local mins=$(((seconds % 3600) / 60))
  if (( days > 0 )); then
    printf "%dd %dh %dm" "$days" "$hours" "$mins"
  elif (( hours > 0 )); then
    printf "%dh %dm" "$hours" "$mins"
  else
    printf "%dm" "$mins"
  fi
}

get_connected_players() {
  # Parse log for most recent player list (join/disconnect messages)
  if [[ ! -f "${LOGFILE}" ]]; then echo "0"; return; fi
  # Count unique players currently connected by examining recent log entries
  grep -E "Player '[^']*' (connected|disconnected)" "${LOGFILE}" 2>/dev/null | sort | uniq | wc -l
}

count_connected_players() {
  # More accurate: track who connected and disconnected
  if [[ ! -f "${LOGFILE}" ]]; then echo "0"; return 1; fi
  local -A players
  while IFS= read -r line; do
    if [[ $line =~ \"([^\"]+)\"\ (connected|disconnected) ]]; then
      local player="${BASH_REMATCH[1]}"
      local action="${BASH_REMATCH[2]}"
      if [[ "${action}" == "connected" ]]; then
        players["${player}"]=1
      else
        unset 'players["${player}"]'
      fi
    fi
  done < "${LOGFILE}"
  echo "${#players[@]}"
  return 0
}

get_player_count() {
  # Get player count with better error handling and performance optimization
  if [[ ! -f "${LOGFILE}" ]]; then
    echo "0"
    return 1
  fi
  
  # More efficient approach using awk to process log lines directly
  # This avoids calling count_connected_players function and reduces overhead
  local count
  count=$(awk -v logfile="${LOGFILE}" '
    BEGIN {
      # Read only the last 2000 lines for performance (more than enough for player count)
      max_lines = 2000
      line_count = 0
    }
    {
      # Store lines in array for processing
      lines[++line_count] = $0
    }
    END {
      # Process lines from the end backwards to find current players
      connected_players = 0
      player_status = ""
      
      # Process lines from newest to oldest
      for (i = line_count; i >= 1 && connected_players < 1000; i--) {
        line = lines[i]
        
        # Look for player connected/disconnected messages
        if (line ~ /Player \'([^\']+)\' (connected|disconnected)/) {
          # Extract player name and action
          player = line
          gsub(/.*Player \'/, "", player)
          gsub(/\' (connected|disconnected).*/, "", player)
          
          action = line
          gsub(/.* (connected|disconnected).*/, "", action)
          action = tolower(action)
          
          # Update player status
          if (action == "connected") {
            player_status[player] = 1
          } else if (action == "disconnected") {
            player_status[player] = 0
          }
        }
      }
      
      # Count currently connected players
      count = 0
      for (player in player_status) {
        if (player_status[player] == 1) {
          count++
        }
      }
      
      print count
    }
  ' "${LOGFILE}" 2>/dev/null)
  
  # Validate that count is a number
  if [[ -z "$count" ]] || ! [[ "$count" =~ ^[0-9]+$ ]]; then
    echo "0"
    return 1
  fi
  
  echo "$count"
  return 0
}

get_server_ip() {
  # Try to get external IP address (common methods)
  # Check for common public IP detection services
  local ip
  
  # Try curl first (most reliable)
  if command -v curl &>/dev/null; then
    ip=$(curl -s --max-time 2 --connect-timeout 2 ifconfig.me 2>/dev/null || \
         curl -s --max-time 2 --connect-timeout 2 icanhazip.com 2>/dev/null)
    [[ -n "${ip}" ]] && echo "${ip}" && return
  fi
  
  # Fallback to dig/nslookup
  if command -v dig &>/dev/null; then
    ip=$(dig +short myip.opendns.com @resolver1.opendns.com 2>/dev/null | tail -1)
    [[ -n "${ip}" && "${ip}" != ";" ]] && echo "${ip}" && return
  fi
  
  # Fallback to hostname
  if command -v hostname &>/dev/null; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    [[ -n "${ip}" ]] && echo "${ip}" && return
  fi
  
  echo "unknown"
}

get_join_code() {
  # Extract join code and IP from server logs
  # Pattern: Session "ServerName" with join code XXXXXX and IP 1.2.3.4:PORT is active
  if [[ ! -f "${LOGFILE}" ]]; then echo ""; return; fi
  grep -E "with join code [0-9]+" "${LOGFILE}" 2>/dev/null | tail -1 | grep -oE "[0-9]+$"
}

get_server_ip_from_logs() {
  # Extract IP from server logs (more accurate than external IP detection)
  # Pattern: Session "ServerName" with join code XXXXXX and IP 1.2.3.4:PORT is active
  if [[ ! -f "${LOGFILE}" ]]; then echo ""; return 1; fi
  local ip
  ip=$(grep -oE "and IP [0-9.]+:[0-9]+" "${LOGFILE}" 2>/dev/null | tail -1 | cut -d' ' -f3)
  if [[ -n "${ip}" ]]; then
    echo "${ip%:*}"  # Return just the IP part, not the port
    return 0
  else
    echo ""
    return 1
  fi
}
