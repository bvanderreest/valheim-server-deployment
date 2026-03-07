# Valheim Server Management API

A FastAPI application that exposes the Valheim server's status and control commands over HTTP. Designed to be consumed by a centralised game server dashboard alongside APIs from other game servers (7 Days to Die, etc.).

## Security model

- All endpoints except `GET /health` require an `X-API-Key` header.
- Failed authentication attempts are rate-limited (5 per IP per 15 minutes → `429`).
- The API binds to `127.0.0.1` only; HTTPS is handled by a reverse proxy (nginx).
- The API will **not start** unless `API_ENABLED=true` is set in `.env`.

---

## Prerequisites

- Python 3.11+
- The Valheim server manager already deployed (`valheim-server-manager.sh` present)
- The API must run as the same OS user that manages the Valheim server (or a user with execute permission on `valheim-server-manager.sh` and read access to `LOGFILE` and `PIDFILE`)

---

## Installation

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r api/requirements.txt
```

---

## Configuration

All configuration lives in the same `.env` file used by the Valheim server scripts. Add or update these variables:

```bash
# Must be set to true to allow the API to start
API_ENABLED=true

# Network binding — loopback only is strongly recommended in production
API_HOST=127.0.0.1
API_PORT=8080

# Generate a key: python3 -c "import secrets; print(secrets.token_hex(32))"
# Multiple keys are comma-separated (useful for key rotation)
API_KEYS="your-key-here,optional-second-key"

# Dashboard origin(s) for CORS — comma-separated, or * for any
CORS_ORIGINS="https://dashboard.example.com,http://localhost:3000"

# Server identity returned in every response
SERVER_TYPE="valheim"
SERVER_LABEL="Lowood-AU"
```

The following existing `.env` variables are also read by the API:

| Variable | Used for |
|----------|----------|
| `LOG_DIR` | Locates the live server log (`LOG_DIR/valheim-server.log`) |
| `PIDFILE` | Checks whether the server process is running |
| `SERVER_NAME` | Returned in `/status` |
| `WORLD_NAME` | Returned in `/status` |
| `PORT` | Returned in `/status` |
| `CROSSPLAY` | Returned in `/status` |
| `PUBLIC` | Returned in `/status` |

---

## Managing the API process

Use `api-manager.sh` from the repository root:

```bash
./api-manager.sh start    # Start the API in the background
./api-manager.sh stop     # Stop it gracefully
./api-manager.sh restart  # Stop then start
./api-manager.sh status   # Show running state, PID, and uptime
```

Logs are written to `.api.log` in the repository root.

### Alternatively: systemd

Copy `api/valheim-api.service` to `/etc/systemd/system/` (edit the paths inside it first), then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now valheim-api
sudo journalctl -u valheim-api -f   # Follow logs
```

---

## Endpoints

### `GET /health` — No auth required

Lightweight check for uptime monitors.

```json
{ "status": "ok", "server_type": "valheim", "server_label": "Lowood-AU" }
```

### `GET /status`

Full server status.

```json
{
  "server_type": "valheim",
  "server_label": "Lowood-AU",
  "server_name": "Lowood-AU",
  "world_name": "CrowsNest",
  "running": true,
  "pid": 12345,
  "uptime_seconds": 3661,
  "uptime_human": "1h 1m 1s",
  "version": "0.217.46",
  "players": { "count": 2, "names": ["Alice", "Bob"] },
  "join_code": "ABC123",
  "server_ip": "192.168.1.100",
  "port": 2456,
  "crossplay": true,
  "public": true,
  "last_save": "03/06/2026 17:45:00"
}
```

### `POST /server/start` / `stop` / `restart` / `backup`

Action endpoints return `202 Accepted` immediately. The underlying manager script runs in a background thread.

```json
{ "accepted": true, "message": "Start command accepted. Check /status for progress." }
```

- `start`: returns `409` if already running
- `stop`: returns `409` if not running
- `backup`: returns `409` if not running

### `GET /logs?lines=100`

Returns the last N lines of the server log (1–5000, default 100).

### `GET /logs/stream`

Server-Sent Events stream of the live log. Connect with:

```bash
curl -N -H "X-API-Key: your-key" http://127.0.0.1:8080/logs/stream
```

---

## Example usage

```bash
KEY="your-api-key-here"
BASE="http://127.0.0.1:8080"

# Health check (no key needed)
curl "${BASE}/health"

# Server status
curl -H "X-API-Key: ${KEY}" "${BASE}/status"

# Start the server
curl -X POST -H "X-API-Key: ${KEY}" "${BASE}/server/start"

# Last 200 log lines
curl -H "X-API-Key: ${KEY}" "${BASE}/logs?lines=200"

# Live log stream
curl -N -H "X-API-Key: ${KEY}" "${BASE}/logs/stream"
```

---

## nginx reverse proxy (HTTPS)

Run the API on loopback only and let nginx terminate SSL:

```nginx
server {
    listen 443 ssl;
    server_name api.yourserver.com;

    ssl_certificate     /etc/letsencrypt/live/api.yourserver.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourserver.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Required for Server-Sent Events (/logs/stream)
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}

server {
    listen 80;
    server_name api.yourserver.com;
    return 301 https://$host$request_uri;
}
```

> **Note**: `proxy_set_header X-Real-IP $remote_addr` is required for the rate limiter to see the real client IP rather than `127.0.0.1`.

---

## Adapting for other game servers

Each game server gets its own copy of the `api/` directory. Only two files need changing:

1. **`api/config.py`** — update default paths (`log_dir`, `pidfile`) and the manager script name
2. **`api/routes/server.py`** — update the log-parsing patterns (`_get_player_info`, `_get_version`, `_get_join_code`, `_get_last_save`) to match the new game's log format

The response shapes (`StatusResponse`, `ActionResponse`, etc.) remain identical so the dashboard receives a consistent structure from all servers.

---

## Notes

- **Single worker only**: `api-manager.sh` and the systemd unit both use `--workers 1`. The in-memory rate limiter (`auth.py`) is not shared across processes. If you ever need multiple workers, replace it with a Redis-backed store.
- **API docs disabled**: The `/docs` and `/redoc` endpoints are disabled in production (`main.py`). To enable them locally, comment out the `docs_url=None, redoc_url=None` lines.
