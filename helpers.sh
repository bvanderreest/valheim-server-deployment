#!/usr/bin/env bash
# Valheim server manager — Helper functions

########################################
#               HELPERS                #
########################################

ensure_paths() { mkdir -p "${SAVEDIR}" "${LOG_DIR}" "${BACKUP_DIR}"; }

rotate_log() {
  if [[ -f "${LOGFILE}" && -s "${LOGFILE}" ]]; then
    local ts; ts="$(date +"%Y-%m-%d_%H-%M-%S")"
    local base="${LOGFILE%.log}"
    mv "${LOGFILE}" "${base}-${ts}.log"
    echo "[rotate_log] Previous log archived to ${base}-${ts}.log"
  fi
}


build_args() {
  # Check if modifiers.conf exists, if not, create it from the example
  local script_dir; script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ ! -f "${script_dir}/modifiers.conf" ]]; then
    if [[ -f "${script_dir}/modifiers.example.conf" ]]; then
      cp "${script_dir}/modifiers.example.conf" "${script_dir}/modifiers.conf"
      echo "Created modifiers.conf from modifiers.example.conf. Please customize settings in modifiers.conf." >&2
    else
      echo "Error: Neither modifiers.conf nor modifiers.example.conf found!" >&2
      exit 1
    fi
  fi
  
  source "${script_dir}/modifiers.conf"
  
  local args=()
  args+=( -nographics -batchmode )
  args+=( -name "${SERVER_NAME}" -port "${PORT}" -world "${WORLD_NAME}" -password "${PASSWORD}" )
  args+=( -public "${PUBLIC}" -savedir "${SAVEDIR}" -logFile "${LOGFILE}" )
  args+=( -saveinterval "${SAVE_INTERVAL}" -backups "${BACKUPS_KEEP}" -backupshort "${BACKUP_SHORT}" -backuplong "${BACKUP_LONG}" )
  [[ "${CROSSPLAY}" == "true" ]] && args+=( -crossplay )
  [[ -n "${PRESET}" ]] && args+=( -preset "${PRESET}" )
  
  # Process modifiers
  if [[ "${ENABLE_MODIFIERS}" == "true" ]]; then
    for m in "${MODIFIERS[@]}"; do
      local cat="${m%%=*}" val="${m#*=}"
      [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
    done
  fi

  # Process extra modifiers (modded servers / power users)
  if [[ "${ENABLE_EXTRA_MODIFIERS}" == "true" ]]; then
    for m in "${EXTRA_MODIFIERS[@]}"; do
      local cat="${m%%=*}" val="${m#*=}"
      [[ -n "${cat}" && -n "${val}" ]] && args+=( -modifier "${cat,,}" "${val,,}" )
    done
  fi

  # Process setkeys — supports both toggle keys ("nomap") and numeric keys ("EnemyDamage=200")
  for key in "${SETKEYS[@]}"; do
    if [[ "${key}" == *"="* ]]; then
      local k="${key%%=*}" v="${key#*=}"
      [[ -n "${k}" && -n "${v}" ]] && args+=( -setkey "${k}" "${v}" )
    else
      [[ -n "${key}" ]] && args+=( -setkey "${key}" )
    fi
  done

  # Process custom arguments
  if [[ "${ENABLE_CUSTOM_ARGS}" == "true" ]]; then
    for arg in "${CUSTOM_ARGS[@]}"; do
      args+=( "${arg}" )
    done
  fi
  
  printf '%s\n' "${args[@]}"
}

