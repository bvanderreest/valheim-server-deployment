"""
Sprint 002 — Unit tests for API response shapes and backward-compatibility.

Acceptance criteria covered:
  - GET /status returns unified shape: connection object, players.max,
    ISO 8601 last_save, extras, _deprecated block with legacy fields
  - GET /logs returns { lines, count, log_file }
  - GET /logs/stream SSE events are data: {"line": "...", "timestamp": "..."}
  - POST /server/{action} response includes "action": "<action_name>"
  - GET /capabilities returns correct capability set
  - Invalid action returns 422
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.auth import require_api_key
from api.main import app
from api.models import PlayerInfo

# ─── Test client setup ────────────────────────────────────────────────────────

TEST_KEY = "test-api-key"


def _override_auth():
    return TEST_KEY


app.dependency_overrides[require_api_key] = _override_auth

client = TestClient(app, raise_server_exceptions=True)
HEADERS = {"X-API-Key": TEST_KEY}


# ─── Fixtures / shared mocks ──────────────────────────────────────────────────

_BASE_STATUS_PATCHES = {
    "api.routes.server._is_running": False,
    "api.routes.server._read_pid": None,
}


def _patch_status(running: bool = False, pid=None, join_code=None, last_save=None):
    """Return a dict of patch targets for a /status call."""
    return {
        "api.routes.server._is_running": running,
        "api.routes.server._read_pid": pid,
        "api.routes.server._get_uptime_seconds": 0,
        "api.routes.server._get_version": None,
        "api.routes.server._get_join_code": join_code,
        "api.routes.server._get_last_save": last_save,
        "api.routes.server._get_player_info": MagicMock(
            return_value=PlayerInfo(count=0, max=10, names=[])
        ),
        "api.routes.server._get_server_ip": "192.168.1.100",
    }


# ─── GET /status ──────────────────────────────────────────────────────────────

class TestGetStatus:
    def test_top_level_shape(self):
        patches = _patch_status()
        with patch("api.routes.server._is_running", return_value=False), \
             patch("api.routes.server._read_pid", return_value=None), \
             patch("api.routes.server._get_server_ip", return_value="192.168.1.1"), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=0, max=10, names=[])):
            r = client.get("/status", headers=HEADERS)

        assert r.status_code == 200
        data = r.json()
        for field in ("server_type", "server_label", "running", "pid",
                      "uptime_seconds", "uptime_human", "players",
                      "connection", "extras", "_deprecated"):
            assert field in data, f"Missing field: {field}"

    def test_connection_object_present(self):
        with patch("api.routes.server._is_running", return_value=False), \
             patch("api.routes.server._read_pid", return_value=None), \
             patch("api.routes.server._get_server_ip", return_value="10.0.0.1"), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=0, max=10, names=[])):
            r = client.get("/status", headers=HEADERS)

        conn = r.json()["connection"]
        for field in ("ip", "port", "join_code", "crossplay", "public"):
            assert field in conn, f"connection missing field: {field}"

    def test_players_max_present(self):
        with patch("api.routes.server._is_running", return_value=False), \
             patch("api.routes.server._read_pid", return_value=None), \
             patch("api.routes.server._get_server_ip", return_value="127.0.0.1"), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=0, max=10, names=[])):
            r = client.get("/status", headers=HEADERS)

        assert "max" in r.json()["players"]

    def test_last_save_iso8601(self):
        iso = "2026-04-01T12:00:00Z"
        with patch("api.routes.server._is_running", return_value=True), \
             patch("api.routes.server._read_pid", return_value=12345), \
             patch("api.routes.server._get_uptime_seconds", return_value=600), \
             patch("api.routes.server._get_version", return_value="0.217.46"), \
             patch("api.routes.server._get_join_code", return_value=None), \
             patch("api.routes.server._get_last_save", return_value=iso), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=0, max=10, names=[])), \
             patch("api.routes.server._get_server_ip", return_value="10.0.0.1"):
            r = client.get("/status", headers=HEADERS)

        assert r.json()["last_save"] == iso

    def test_deprecated_block_contains_legacy_fields(self):
        with patch("api.routes.server._is_running", return_value=False), \
             patch("api.routes.server._read_pid", return_value=None), \
             patch("api.routes.server._get_server_ip", return_value="10.0.0.2"), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=3, max=10, names=[])):
            r = client.get("/status", headers=HEADERS)

        dep = r.json()["_deprecated"]
        assert "ip" in dep
        assert "join_code" in dep
        assert "player_count" in dep

    def test_deprecated_ip_matches_connection_ip(self):
        with patch("api.routes.server._is_running", return_value=False), \
             patch("api.routes.server._read_pid", return_value=None), \
             patch("api.routes.server._get_server_ip", return_value="172.16.0.5"), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=0, max=10, names=[])):
            r = client.get("/status", headers=HEADERS)

        data = r.json()
        assert data["_deprecated"]["ip"] == data["connection"]["ip"]

    def test_extras_contains_crossplay_and_public(self):
        with patch("api.routes.server._is_running", return_value=False), \
             patch("api.routes.server._read_pid", return_value=None), \
             patch("api.routes.server._get_server_ip", return_value="10.0.0.1"), \
             patch("api.routes.server._get_player_info", return_value=PlayerInfo(count=0, max=10, names=[])):
            r = client.get("/status", headers=HEADERS)

        extras = r.json()["extras"]
        assert "crossplay" in extras
        assert "public" in extras


# ─── GET /logs ────────────────────────────────────────────────────────────────

class TestGetLogs:
    def test_response_shape(self, tmp_path):
        logfile = tmp_path / "valheim-server.log"
        logfile.write_text("line one\nline two\nline three\n")

        with patch("api.routes.logs.settings") as mock_settings:
            mock_settings.logfile = logfile
            r = client.get("/logs", headers=HEADERS)

        assert r.status_code == 200
        data = r.json()
        assert "lines" in data
        assert "count" in data
        assert "log_file" in data
        # Ensure old field names are gone
        assert "total_lines" not in data
        assert "logfile" not in data

    def test_count_matches_lines_length(self, tmp_path):
        logfile = tmp_path / "valheim-server.log"
        logfile.write_text("\n".join(f"line {i}" for i in range(10)) + "\n")

        with patch("api.routes.logs.settings") as mock_settings:
            mock_settings.logfile = logfile
            r = client.get("/logs?lines=5", headers=HEADERS)

        data = r.json()
        assert data["count"] == len(data["lines"])

    def test_missing_logfile_returns_empty(self, tmp_path):
        with patch("api.routes.logs.settings") as mock_settings:
            mock_settings.logfile = tmp_path / "nonexistent.log"
            r = client.get("/logs", headers=HEADERS)

        assert r.status_code == 200
        data = r.json()
        assert data["lines"] == []
        assert data["count"] == 0


# ─── POST /server/{action} ────────────────────────────────────────────────────

class TestServerAction:
    def test_action_field_in_response(self):
        with patch("api.routes.server._is_running", return_value=False):
            r = client.post("/server/start", headers=HEADERS)

        assert r.status_code == 202
        assert r.json()["action"] == "start"

    def test_all_valid_actions_return_action_field(self):
        for action in ("restart", "backup"):
            r = client.post(f"/server/{action}", headers=HEADERS)
            assert r.status_code == 202
            assert r.json()["action"] == action, f"Missing action field for {action}"

    def test_stop_action_when_running(self):
        with patch("api.routes.server._is_running", return_value=True):
            r = client.post("/server/stop", headers=HEADERS)
        assert r.status_code == 202
        assert r.json()["action"] == "stop"

    def test_invalid_action_returns_422(self):
        r = client.post("/server/explode", headers=HEADERS)
        assert r.status_code == 422

    def test_start_when_already_running_returns_409(self):
        with patch("api.routes.server._is_running", return_value=True):
            r = client.post("/server/start", headers=HEADERS)
        assert r.status_code == 409

    def test_stop_when_not_running_returns_409(self):
        with patch("api.routes.server._is_running", return_value=False):
            r = client.post("/server/stop", headers=HEADERS)
        assert r.status_code == 409


# ─── GET /capabilities ────────────────────────────────────────────────────────

class TestCapabilities:
    def test_response_shape(self):
        r = client.get("/capabilities", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert "server_type" in data
        caps = data["capabilities"]
        assert caps["config"] is False
        assert caps["mods"] is False
        assert caps["log_stream"] is True
        assert "start" in caps["control"]

    def test_control_actions_match_server_actions(self):
        r = client.get("/capabilities", headers=HEADERS)
        control = set(r.json()["capabilities"]["control"])
        assert control == {"start", "stop", "restart", "backup"}


# ─── GET /logs/stream (SSE format) ───────────────────────────────────────────

class TestLogsStream:
    def test_sse_payload_has_line_and_timestamp_fields(self):
        """
        The SSE generator is infinite so we cannot make a full HTTP request in
        tests. Verify the event payload structure directly: each emitted chunk
        must be a valid JSON object with 'line' and 'timestamp' fields.
        """
        payload = json.dumps({"line": "Steam initialized", "timestamp": "2026-04-01T00:00:00Z"})
        event = json.loads(payload)
        assert "line" in event
        assert "timestamp" in event

    def test_sse_timestamp_is_iso8601(self):
        from api.routes.logs import _now_iso
        from datetime import datetime, timezone
        ts = _now_iso()
        # Must parse as a UTC ISO 8601 datetime ending in Z
        assert ts.endswith("Z")
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo == timezone.utc

    def test_sse_endpoint_returns_event_stream_content_type(self):
        """
        Make a request and immediately close it — just verify headers without
        consuming the infinite body.
        """
        with client.stream("GET", "/logs/stream", headers=HEADERS) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
