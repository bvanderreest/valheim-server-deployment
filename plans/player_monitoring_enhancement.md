# Enhanced Player Monitoring for Valheim Server Manager

## Problem Statement
The current player counting implementation in the Valheim server manager uses `grep -c "Connected player"` on the last 200 lines of the log file. This approach has several limitations:
- Inaccurate player counts, often showing 0 even when players are connected
- May miss players who connect/disconnect rapidly
- Relies on log format that may change
- Doesn't provide real-time accurate player information

## Proposed Solution

### 1. Multi-Method Player Counting
Implement a hybrid approach that uses multiple methods to determine player count:
- Primary: Steam Query Protocol (A2S) for real-time accurate count
- Secondary: Log-based counting as fallback
- Tertiary: Process-based counting for edge cases

### 2. Enhanced Stats Command
Modify the stats command to:
- Use A2S protocol for accurate player count
- Include additional server information
- Provide better error handling and fallbacks
- Show player list when available

### 3. Monitoring Script
Create a monitoring script that:
- Can be run independently for player count
- Integrates with existing monitoring systems
- Provides JSON output for easy parsing
- Supports multiple server instances

## Implementation Details

### A2S Protocol Integration
Use Python's `python-valve` library or similar to query the server using A2S protocol:
```bash
# Example using a2s command line tool
a2s info <server_ip>:<port>
a2s players <server_ip>:<port>
```

### Improved count_connected_players Function
Replace current implementation in `helpers.sh`:
```bash
count_connected_players() {
    if ! is_running; then echo "0"; return; fi
    
    # Try A2S query first (most accurate)
    if command -v a2s &> /dev/null; then
        local player_count=$(a2s players "${SERVER_IP}:${PORT}" 2>/dev/null | grep -c "Player")
        echo "$player_count"
        return
    fi
    
    # Fallback to log parsing
    local log; log="$(tail -n 500 "${LOGFILE}" 2>/dev/null || echo "")"
    local count=$(echo "$log" | grep -c "Connected player" || echo "0")
    echo "$count"
}
```

### Enhanced Stats Command
Update the stats command in `valheim-server-manager.sh`:
```bash
stats() {
    echo "Server Status:"
    echo "================"
    echo "Status:           $(is_running && echo "Running" || echo "Stopped")"
    echo "Server:           ${SERVER_NAME}"
    echo "World:            ${WORLD_NAME}"
    echo "Connected:        $(count_connected_players) player(s)"
    
    # Add additional server info
    if command -v a2s &> /dev/null && is_running; then
        echo "Server Info:"
        echo "  Players:        $(a2s players "${SERVER_IP}:${PORT}" 2>/dev/null | grep -c "Player" || echo "N/A")"
        echo "  Server Name:    $(a2s info "${SERVER_IP}:${PORT}" 2>/dev/null | grep "name" | cut -d: -f2- | xargs || echo "N/A")"
    fi
}
```

## Benefits
1. **Accurate Player Counting**: Real-time data from A2S protocol
2. **Reliability**: Fallback mechanisms when A2S is unavailable
3. **Enhanced Monitoring**: Additional server information in stats
4. **Better Integration**: JSON output for monitoring systems
5. **Improved User Experience**: More accurate status information

## Implementation Steps
1. Add A2S query capability to the monitoring system
2. Update `count_connected_players` function with fallback logic
3. Enhance stats command output
4. Create monitoring script for external use
5. Update documentation