preflight_check() {
  local failed=0
  echo "[preflight] Checking shared library dependencies..."

  if [[ ! -x "${BINARY}" ]]; then
    echo "[preflight] ERROR: Binary not found or not executable: ${BINARY}" >&2
    return 1
  fi

  # Check server binary
  if ldd "${BINARY}" 2>&1 | grep -q "not found"; then
    echo "[preflight] WARNING: Missing libraries for ${BINARY}:" >&2
    ldd "${BINARY}" 2>&1 | grep "not found" >&2
    failed=1
  fi

  # Check plugin .so files (linux64/ Steam runtime plugins)
  while IFS= read -r -d '' sofile; do
    if ldd "${sofile}" 2>&1 | grep -q "not found"; then
      echo "[preflight] WARNING: Missing libraries for ${sofile}:" >&2
      ldd "${sofile}" 2>&1 | grep "not found" >&2
      failed=1
    fi
  done < <(find "${SERVER_DIR}/linux64" -maxdepth 1 -name "*.so" -print0 2>/dev/null)

  # When crossplay is enabled, verify the additional native libraries PlayFab needs.
  if [[ "${CROSSPLAY}" == "true" ]]; then
    echo "[preflight] Checking crossplay library dependencies..."
    local crossplay_missing=()
    ldconfig -p 2>/dev/null | grep -q "libatomic.so"  || crossplay_missing+=("libatomic1")
    ldconfig -p 2>/dev/null | grep -q "libpulse.so"   || crossplay_missing+=("libpulse0")
    if [[ ${#crossplay_missing[@]} -gt 0 ]]; then
      echo "[preflight] WARNING: Missing crossplay libraries: ${crossplay_missing[*]}" >&2
      echo "[preflight] Fix with: sudo apt install -y ${crossplay_missing[*]} libpulse-dev" >&2
      failed=1
    fi
  fi

  if [[ $failed -eq 0 ]]; then
    echo "[preflight] All library checks passed."
  else
    echo "[preflight] Some libraries are missing. Server may fail to start." >&2
    return 1
  fi
}

is_running() { [[ -f "${PIDFILE}" ]] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null; }

latest_backup() { find "${BACKUP_DIR}" -maxdepth 1 -name "world-${WORLD_NAME}-*.tar.gz" 2>/dev/null | sort -r | head -n 1; }

guard_world() {
  # If current world files are missing or zero-sized (common after power cut), restore the newest backup.
  local world_dir="${SAVEDIR}/worlds_local"
  local db="${world_dir}/${WORLD_NAME}.db"
  local fwl="${world_dir}/${WORLD_NAME}.fwl"
  if [[ ! -f "${db}" || ! -s "${db}" || ! -f "${fwl}" || ! -s "${fwl}" ]]; then
    local last; last="$(latest_backup || true)"
    if [[ -n "${last}" ]]; then
      echo "[guard] Damaged/missing world. Restoring from ${last}"
      mkdir -p "${world_dir}"
      if ! tar -xzf "${last}" -C "${world_dir}" "${WORLD_NAME}.db" "${WORLD_NAME}.fwl"; then
        echo "[guard] ERROR: Restore failed — backup may be corrupt. Manual intervention required." >&2
        exit 1
      fi
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
    local query_ip; query_ip="$(get_server_ip)"
    local player_count
    player_count=$(a2s players "${query_ip}:${PORT}" 2>/dev/null | grep -c "Player" || echo "0")
    echo "$player_count"
    return
  fi

  # Fallback: net count from log (peers connected minus disconnects)
  local log_tail
  log_tail="$(tail -n 2000 "${LOGFILE}" 2>/dev/null || echo "")"
  local connected disconnected net
  connected=$(echo "$log_tail" | grep -c "Server: New peer connected" || true)
  disconnected=$(echo "$log_tail" | grep -c "RPC_Disconnect" || true)
  net=$(( connected - disconnected ))
  echo "$(( net < 0 ? 0 : net ))"
}

get_connected_player_names() {
  if ! is_running; then echo ""; return; fi
  tail -n 2000 "${LOGFILE}" 2>/dev/null \
    | grep "Got character ZDOID from" \
    | grep -v " 0:0$" \
    | sed 's/.*Got character ZDOID from //; s/ *:.*$//' \
    | sed 's/[[:space:]]*$//' \
    | sort -u
}

get_join_code() {
  if ! is_running; then echo ""; return; fi
  local log; log="$(tail -n 200 "${LOGFILE}" 2>/dev/null || echo "")"
  echo "$log" | grep -oE "Join code: [0-9a-zA-Z]{6}" | tail -1 | cut -d' ' -f3 || echo ""
}

get_valheim_version() {
  grep -m1 "Valheim version:" "${LOGFILE}" 2>/dev/null \
    | sed 's/.*Valheim version: //' || echo ""
}

get_game_server_status() {
  if ! is_running; then echo ""; return; fi
  tail -n 500 "${LOGFILE}" 2>/dev/null \
    | grep "Game server" \
    | tail -1 \
    | sed 's/.*Game server //' || echo ""
}

get_last_save() {
  if ! is_running; then echo ""; return; fi
  grep "World saved" "${LOGFILE}" 2>/dev/null \
    | tail -1 \
    | grep -oE "[0-9]{2}/[0-9]{2}/[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}" || echo ""
}

get_server_ip() {
  local ip; ip="$(hostname -I 2>/dev/null | cut -d' ' -f1 || echo "")"
  [[ -n "${ip}" ]] && echo "${ip}" || echo "127.0.0.1"
}
