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

  # return, not exit — same trap as stop(): an exit here kills any caller.
  if is_running; then echo "Already running (PID $(cat "${PIDFILE}"))."; return 0; fi

  preflight_check

  # Verify server directory exists before attempting to cd
  if [[ ! -d "${SERVER_DIR}" ]]; then
    echo "Error: Server directory not found: ${SERVER_DIR}"
    echo "  Fix: sudo ./valheim-server-manager.sh deploy"
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

  "${BINARY}" "${ARGS[@]}" >> "${LOGFILE}" 2>&1 &
  echo $! > "${PIDFILE}"
  local pid; pid="$(cat "${PIDFILE}")"

  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║                  Valheim Server Starting                  ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  printf "  %-12s %s\n" "Server:"    "${SERVER_NAME}"
  printf "  %-12s %s\n" "World:"     "${WORLD_NAME}"
  printf "  %-12s %s\n" "Port:"      "${PORT}"
  printf "  %-12s %s\n" "Public:"    "$([[ "${PUBLIC}" == "1" ]] && echo 'Yes' || echo 'No')"
  printf "  %-12s %s\n" "Crossplay:" "${CROSSPLAY}"
  printf "  %-12s %s\n" "Save dir:"  "${SAVEDIR}"
  printf "  %-12s %s\n" "PID:"       "${pid}"
  printf "  %-12s %s\n" "Log:"       "${LOGFILE}"
  echo "───────────────────────────────────────────────────────────"

  # Milestone patterns fired by the Valheim server log in sequence.
  # Labels describe what was just ACHIEVED (shown after each milestone is confirmed).
  # "DungeonDB Start" marks world loading beginning — "DungeonDB done" does not appear in this Valheim build's log.
  # The crossplay join-code step is added only when CROSSPLAY=true.
  local -a ms_patterns=(
    "Initialize engine version"
    "Steam game server initialized"
    "DungeonDB Start"
    "Game server connected"
  )
  local -a ms_labels=(
    "Engine        "
    "Steam         "
    "World         "
    "Network       "
  )
  if [[ "${CROSSPLAY}" == "true" ]]; then
    ms_patterns+=("registered with join code")
    ms_labels+=("Crossplay     ")
  fi
  local total=${#ms_patterns[@]}
  local bar_width=20
  local bar_full=""
  for (( _i=0; _i<bar_width; _i++ )); do bar_full+="█"; done
  printf "  %-14s  [%s] 100%%\n" "Pre-flight" "${bar_full}"
  local step=0
  local spin_idx=0
  local spinners=('|' '/' '-' '\')
  # Configurable: a 1.0 world migration on a large world can far exceed the
  # old hard-coded 300s. Default is generous on purpose (#71).
  local timeout="${START_TIMEOUT:-900}"
  local elapsed=0
  local ready=0
  local last_log_size; last_log_size="$(log_size)"
  local stalled_for=0

  # Four-line display: bar line + 3 live log lines below it.
  # Subsequent ticks use ANSI cursor-up to redraw all four lines in place.
  printf "  Starting...     [%-${bar_width}s]   0%%\n  \n  \n  \n" ""

  while [[ $elapsed -lt $timeout ]]; do
    # Fail fast if the process died
    if ! kill -0 "${pid}" 2>/dev/null; then
      printf "\033[4A\033[2K\r  %-14s  [%-${bar_width}s] FAILED\n\033[2K\r\033[2K\r\033[2K\r" "Process exited" ""
      echo "───────────────────────────────────────────────────────────"
      echo "  The server process exited unexpectedly."
      echo "  Check logs: ./valheim-server-manager.sh logs"
      echo "  Common causes: missing Steam libs, bad .env config, port in use."
      echo "═══════════════════════════════════════════════════════════"
      rm -f "${PIDFILE}"
      exit 1
    fi

    # Advance through any newly reached milestones
    while [[ $step -lt $total ]] && grep -q "${ms_patterns[$step]}" "${LOGFILE}" 2>/dev/null; do
      step=$(( step + 1 ))
    done

    # Bar geometry
    local pct=$(( step * 100 / total ))
    local filled=$(( step * bar_width / total ))
    local bar=""
    for (( i=0; i<filled; i++ ));         do bar+="█"; done
    for (( i=filled; i<bar_width; i++ )); do bar+="░"; done

    # Label shows what was last confirmed (step-1), not what we're waiting for
    local label
    [[ $step -eq 0 ]] && label="Starting...   " || label="${ms_labels[$((step-1))]}"

    # Latest 3 meaningful log lines — strip timestamp, filter known Unity/Steam noise.
    # grep -v removes lines that are purely internal chatter with no operator value.
    local log_lines
    mapfile -t log_lines < <(tail -200 "${LOGFILE}" 2>/dev/null | grep -v \
      -e "Fallback handler could not load library" \
      -e "Unloading [0-9]* Unused" \
      -e "^\[Physics" \
      -e "^GfxDevice" \
      -e "^d3d" \
      -e "^Mono " \
      -e "^Desktop is" \
      -e "^Using GLFW" \
      | tail -3 \
      | sed 's|^[0-9][0-9]/[0-9][0-9]/[0-9]* [0-9][0-9]:[0-9][0-9]:[0-9][0-9]: ||' \
      | cut -c1-55 || true)
    # Pad to exactly 3 entries so printf always has values
    while [[ ${#log_lines[@]} -lt 3 ]]; do log_lines+=(""); done

    # AUTHORITATIVE readiness: the game port is bound by our PID. Log strings
    # are only a progress hint — 1.0 is a Unity 6 rebuild and any of them may
    # change, which must never turn a healthy server into a reported failure.
    if server_port_bound "${pid}"; then
      ready=1
      local rlabel="Ready         "
      [[ $step -gt 0 ]] && rlabel="${ms_labels[$((step-1))]}"
      printf "\033[4A\033[2K\r  %-14s  [%s] 100%%\n\033[2K\r\033[2K\r\033[2K\r" "${rlabel}" "${bar_full}"
      break
    fi

    if [[ $step -eq $total ]]; then
      printf "\033[4A\033[2K\r  %-14s  [%s] 100%%\n\033[2K\r\033[2K\r\033[2K\r" "${ms_labels[$((step-1))]}" "${bar}"
      ready=1
      break
    fi

    # Track whether the log is still advancing — used to tell "slow" from "hung".
    local cur_log_size; cur_log_size="$(log_size)"
    if [[ "${cur_log_size}" == "${last_log_size}" ]]; then
      stalled_for=$(( stalled_for + 1 ))
    else
      stalled_for=0
      last_log_size="${cur_log_size}"
    fi

    local spin="${spinners[$spin_idx]}"
    printf "\033[4A\033[2K\r  %-14s  [%s] %3d%% %s\n\033[2K  │ %.51s\n\033[2K  │ %.51s\n\033[2K  │ %.51s\n" \
      "${label}" "${bar}" "${pct}" "${spin}" \
      "${log_lines[0]}" "${log_lines[1]}" "${log_lines[2]}"
    spin_idx=$(( (spin_idx + 1) % ${#spinners[@]} ))
    sleep 1
    elapsed=$(( elapsed + 1 ))
  done

  if [[ ${ready} -ne 1 ]]; then
    # The old code called this FAILED and exited 1. That is wrong and dangerous:
    # the first boot after a major patch migrates the world in place, which on a
    # large world can take a very long time. Reporting failure invites the
    # operator to restart mid-migration — a reliable way to corrupt a world.
    if kill -0 "${pid}" 2>/dev/null; then
      printf "\033[4A\033[2K\r  %-14s  [%-${bar_width}s] STILL WORKING\n\033[2K\r\033[2K\r\033[2K\r" "In progress" ""
      echo "───────────────────────────────────────────────────────────"
      echo "  Server is STILL RUNNING and has not finished starting."
      if world_migration_in_progress; then
        echo "  A world upgrade/migration appears to be in progress."
      fi
      if [[ ${stalled_for} -ge 120 ]]; then
        echo "  ⚠ The log has not advanced for ${stalled_for}s — it may be stuck."
      else
        echo "  The log is still advancing, so it is working, just slow."
      fi
      echo ""
      echo "  ⚠ DO NOT restart or stop it now — interrupting a world migration"
      echo "    is one of the most reliable ways to corrupt a Valheim world."
      echo ""
      echo "  Watch it:  ./valheim-server-manager.sh logs"
      echo "  PID ${pid} is alive. Waited ${timeout}s (raise START_TIMEOUT to wait longer)."
      echo "═══════════════════════════════════════════════════════════"
      exit 0
    fi
    printf "\033[4A\033[2K\r  %-14s  [%-${bar_width}s] FAILED\n\033[2K\r\033[2K\r\033[2K\r" "Process gone" ""
    echo "───────────────────────────────────────────────────────────"
    echo "  The server process is no longer running."
    echo "  Check logs: ./valheim-server-manager.sh logs"
    echo "═══════════════════════════════════════════════════════════"
    rm -f "${PIDFILE}"
    exit 1
  fi

  echo "───────────────────────────────────────────────────────────"
  echo "  Status:      Started"

  # API startup as a final animated bar step
  if [[ "${API_ENABLED,,}" == "true" ]]; then
    local api_tmp; api_tmp=$(mktemp)
    "${SCRIPT_DIR}/api-manager.sh" start > "${api_tmp}" 2>&1 &
    local api_bg=$!
    local api_spin_idx=0
    printf "  %-14s  [%-${bar_width}s]  -- |" "API           " ""
    while kill -0 "${api_bg}" 2>/dev/null; do
      printf "\r  %-14s  [%-${bar_width}s]  -- %s" "API           " "" "${spinners[$api_spin_idx]}"
      api_spin_idx=$(( (api_spin_idx + 1) % ${#spinners[@]} ))
      sleep 1
    done
    wait "${api_bg}"
    local api_exit=$?
    if [[ $api_exit -eq 0 ]]; then
      printf "\r\033[2K  %-14s  [%s] 100%%\n" "API           " "${bar_full}"
    else
      local last_err; last_err=$(grep -i "error\|not found" "${api_tmp}" | tail -1)
      printf "\r\033[2K  %-14s  [%-${bar_width}s] FAILED\n" "API           " ""
      [[ -n "${last_err}" ]] && echo "  ${last_err}"
      echo "  Diagnose: ./api-manager.sh setup && ./api-manager.sh start"
    fi
    rm -f "${api_tmp}"
  fi

  echo "═══════════════════════════════════════════════════════════"
  echo "  Use './valheim-server-manager.sh logs' to follow output."
  echo "═══════════════════════════════════════════════════════════"
}

stop() {
  local api_pid_file="${SCRIPT_DIR}/.api.pid"
  if [[ -f "${api_pid_file}" ]] && kill -0 "$(cat "${api_pid_file}")" 2>/dev/null; then
    echo "[stop] Stopping API..."
    "${SCRIPT_DIR}/api-manager.sh" stop
  fi

  # `return`, NOT `exit`. restart() is `stop; sleep 2; start` — an `exit 0`
  # here terminates the whole script, so restarting a STOPPED server printed
  # "Server is not running." and never reached start(). The API answered 202
  # "Restart command accepted" and nothing happened.
  if ! is_running; then echo "Server is not running."; return 0; fi
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
  echo "API:"
  local api_pid_file="${SCRIPT_DIR}/.api.pid"
  if [[ "${API_ENABLED,,}" == "true" ]]; then
    if [[ -f "${api_pid_file}" ]] && kill -0 "$(cat "${api_pid_file}")" 2>/dev/null; then
      local api_pid; api_pid="$(cat "${api_pid_file}")"
      echo "  Status:         RUNNING (PID ${api_pid})"
      echo "  Address:        ${API_HOST:-127.0.0.1}:${API_PORT:-8080}"
    else
      echo "  Status:         STOPPED"
      echo "  Address:        ${API_HOST:-127.0.0.1}:${API_PORT:-8080}"
    fi
  else
    echo "  Status:         DISABLED (set API_ENABLED=true in .env to enable)"
  fi

  printf "\n"
  echo "═══════════════════════════════════════════════════════"
}

check_steam_connectivity() {
  # Uses the official SteamCMD API to verify connectivity before invoking SteamCMD.
  # This is more reliable than pinging generic CDN endpoints — a successful response
  # confirms Steam can serve the exact app data SteamCMD needs.
  local api_url="https://api.steamcmd.net/v1/info/896660"

  echo "[update] Checking Steam connectivity via api.steamcmd.net..."
  local response
  response="$(curl --silent --max-time 10 "${api_url}" 2>/dev/null)"

  if [[ -z "${response}" ]]; then
    echo "[update] Error: No response from api.steamcmd.net. Check your network and outbound TCP 443."
    return 1
  fi

  if grep -qE '"status"[[:space:]]*:[[:space:]]*"success"' <<< "${response}"; then
    echo "[update] Steam connectivity OK — app 896660 is reachable."
  else
    echo "[update] Warning: api.steamcmd.net responded but returned an unexpected status."
    echo "[update] Response: ${response:0:200}"
    echo "[update] Proceeding anyway — SteamCMD may still work."
  fi
  return 0
}

# Read the installed build id from the Steam app manifest.
installed_buildid() {
  local acf="${SERVER_DIR}/steamapps/appmanifest_896660.acf"
  [[ -f "${acf}" ]] || { echo "unknown"; return; }
  grep -oE '"buildid"[[:space:]]+"[0-9]+"' "${acf}" | grep -oE '[0-9]+' | head -1 || echo "unknown"
}

# Shared implementation for `update` and `rollback`.
# $1 = optional Steam beta branch (empty for the public branch)
_do_steam_update() {
  local branch="${1:-}"
  local start_after="${2:-auto}"

  if [[ "${USE_STEAMCMD_UPDATE}" != "true" ]]; then echo "SteamCMD update disabled."; return 0; fi
  if [[ ! -x "${STEAMCMD_BIN}" ]]; then
    echo "Error: SteamCMD not found at ${STEAMCMD_BIN}"
    echo "  Fix: sudo ./valheim-server-manager.sh deploy"
    exit 1
  fi

  local was_running=0
  if is_running; then was_running=1; echo "[update] Stopping…"; stop; fi

  # Free space: a major-version depot is a full re-download, and SteamCMD
  # stages before committing. Refuse rather than fill the disk mid-write.
  local avail_kb; avail_kb="$(df -Pk "${SERVER_DIR}" | awk 'NR==2{print $4}')"
  local need_kb=$(( 6 * 1024 * 1024 ))     # 6 GiB headroom
  if [[ "${avail_kb}" -lt "${need_kb}" ]]; then
    echo "[update] ERROR: only $(( avail_kb / 1024 ))MB free on ${SERVER_DIR}; want $(( need_kb / 1024 ))MB." >&2
    exit 1
  fi

  # BACKUP FIRST — non-negotiable. A Valheim world-format migration is one-way,
  # so an update without a verified backup has no way back (#74).
  echo "[update] Taking a pre-update backup…"
  if ! backup; then
    echo "[update] ABORTING: pre-update backup failed. Not touching the install." >&2
    exit 1
  fi

  rm -f "${HOME}/.steam/steam.pid" "${HOME}/.local/share/Steam/steam.pid" 2>/dev/null

  check_steam_connectivity || exit 1

  if [[ ! -w "${SERVER_DIR}" ]]; then
    echo "[update] Error: ${SERVER_DIR} is not writable by $(whoami)."
    echo "[update] Fix with: sudo chown -R $(whoami) \"${SERVER_DIR}\""
    exit 1
  fi

  local before; before="$(installed_buildid)"
  echo "[update] Installed build before: ${before}"

  local -a steam_args=( +force_install_dir "${SERVER_DIR}" +login "${STEAM_LOGIN}" +app_update 896660 )
  if [[ -n "${branch}" ]]; then
    echo "[update] Target branch: ${branch}"
    steam_args+=( -beta "${branch}" )
  fi
  steam_args+=( validate +quit )

  echo "[update] Updating app 896660 to ${SERVER_DIR}…"
  if ! "${STEAMCMD_BIN}" "${steam_args[@]}"; then
    echo "[update] Error: SteamCMD failed. Check network and that TCP 80/443 are open outbound." >&2
    echo "[update] Your pre-update backup is in ${BACKUP_DIR}." >&2
    exit 1
  fi

  local after; after="$(installed_buildid)"
  echo "[update] Installed build after:  ${after}"
  if [[ "${before}" == "${after}" ]]; then
    echo "[update] NOTE: build id did not change — you were already on this build."
  else
    echo "[update] Build changed ${before} → ${after}."
  fi

  # Restart unless told not to. The old code left the server stopped, which
  # silently took the server offline every time anyone ran an update (#74).
  case "${start_after}" in
    never) echo "[update] Done. Server left stopped (--no-start)." ;;
    always) echo "[update] Starting server…"; start ;;
    *)
      if [[ "${was_running}" -eq 1 ]]; then
        echo "[update] Restarting server (it was running before the update)…"
        start
      else
        echo "[update] Done. Server was not running before the update, leaving it stopped."
        echo "[update] Start it with: ./valheim-server-manager.sh start"
      fi
      ;;
  esac
}

update() {
  local start_after="auto"
  case "${1:-}" in
    --no-start) start_after="never" ;;
    --start)    start_after="always" ;;
  esac
  _do_steam_update "" "${start_after}"
}

# Roll the server back to the last stable build before Valheim 1.0.
# Verified against Steam app metadata for 896660:
#   default_pre1_0  buildid=21981590  pwdrequired=0  "Last stable build before 1.0"
# NOTE: a world already migrated to the 1.0 format will NOT load on this build.
# Restore a pre-1.0 world backup as well, or the rollback is useless.
rollback() {
  local branch="${ROLLBACK_BRANCH:-default_pre1_0}"
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║  ROLLBACK to pre-1.0 build (${branch})"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo "  ⚠ A world already opened by 1.0 will NOT load on this build."
  echo "    You must also restore a PRE-UPDATE world backup from:"
  echo "      ${BACKUP_DIR}"
  echo "  ⚠ Every player must switch their client to the same branch."
  echo ""
  read -r -p "  Continue with rollback? (y/N): " reply
  if [[ ! "${reply}" =~ ^[Yy]$ ]]; then echo "  Cancelled."; return 0; fi
  _do_steam_update "${branch}" "${1:-auto}"
}

backup() {
  echo "[backup] Creating backup for world: ${WORLD_NAME}"

  local world_dir="${SAVEDIR}/worlds_local"
  mkdir -p "${BACKUP_DIR}"

  # LAYOUT-AGNOSTIC (#73). The old version hard-coded "<World>.db" and
  # "<World>.fwl"; under the 1.0 chunked layout those may not exist, and the
  # old code treated that as a WARNING and returned — so the backup timer kept
  # reporting success while archiving nothing. A backup that cannot fail is
  # not a backup.
  if [[ ! -d "${world_dir}" ]]; then
    echo "[backup] ERROR: world directory does not exist: ${world_dir}" >&2
    return 1
  fi
  if ! world_has_data; then
    echo "[backup] ERROR: no data found for world '${WORLD_NAME}' in ${world_dir}" >&2
    echo "[backup] Refusing to write an empty backup." >&2
    return 1
  fi

  local layout; layout="$(world_layout)"
  local ts; ts="$(date +"%Y-%m-%d_%H-%M-%S")"
  local out="${BACKUP_DIR}/world-${WORLD_NAME}-${ts}.tar.gz"
  echo "[backup] Layout: ${layout}"
  echo "[backup] Creating ${out}…"

  # Archive the whole savedir: every world file in whatever layout, plus the
  # access lists, which are needed to reconstitute a working server.
  local items=("worlds_local")
  for f in adminlist.txt bannedlist.txt permittedlist.txt; do
    [[ -f "${SAVEDIR}/${f}" ]] && items+=("${f}")
  done

  if ! tar -czf "${out}" -C "${SAVEDIR}" "${items[@]}"; then
    echo "[backup] ERROR: tar failed." >&2
    rm -f "${out}"
    return 1
  fi

  # VERIFY. Creating a file is not the same as having a backup.
  if ! gzip -t "${out}" 2>/dev/null; then
    echo "[backup] ERROR: archive failed integrity check — removing it." >&2
    rm -f "${out}"
    return 1
  fi
  # Capture first: `tar ... | grep -q` fails under `set -o pipefail` because
  # grep -q closes the pipe on match and tar dies of SIGPIPE. That made this
  # check fail on every SUCCESSFUL backup. Caught on the live host.
  local listing; listing="$(tar -tzf "${out}" 2>/dev/null || true)"
  if ! grep -q "${WORLD_NAME}" <<< "${listing}"; then
    echo "[backup] ERROR: archive contains no files for '${WORLD_NAME}' — removing it." >&2
    rm -f "${out}"
    return 1
  fi

  local size; size="$(du -h "${out}" | cut -f1)"
  echo "[backup] OK — ${size}, integrity verified."

  # Retention. Timestamp format sorts lexicographically = chronologically.
  find "${BACKUP_DIR}" -maxdepth 1 -name "world-${WORLD_NAME}-*.tar.gz" \
    | sort -r | tail -n +$((BACKUPS_KEEP + 1)) | xargs -r rm --
  return 0
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
    apt-get install -y \
      lib32gcc-s1 lib32stdc++6 steamcmd curl wget unzip \
      ca-certificates libcurl4 libsdl2-2.0-0 \
      libpulse0 libpulse-dev libpulse-mainloop-glib0 \
      libatomic1
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
  
  # Determine the user who will run day-to-day commands (not root).
  # When deploy is run with sudo, SUDO_USER holds the real caller.
  local owner="${SUDO_USER:-$(whoami)}"

  # Create runtime directories (logs, worlds, backups, PID location) and
  # transfer ownership so start/stop/backup work without sudo.
  local pidfile_dir; pidfile_dir="$(dirname "${PIDFILE}")"
  echo "[deploy] Creating runtime directories under ${pidfile_dir}..."
  mkdir -p "${pidfile_dir}" "${LOG_DIR}" "${SAVEDIR}" "${BACKUP_DIR}"
  chown -R "${owner}" "${pidfile_dir}" "${LOG_DIR}" "${SAVEDIR}" "${BACKUP_DIR}"

  # Install Valheim server using SteamCMD with better error handling
  if ! "${steamcmd_bin}" +force_install_dir "${server_dir}" +login anonymous +app_update 896660 validate +quit; then
    echo "[deploy] Error: Failed to install Valheim server via SteamCMD"
    exit 1
  fi

  # Transfer server directory ownership to the real user after SteamCMD has
  # written all files (SteamCMD runs as root, so files would otherwise be root-owned).
  echo "[deploy] Setting ownership of ${server_dir} to ${owner}..."
  chown -R "${owner}" "${server_dir}"
  
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
  
  # Install systemd service and timer files with correct paths/user substituted.
  # The source files use __USER__ and __SCRIPT_DIR__ as placeholders.
  if [[ -d "/etc/systemd/system" ]]; then
    echo "[deploy] Installing systemd service and timer..."
    sed -e "s|__USER__|${owner}|g" \
        -e "s|__SCRIPT_DIR__|${SCRIPT_DIR}|g" \
        -e "s|__PIDFILE__|${PIDFILE}|g" \
        "${SCRIPT_DIR}/valheim-server.service" > /etc/systemd/system/valheim-server.service
    sed -e "s|__USER__|${owner}|g" \
        -e "s|__SCRIPT_DIR__|${SCRIPT_DIR}|g" \
        "${SCRIPT_DIR}/valheim-backup.service" > /etc/systemd/system/valheim-backup.service
    cp "${SCRIPT_DIR}/valheim-backup.timer" /etc/systemd/system/valheim-backup.timer
    sed -e "s|__USER__|${owner}|g" \
        -e "s|__SCRIPT_DIR__|${SCRIPT_DIR}|g" \
        "${SCRIPT_DIR}/api/valheim-api.service" > /etc/systemd/system/valheim-api.service
    systemctl daemon-reload
    echo "[deploy] Systemd units installed."
    echo "[deploy]   Server       : sudo systemctl enable --now valheim-server"
    echo "[deploy]                  (autostart on boot + restart on crash — #28)"
    echo "[deploy]   Backup timer : sudo systemctl enable --now valheim-backup.timer"
    echo "[deploy]   API (opt-in) : set API_ENABLED=true in .env first, then:"
    echo "[deploy]                  sudo systemctl enable --now valheim-api"
  fi

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
  echo "  backup     Archive the whole savedir to \$BACKUP_DIR (verified)"
  echo "  update     Back up, pull the latest build via SteamCMD, restart"
  echo "             --no-start  leave the server stopped afterwards"
  echo "             --start     always start afterwards"
  echo "  rollback   Revert to the last stable pre-1.0 build (default_pre1_0)"
  echo "  deploy     Install SteamCMD, dependencies, and server files"
  echo ""
  echo "  ── API Management ──────────────────────────────────────────"
  echo "  (Requires API_ENABLED=true in .env; co-managed by start/stop)"
  echo "  ./api-manager.sh [start|stop|restart|status|setup]"
  echo ""
  echo "  ── Examples ────────────────────────────────────────────────"
  echo "  sudo $0 deploy     # First-time install"
  echo "  $0 start           # Start the server"
  echo "  $0 stats           # Check status and storage"
  echo "  $0 backup          # Manual world backup (verified)"
  echo "  $0 update          # Safe update: backup -> update -> restart"
  echo "  $0 rollback        # Emergency: back to the pre-1.0 build"
  echo ""
  echo "  ── Env overrides ───────────────────────────────────────────"
  echo "  START_TIMEOUT=1800 $0 start   # wait longer for a slow migration"
  echo "  GUARD_WORLD=false  $0 start   # skip the world-restore guard"
  echo ""
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  stats) stats ;;
  logs) logs ;;
  update) update "${2:-}" ;;
  rollback) rollback "${2:-}" ;;
  backup) backup ;;
  deploy) deploy ;;
  *) usage; exit 1 ;;
esac