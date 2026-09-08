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
  # Reference: libatomic.so.1, libpulse.so.0, libpulse-simple.so.0,
  #            libpulse-mainloop-glib.so.0 (lloesche/valheim-server-docker).
  if [[ "${CROSSPLAY}" == "true" ]]; then
    echo "[preflight] Checking crossplay library dependencies..."
    local crossplay_missing=()
    ldconfig -p 2>/dev/null | grep -q "libatomic.so"              || crossplay_missing+=("libatomic1")
    ldconfig -p 2>/dev/null | grep -q "libpulse.so"               || crossplay_missing+=("libpulse0")
    ldconfig -p 2>/dev/null | grep -q "libpulse-mainloop-glib.so" || crossplay_missing+=("libpulse-mainloop-glib0")
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

# ─── Save-layout awareness (Valheim 1.0 chunked saves) ────────────────────────
# Valheim 0.221.13 replaced the flat "<World>.db + <World>.fwl" pair with a
# per-world FOLDER of chunked files. That build never reached the live branch,
# so 1.0 (9 Sep 2026) is where it is expected to land. Nothing below assumes
# which layout is in use — it detects, and refuses to act destructively when
# it cannot positively identify a damaged world.

# Echoes: flat | chunked | none
world_layout() {
  local world_dir="${SAVEDIR}/worlds_local"
  local db="${world_dir}/${WORLD_NAME}.db"

  if [[ -f "${db}" ]]; then echo "flat"; return; fi
  # A directory named after the world, holding anything at all, is the
  # chunked layout. Match loosely on purpose: the exact 1.0 on-disk shape is
  # not published, and guessing it wrongly must not cause a restore.
  if [[ -d "${world_dir}/${WORLD_NAME}" ]] && \
     [[ -n "$(ls -A "${world_dir}/${WORLD_NAME}" 2>/dev/null)" ]]; then
    echo "chunked"; return
  fi
  echo "none"
}

# True when ANY file in worlds_local belongs to this world, in any layout.
# Deliberately broad — this is the "do not destroy it" test, so a false
# positive (declining to restore) is always safer than a false negative.
world_has_data() {
  local world_dir="${SAVEDIR}/worlds_local"
  [[ -d "${world_dir}" ]] || return 1
  find "${world_dir}" -maxdepth 1 -name "${WORLD_NAME}*" \
       \( -type f -size +0c -o -type d \) 2>/dev/null | grep -q . 
}

guard_world() {
  # Opt-out for the 1.0 cutover, or any time the operator is doing something
  # deliberate with the save files.
  if [[ "${GUARD_WORLD,,}" == "false" ]]; then
    echo "[guard] Disabled via GUARD_WORLD=false — skipping world restore check."
    return 0
  fi

  local world_dir="${SAVEDIR}/worlds_local"
  local layout; layout="$(world_layout)"

  case "${layout}" in
    chunked)
      # 1.0 folder layout present and non-empty. The legacy .db/.fwl are
      # SUPPOSED to be absent here. Restoring would be catastrophic.
      echo "[guard] Chunked (1.0) save layout detected — world present, no action."
      return 0
      ;;
    flat)
      local db="${world_dir}/${WORLD_NAME}.db"
      local fwl="${world_dir}/${WORLD_NAME}.fwl"
      if [[ -s "${db}" && -s "${fwl}" ]]; then
        return 0                      # healthy flat world
      fi
      echo "[guard] Flat save layout with a missing/empty .db or .fwl — world looks damaged."
      ;;
    none)
      if world_has_data; then
        # Files matching the world exist but match no layout we recognise.
        # This is exactly the case where the old guard destroyed data.
        echo "[guard] Unrecognised save layout, but world data IS present." >&2
        echo "[guard] Refusing to restore — that would risk overwriting a good world." >&2
        echo "[guard] Inspect manually: ${world_dir}" >&2
        return 0
      fi
      echo "[guard] No world data found for '${WORLD_NAME}'."
      ;;
  esac

  # Only reached for: damaged flat world, or genuinely nothing on disk.
  local last; last="$(latest_backup || true)"
  if [[ -z "${last}" ]]; then
    echo "[guard] No backups found; starting with current files (if any)."
    return 0
  fi

  echo "[guard] Restoring from ${last}"
  mkdir -p "${world_dir}"

  # Archives come in two shapes and the extraction target differs:
  #   current  — contains "worlds_local/..."  -> extract into $SAVEDIR
  #   legacy   — bare "<World>.db" at root    -> extract into $SAVEDIR/worlds_local
  # Getting this wrong silently puts the world in the wrong directory, which
  # looks like a successful restore and isn't. (Caught by the guard tests.)
  local dest
  if tar -tzf "${last}" 2>/dev/null | grep -qE "^(\./)?worlds_local/"; then
    dest="${SAVEDIR}"
  else
    dest="${world_dir}"
  fi

  if ! tar -xzf "${last}" -C "${dest}"; then
    echo "[guard] ERROR: Restore failed — backup may be corrupt. Manual intervention required." >&2
    exit 1
  fi

  # Prove the restore actually produced a world, rather than assuming it did.
  if ! world_has_data; then
    echo "[guard] ERROR: restore completed but no world data is present." >&2
    echo "[guard] Archive: ${last} (extracted to ${dest})" >&2
    exit 1
  fi
  echo "[guard] Restore complete (extracted to ${dest})."
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
  echo "$log" | grep -oE "Join code: [0-9a-zA-Z]{4,16}" | tail -1 | awk '{print $3}' || echo ""
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

# ─── Readiness / liveness ─────────────────────────────────────────────────────
# A log-string grep is a fragile readiness test: 1.0 is a Unity 6 rebuild and
# any of those strings may change (one already did — "DungeonDB done" never
# fires). These check the things that are true regardless of log wording.

# True when the Valheim UDP game port is actually bound by our process.
# This is the authoritative "the server is up" signal.
server_port_bound() {
  local pid="${1:-}"
  [[ -n "${pid}" ]] || return 1
  # ss is in iproute2 and always present on Ubuntu; fall back to /proc if not.
  if command -v ss >/dev/null 2>&1; then
    ss -lunp 2>/dev/null | grep -q ":${PORT}\b.*pid=${pid}\b" && return 0
    # Some ss builds omit pid without root — fall back to "port is bound at all"
    ss -lun 2>/dev/null | grep -q ":${PORT}\b" && return 0
  fi
  return 1
}

# Size of the log file, for detecting whether startup is still progressing.
log_size() { stat -c %s "${LOGFILE}" 2>/dev/null || echo 0; }

# True when the log mentions an in-progress world upgrade/migration. Matched
# loosely because the 1.0 wording is unknown.
world_migration_in_progress() {
  tail -n 50 "${LOGFILE}" 2>/dev/null \
    | grep -qiE "upgrad|migrat|convert|chunk|rebuild.*world|world.*rebuild"
}

# Escape a string for safe embedding inside a JSON double-quoted value.
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"   # backslash → \\
  s="${s//\"/\\\"}"   # " → \"
  s="${s//$'\n'/\\n}" # newline → \n
  s="${s//$'\r'/\\r}" # carriage return → \r
  s="${s//$'\t'/\\t}" # tab → \t
  printf '%s' "${s}"
}
