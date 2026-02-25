#!/usr/bin/env bash
# Valheim server manager — Helper functions

########################################
#               HELPERS                #
########################################

ensure_paths() { mkdir -p "${SAVEDIR}" "${LOG_DIR}" "${BACKUP_DIR}"; }

# Function to set modifier group variables based on DEFAULT_MODIFIER_GROUP
set_modifier_group() {
  # Default to standard if not set
  local modifier_group="${DEFAULT_MODIFIER_GROUP:-standard}"
  
  # Reset all modifier group flags
  ENABLE_BASIC_MODIFIERS=false
  ENABLE_ADVANCED_MODIFIERS=false
  ENABLE_EXPERT_MODIFIERS=false
  ENABLE_CUSTOM_MODIFIERS=false
  
  # Set modifier group based on selection
  case "${modifier_group,,}" in
    "basic")
      ENABLE_BASIC_MODIFIERS=true
      ;;
    "preset")
      # For preset only, we disable all modifier tiers except preset
      # This means we don't enable any modifiers, just use the preset
      # The preset is handled separately via -preset flag in build_args
      ;;
    "standard")
      ENABLE_BASIC_MODIFIERS=true
      ENABLE_ADVANCED_MODIFIERS=true
      ;;
    "hardcore")
      ENABLE_BASIC_MODIFIERS=true
      ENABLE_ADVANCED_MODIFIERS=true
      ENABLE_EXPERT_MODIFIERS=true
      ;;
    "custom")
      ENABLE_CUSTOM_MODIFIERS=true
      ;;
    *)
      # Default to standard if invalid value
      ENABLE_BASIC_MODIFIERS=true
      ENABLE_ADVANCED_MODIFIERS=true
      echo "Warning: Invalid DEFAULT_MODIFIER_GROUP '${modifier_group}', defaulting to 'standard'" >&2
      ;;
  esac
}

build_args() {
  # Source base configuration first
  local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  source "${script_dir}/modifiers-base.conf"
  
  # Source user configuration if it exists
  if [[ -f "${script_dir}/modifiers-user.conf" ]]; then
    source "${script_dir}/modifiers-user.conf"
  fi
  
  # Set modifier group variables based on DEFAULT_MODIFIER_GROUP
  set_modifier_group
  
  local args=()
  args+=( -nographics -batchmode )
  args+=( -name "${SERVER_NAME}" -port "${PORT}" -world "${WORLD_NAME}" -password "${PASSWORD}" )
  args+=( -public "${PUBLIC}" -savedir "${SAVEDIR}" -logFile "${LOGFILE}" )
  args+=( -saveinterval "${SAVE_INTERVAL}" -backups "${BACKUPS_KEEP}" -backupshort "${BACKUP_SHORT}" -backuplong "${BACKUP_LONG}" )
  [[ "${CROSSPLAY}" == "true" ]] && args+=( -crossplay )
  [[ -n "${PRESET}" ]] && args+=( -preset "${PRESET}" )
  
  # Process basic modifiers
  if [[ "${ENABLE_BASIC_MODIFIERS}" == "true" ]]; then
    for m in "${BASIC_MODIFIERS[@]}"; do
      local cat="${m%%=*}" val="${m#*=}"
      [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
    done
  fi
  
  # Process advanced modifiers
  if [[ "${ENABLE_ADVANCED_MODIFIERS}" == "true" ]]; then
    for m in "${ADVANCED_MODIFIERS[@]}"; do
      local cat="${m%%=*}" val="${m#*=}"
      [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
    done
  fi
  
  # Process expert modifiers
  if [[ "${ENABLE_EXPERT_MODIFIERS}" == "true" ]]; then
    for m in "${EXPERT_MODIFIERS[@]}"; do
      local cat="${m%%=*}" val="${m#*=}"
      [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
    done
  fi
  
  # Process custom modifiers
  if [[ "${ENABLE_CUSTOM_MODIFIERS}" == "true" ]]; then
    for m in "${CUSTOM_MODIFIERS[@]}"; do
      local cat="${m%%=*}" val="${m#*=}"
      [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
    done
  fi
  
  # Process custom arguments
  if [[ "${ENABLE_CUSTOM_ARGS}" == "true" ]]; then
    for arg in "${CUSTOM_ARGS[@]}"; do
      args+=( "${arg}" )
    done
  fi
  
  echo "${args[@]}"
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
      # Extract both files from backup to ensure both are restored
      tar -xzf "${last}" -C "${SAVEDIR}" "${WORLD_NAME}.db" "${WORLD_NAME}.fwl"
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
  local uptime="$1"
  local days=$((uptime / 86400))
  local hours=$((uptime % 86400 / 3600))
  local mins=$((uptime % 3600 / 60))
  local secs=$((uptime % 60))
  
  local result=""
  [[ $days -gt 0 ]] && result="${days}d "
  [[ $hours -gt 0 ]] && result="${result}${hours}h "
  [[ $mins -gt 0 ]] && result="${result}${mins}m "
  [[ $secs -gt 0 ]] && result="${result}${secs}s"
  
  echo "${result:-0s}"
}

count_connected_players() {
  if ! is_running; then echo "0"; return; fi
  
  # Try A2S query first (most accurate)
  if command -v a2s &> /dev/null; then
    local player_count
    player_count=$(a2s players "${SERVER_IP}:${PORT}" 2>/dev/null | grep -c "Player" || echo "0")
    echo "$player_count"
    return
  fi
  
  # Fallback to log parsing
  local log
  log="$(tail -n 500 "${LOGFILE}" 2>/dev/null || echo "")"
  local count
  count=$(echo "$log" | grep -c "Connected player" || echo "0")
  echo "$count"
}

get_join_code() {
  if ! is_running; then echo ""; return; fi
  local log; log="$(tail -n 200 "${LOGFILE}" 2>/dev/null || echo "")"
  echo "$log" | grep -oE "Join code: [0-9a-zA-Z]{6}" | cut -d' ' -f2 || echo ""
}

get_server_ip_from_logs() {
  if ! is_running; then echo ""; return; fi
  local log; log="$(tail -n 200 "${LOGFILE}" 2>/dev/null || echo "")"
  echo "$log" | grep -oE "Server IP: [0-9.]{7,15}" | cut -d' ' -f2 || echo ""
}

get_server_ip() {
  # Get server IP address
  local ip; ip="$(hostname -I 2>/dev/null | cut -d' ' -f1 || echo "")"
  [[ -n "${ip}" ]] && echo "${ip}" || echo "127.0.0.1"
}

# Enhanced monitoring function for external use
monitor_server() {
  local output_format="${1:-text}"  # text or json
  
  if [[ "${output_format}" == "json" ]]; then
    echo "{"
    echo "  \"status\": \"$(is_running && echo "running" || echo "stopped")\","
    echo "  \"players\": \"$(count_connected_players)\","
    echo "  \"server_name\": \"${SERVER_NAME}\","
    echo "  \"world\": \"${WORLD_NAME}\","
    echo "  \"port\": \"${PORT}\","
    echo "  \"public\": \"${PUBLIC}\""
    echo "}"
  else
    echo "Server Status:"
    echo "  Status: $(is_running && echo "Running" || echo "Stopped")"
    echo "  Players: $(count_connected_players)"
    echo "  Server: ${SERVER_NAME}"
    echo "  World: ${WORLD_NAME}"
    echo "  Port: ${PORT}"
  fi
}