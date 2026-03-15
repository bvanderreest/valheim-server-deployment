#!/usr/bin/env bash
# Valheim Server Backup Automation Script
# This script can be run manually or scheduled via cron or systemd

set -eo pipefail

# Source the main configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.conf"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check if server is running and backup if it is
backup_if_running() {
    if [ -f "${PIDFILE}" ]; then
        local pid
        pid=$(cat "${PIDFILE}")
        if kill -0 "$pid" 2>/dev/null; then
            log "Server is running (PID: $pid). Creating backup..."
            "${SCRIPT_DIR}/valheim-server-manager.sh" backup
            log "Backup completed."
        else
            log "PID file exists but process is not running. Removing stale PID file."
            rm -f "${PIDFILE}"
        fi
    else
        log "Server is not running. Creating backup anyway..."
        "${SCRIPT_DIR}/valheim-server-manager.sh" backup
        log "Backup completed."
    fi
}

# Main execution
main() {
    log "Starting automated backup process..."
    
    # Ensure backup directory exists
    mkdir -p "${BACKUP_DIR}"
    
    # Run backup
    backup_if_running
    
    # Clean up old backups (keep only the most recent ones)
    log "Cleaning up old backups..."
    cd "${BACKUP_DIR}"
    ls -1t world-"${WORLD_NAME}"-*.tar.gz | tail -n +${BACKUPS_KEEP} | xargs -r rm -f
    log "Backup cleanup completed."
    
    log "Automated backup process completed."
}

# Run main function
main "$@"