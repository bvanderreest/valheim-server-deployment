# Valheim Server Deployment

This is a complete deployment script for a Valheim dedicated server with automated backup functionality.

## Features

- Server management (start, stop, restart, stats, logs, update, backup)
- Automated backup system with systemd timer
- Join code extraction from server logs
- Connected players tracking

## Setup Instructions

### 1. Configure the server

Edit `config.conf` to set your server parameters:

```bash
# Server configuration
SERVER_NAME="My Valheim Server"
WORLD_NAME="MyWorld"
PASSWORD="serverpassword"
PORT=2456
PUBLIC=1
CROSSPLAY=true
```

### 2. Set up automated backups

To enable automated backups using systemd timers:

```bash
# Copy the service and timer files to systemd directory
sudo cp valheim-backup.service /etc/systemd/system/
sudo cp valheim-backup.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the timer
sudo systemctl enable valheim-backup.timer
sudo systemctl start valheim-backup.timer

# Check status
sudo systemctl status valheim-backup.timer
```

### 3. Manual backup

To create a backup manually:

```bash
./valheim-server-manager.sh backup
```

### 4. Check server status

```bash
./valheim-server-manager.sh stats
```

## Functions

### Server Management
- `start` - Start the server
- `stop` - Stop the server
- `restart` - Restart the server
- `stats` - Show server statistics including join code
- `logs` - Show server logs
- `update` - Update the server
- `backup` - Create a backup

### Backup Automation
The backup automation system:
- Creates backups daily using systemd timer
- Keeps only the most recent backups (configurable)
- Works with running or stopped servers
- Automatically cleans up old backups

## Join Code Extraction

The `get_join_code()` function in `helpers.sh` extracts the join code from server logs. The join code appears in logs like:
```
Session MyWorld with join code 123456 and IP 192.168.1.100:2456 is active
```

## Connected Players Tracking

The `count_connected_players()` function tracks connected players by parsing server logs for connection/disconnection events.

## Requirements

- Bash 4+
- curl
- tar
- pv (optional, for progress indication during backup)
- systemd (for automated backups)