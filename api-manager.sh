#!/usr/bin/env bash
# Valheim Server Management API — Process Manager
# Manages the uvicorn process that serves the FastAPI application.
#
# Usage: ./api-manager.sh [start|stop|restart|status]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${SCRIPT_DIR}/.api.pid"

# Load .env for API_ENABLED, API_PORT, API_HOST (and all other vars)
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/.env"
    set +a
fi

API_ENABLED="${API_ENABLED:-false}"
API_PORT="${API_PORT:-8080}"
API_HOST="${API_HOST:-127.0.0.1}"

# ─── Helpers ──────────────────────────────────────────────────────────────────

find_uvicorn() {
    # Prefer the virtualenv in the repo root, fall back to system PATH
    for candidate in \
        "${SCRIPT_DIR}/.venv/bin/uvicorn" \
        "${SCRIPT_DIR}/venv/bin/uvicorn" \
        "$(command -v uvicorn 2>/dev/null || true)"; do
        if [[ -x "${candidate}" ]]; then
            echo "${candidate}"
            return 0
        fi
    done
    echo ""
}

is_api_running() {
    [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

get_uptime() {
    [[ -f "${PID_FILE}" ]] || { echo "0s"; return; }
    local pid; pid="$(cat "${PID_FILE}")"
    local start; start="$(stat -c %Y "/proc/${pid}" 2>/dev/null || echo 0)"
    [[ "${start}" -eq 0 ]] && { echo "unknown"; return; }
    local uptime=$(( $(date +%s) - start ))
    local days=$(( uptime / 86400 ))
    local hours=$(( uptime % 86400 / 3600 ))
    local mins=$(( uptime % 3600 / 60 ))
    local secs=$(( uptime % 60 ))
    local result=""
    [[ $days  -gt 0 ]] && result="${days}d "
    [[ $hours -gt 0 ]] && result="${result}${hours}h "
    [[ $mins  -gt 0 ]] && result="${result}${mins}m "
    [[ $secs  -gt 0 ]] && result="${result}${secs}s"
    echo "${result:-0s}"
}

# ─── Commands ─────────────────────────────────────────────────────────────────

cmd_setup() {
    # Ensure the Python virtualenv exists and api/requirements.txt is installed.
    # Called automatically by cmd_start and by systemd ExecStartPre.
    local python3_bin; python3_bin="$(command -v python3 2>/dev/null || true)"
    if [[ -z "${python3_bin}" ]]; then
        echo "ERROR: python3 not found. Install python3 to use the API." >&2
        exit 1
    fi
    local venv_dir="${SCRIPT_DIR}/.venv"
    if [[ ! -x "${venv_dir}/bin/python" ]]; then
        echo "[api] Creating virtualenv at ${venv_dir}..."
        "${python3_bin}" -m venv "${venv_dir}"
    fi
    echo "[api] Installing/verifying API dependencies..."
    "${venv_dir}/bin/pip" install --quiet -r "${SCRIPT_DIR}/api/requirements.txt"
    echo "[api] Dependencies ready."
}

cmd_start() {
    if [[ "${API_ENABLED,,}" != "true" ]]; then
        echo "ERROR: API is disabled. Set API_ENABLED=true in .env to enable it." >&2
        exit 1
    fi

    if is_api_running; then
        echo "API is already running (PID $(cat "${PID_FILE}"))."
        exit 0
    fi

    cmd_setup
    local uvicorn; uvicorn="$(find_uvicorn)"
    if [[ -z "${uvicorn}" ]]; then
        echo "ERROR: uvicorn not found after setup. Check api/requirements.txt." >&2
        exit 1
    fi

    echo "Starting API on ${API_HOST}:${API_PORT} ..."
    nohup "${uvicorn}" api.main:app \
        --host "${API_HOST}" \
        --port "${API_PORT}" \
        --workers 1 \
        --log-level info \
        --access-log \
        > "${SCRIPT_DIR}/.api.log" 2>&1 &

    local pid=$!
    echo "${pid}" > "${PID_FILE}"

    # Brief wait to confirm it stayed up
    sleep 2
    if kill -0 "${pid}" 2>/dev/null; then
        echo "API started (PID ${pid}). Listening on ${API_HOST}:${API_PORT}"
    else
        echo "ERROR: API process exited immediately. Check .api.log for details." >&2
        rm -f "${PID_FILE}"
        exit 1
    fi
}

cmd_stop() {
    if ! is_api_running; then
        echo "API is not running."
        exit 0
    fi

    local pid; pid="$(cat "${PID_FILE}")"
    echo "Stopping API (PID ${pid}) ..."
    kill -TERM "${pid}" 2>/dev/null || true

    local waited=0
    while kill -0 "${pid}" 2>/dev/null; do
        sleep 1
        (( waited++ ))
        if [[ ${waited} -ge 15 ]]; then
            echo "Process did not stop after 15s; sending SIGKILL ..."
            kill -KILL "${pid}" 2>/dev/null || true
            break
        fi
    done

    rm -f "${PID_FILE}"
    echo "API stopped."
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    echo "─────────────────────────────────────"
    echo " Valheim API Status"
    echo "─────────────────────────────────────"
    if is_api_running; then
        local pid; pid="$(cat "${PID_FILE}")"
        echo " Status  : RUNNING"
        echo " PID     : ${pid}"
        echo " Address : ${API_HOST}:${API_PORT}"
        echo " Uptime  : $(get_uptime)"
    else
        echo " Status  : STOPPED"
    fi
    echo " Enabled : ${API_ENABLED}"
    echo "─────────────────────────────────────"
}

# ─── Entry point ──────────────────────────────────────────────────────────────

case "${1:-}" in
    start)   cmd_start   ;;
    stop)    cmd_stop    ;;
    restart) cmd_restart ;;
    status)  cmd_status  ;;
    setup)   cmd_setup   ;;
    *)
        echo "Usage: $0 [start|stop|restart|status|setup]"
        exit 1
        ;;
esac
