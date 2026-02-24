#!/usr/bin/env bash
# Valheim Server Monitor
# Standalone script for monitoring Valheim server player counts and status

set -eo pipefail

# Source configuration and helpers
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.conf"
source "${SCRIPT_DIR}/helpers.sh"

########################################
#               COMMANDS               #
######################################

monitor() {
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

# Main execution
case "${1:-}" in
  monitor) monitor "${2:-text}" ;;
  *) echo "Usage: $0 {monitor [text|json]}"; exit 1 ;;
esac