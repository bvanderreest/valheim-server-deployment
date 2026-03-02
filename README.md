# 🏰 Valheim Server Deployment & Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/your-repo/valheim-server-deployment/blob/main/LICENSE)
[![Gitea](https://img.shields.io/badge/Hosted-Gitea-blue)](https://your-gitea-url.com/your-repo/valheim-server-deployment)
[![Valheim](https://img.shields.io/badge/Valheim-Server-orange)](https://www.valheimgame.com/)

A complete, robust, and user-friendly deployment solution for running your own **Valheim** dedicated server with automated backup functionality and advanced management features.

## 🎮 Server Configuration

This deployment is configured for:
- **Server Name**: [Your Server Name]
- **World Name**: [Your World Name]
- **Port**: 2456
- **Public**: Yes
- **Crossplay**: Enabled
- **Difficulty**: Easy (with custom modifiers)
- **Backup Retention**: 12 backups
- **Save Interval**: 5 minutes

## 📦 Requirements

Before you begin, ensure you have:

- **Linux** (Ubuntu/Debian/CentOS recommended)
- **Bash 4+**
- **curl**
- **tar**
- **pv** (optional, for progress indication during backup)
- **systemd** (for automated backups)
- **SteamCMD** (for server updates)

## 🎮 Installing Valheim Server via SteamCMD

Before you can run your Valheim server, you need to install the server files using SteamCMD. Follow these steps:

### 1. Install SteamCMD

**On Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install steamcmd
```

**On CentOS/RHEL/Fedora:**
```bash
sudo dnf install steamcmd
```

### 2. Create SteamCMD Directory

```bash
mkdir -p ~/steamcmd
cd ~/steamcmd
```

### 3. Download and Run SteamCMD

```bash
# Download SteamCMD
wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz

# Extract the archive
tar -xvzf steamcmd_linux.tar.gz

# Run SteamCMD
./steamcmd.sh +login anonymous +quit
```

### 4. Install Valheim Server

```bash
# Install Valheim server files
./steamcmd.sh +login anonymous +force_install_dir ~/valheim +app_update 896660 validate +quit

# Verify installation
ls -la ~/valheim
```

### 5. Configure SteamCMD Path

Update your `config.conf` file with the correct SteamCMD path:
```bash
STEAMCMD_BIN="/home/yourusername/steamcmd/steamcmd.sh"
```

> **Note**: The server will automatically update using SteamCMD if `USE_STEAMCMD_UPDATE=true` is set in `config.conf`.

## 🚀 Features

- **Complete Server Management** - Start, stop, restart, update, and monitor your Valheim server
- **Automated Backup System** - Daily backups with systemd timer integration
- **Smart Backup Management** - Automatic cleanup of old backups with configurable retention
- **Join Code Extraction** - Automatically extract and display your server's join code
- **Player Tracking** - Real-time connected players monitoring
- **Uptime Monitoring** - Track server uptime and performance metrics
- **Power Loss Resilience** - Automatically recovers from unexpected shutdowns
- **SteamCMD Integration** - Easy server updates with SteamCMD
- **Crossplay Support** - Enable crossplay for your server
- **Customizable World Settings** - Configure server name, port, password, and more

## 📦 Requirements

Before you begin, ensure you have:

- **Linux** (Ubuntu/Debian/CentOS recommended)
- **Bash 4+**
- **curl**
- **tar**
- **pv** (optional, for progress indication during backup)
- **systemd** (for automated backups)
- **SteamCMD** (for server updates)

## 🎮 Installing Valheim Server via SteamCMD

Before you can run your Valheim server, you need to install the server files using SteamCMD. Follow these steps:

### 1. Install SteamCMD

**On Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install steamcmd
```

**On CentOS/RHEL/Fedora:**
```bash
sudo dnf install steamcmd
```

### 2. Create SteamCMD Directory

```bash
mkdir -p ~/steamcmd
cd ~/steamcmd
```

### 3. Download and Run SteamCMD

```bash
# Download SteamCMD
wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz

# Extract the archive
tar -xvzf steamcmd_linux.tar.gz

# Run SteamCMD
./steamcmd.sh +login anonymous +quit
```

### 4. Install Valheim Server

```bash
# Install Valheim server files
./steamcmd.sh +login anonymous +force_install_dir ~/valheim +app_update 896660 validate +quit

# Verify installation
ls -la ~/valheim
```

### 5. Configure SteamCMD Path

Update your `config.conf` file with the correct SteamCMD path:
```bash
STEAMCMD_BIN="/home/yourusername/steamcmd/steamcmd.sh"
```

> **Note**: The server will automatically update using SteamCMD if `USE_STEAMCMD_UPDATE=true` is set in `config.conf`.

## 🛠️ Installation & Setup

### 1. Clone the Repository

```bash
git clone https://your-gitea-url.com/your-repo/valheim-server-deployment.git
cd valheim-server-deployment
```

### 2. Configure Your Server

Edit `config.conf` to set your server parameters:

```bash
# Server configuration
SERVER_NAME="[Your Server Name]"
WORLD_NAME="[Your World Name]"
PASSWORD="[Your Server Password]"
PORT=2456
PUBLIC=1
CROSSPLAY=true

# SteamCMD settings (for updates)
STEAM_LOGIN="anonymous"
USE_STEAMCMD_UPDATE=true
STEAMCMD_BIN="/usr/games/steamcmd"

# Server paths
SERVER_DIR="/home/valheim/valheim"
BINARY="${SERVER_DIR}/valheim_server.x86_64"
SAVEDIR="/srv/valheim/worlds"
LOG_DIR="/srv/valheim/logs"
LOGFILE="${LOG_DIR}/valheim-server.log"
PIDFILE="/srv/valheim/valheim.pid"
BACKUP_DIR="/srv/valheim/backups"

# Backup settings
BACKUPS_KEEP=12
BACKUP_SHORT=900
BACKUP_LONG=3600

# Advanced settings
SAVE_INTERVAL=300
MODIFIERS=()
PRESET="easy"
SETKEYS=()
```

### 3. Set Up Automated Backups

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

## 🎮 Usage Commands

### Server Management

```bash
# Start the server
./valheim-server-manager.sh start

# Stop the server
./valheim-server-manager.sh stop

# Restart the server
./valheim-server-manager.sh restart

# Show server statistics
./valheim-server-manager.sh stats

# View server logs
./valheim-server-manager.sh logs

# Update the server
./valheim-server-manager.sh update

# Create a manual backup
./valheim-server-manager.sh backup
```

### Server Status Example

```bash
$ ./valheim-server-manager.sh stats
═══════════════════════════════════════════════════════
  Valheim Server Stats — [Your Server Name]
═══════════════════════════════════════════════════════

Status:           RUNNING (PID 12345)
Uptime:           2h 30m

World:            [Your World Name]
Connected:        3 player(s)

Connect:
  Join Code:      123456
  Server:         192.168.1.100
  Password:       [Your Server Password]

Configuration:
  Public:         Yes
  Crossplay:      true

Storage:
  World DB:       12.5M (/srv/valheim/worlds/[Your World Name].db)
  Backups:        3 file(s)

═══════════════════════════════════════════════════════
```

## 📦 Backup System

### Automated Backups

The backup automation system:
- Creates backups daily using systemd timer
- Keeps only the most recent backups (configurable)
- Works with running or stopped servers
- Automatically cleans up old backups
- Shows progress indication during backup creation

### Manual Backups

To create a backup manually:
```bash
./valheim-server-manager.sh backup
```

### Backup Retention

Configure backup retention in `config.conf`:
```bash
BACKUPS_KEEP=7    # Keep 7 most recent backups
BACKUP_SHORT=1    # Create short backup daily
BACKUP_LONG=7     # Create long backup weekly
```

## 🛡️ Advanced Features

### Crossplay Support

Enable crossplay by setting `CROSSPLAY=true` in `config.conf` to allow players from different platforms to join your server.

### Modifiers Configuration

This deployment uses custom server modifiers:
```bash
MODIFIERS=(
  "Combat=[difficulty]"
  "DeathPenalty=[penalty]"
  "Resources=[amount]"
  "Raids=[frequency]"
)
```

### Custom Presets

This deployment uses the "easy" preset with custom modifiers:
```bash
PRESET="easy"
```

### Server Settings

Configure server settings using SETKEYS:
```bash
SETKEYS=()
```

## 📊 Monitoring & Troubleshooting

### Check Server Status

```bash
./valheim-server-manager.sh stats
```

### View Logs

```bash
./valheim-server-manager.sh logs
```

### Server Health Check

The system automatically:
- Checks if the server is running
- Tracks connected players
- Monitors server uptime
- Recovers from power loss
- Extracts join codes from logs

### Common Issues

1. **Server won't start**: Check that SteamCMD is properly installed and the server directory has correct permissions
2. **Backup fails**: Ensure backup directory has sufficient disk space and correct permissions
3. **Join code not showing**: Wait for server to fully start and check logs for connection messages
4. **Permission denied**: Make sure all scripts are executable (`chmod +x *.sh`)

## 📁 File Structure

```
valheim-server-deployment/
├── config.conf              # Server configuration
├── valheim-server-manager.sh # Main server manager script
├── helpers.sh               # Helper functions
├── backup-automation.sh     # Backup automation script
├── valheim-backup.service   # Systemd service for backups
├── valheim-backup.timer     # Systemd timer for backups
├── README.md                # This file
└── README_MODIFIERS.md      # Modifier documentation
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Thanks to the Valheim community for their support
- Inspired by various server deployment scripts and best practices
- Uses SteamCMD for server updates

## 🎮 Valheim Logo

![Valheim Logo](https://upload.wikimedia.org/wikipedia/en/4/4d/Valheim_logo.png)

*Valheim Server Deployment Project*