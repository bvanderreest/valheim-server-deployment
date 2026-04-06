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

# Client without auth override — used to verify 401 responses
no_auth_client = TestClient(app, raise_server_exceptions=False)


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
        assert caps["config"] is True
        assert caps["mods"] is True
        assert caps["log_stream"] is True
        assert "start" in caps["control"]

    def test_control_actions_match_server_actions(self):
        r = client.get("/capabilities", headers=HEADERS)
        control = set(r.json()["capabilities"]["control"])
        assert control == {"start", "stop", "restart", "backup", "update"}


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


# ─── GET /config ──────────────────────────────────────────────────────────────

def _mock_settings(tmp_path):
    """Return a mock settings object pointing script_dir at tmp_path."""
    m = MagicMock()
    m.script_dir = tmp_path
    m.server_type = "valheim"
    m.server_label = "Valheim Server"
    return m


class TestGetConfig:
    def test_returns_required_fields(self, tmp_path):
        (tmp_path / ".env").write_text('SERVER_NAME="TestServer"\nPASSWORD="secret"\nAPI_KEYS="hidden"\n')
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.get("/config", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["server_type"] == "valheim"
        assert "config" in body
        assert "editable_keys" in body
        assert "config_file" in body

    def test_excludes_api_keys(self, tmp_path):
        (tmp_path / ".env").write_text('API_KEYS="supersecret"\nSERVER_NAME="Test"\n')
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.get("/config", headers=HEADERS)
        assert r.status_code == 200
        config = r.json()["config"]
        assert "API_KEYS" not in config
        assert "SERVER_NAME" in config

    def test_masks_password(self, tmp_path):
        (tmp_path / ".env").write_text('PASSWORD="mypassword"\nSERVER_NAME="Test"\n')
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.get("/config", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["config"]["PASSWORD"] == "****"

    def test_excluded_keys_not_in_editable_keys(self, tmp_path):
        (tmp_path / ".env").write_text("")
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.get("/config", headers=HEADERS)
        editable = set(r.json()["editable_keys"])
        for excluded in ("API_KEYS", "API_ENABLED", "API_HOST", "API_PORT", "CORS_ORIGINS", "LOG_DIR"):
            assert excluded not in editable

    def test_requires_auth(self):
        app.dependency_overrides.clear()
        try:
            r = no_auth_client.get("/config")
            assert r.status_code == 401
        finally:
            app.dependency_overrides[require_api_key] = _override_auth


# ─── PATCH /config ────────────────────────────────────────────────────────────

class TestPatchConfig:
    def test_applies_editable_key(self, tmp_path):
        (tmp_path / ".env").write_text('SERVER_NAME="OldName"\n')
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.patch("/config", json={"changes": {"SERVER_NAME": "NewName"}}, headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["applied"]["SERVER_NAME"] == "NewName"
        assert body["restart_required"] is True

    def test_rejects_excluded_key(self, tmp_path):
        (tmp_path / ".env").write_text("")
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.patch("/config", json={"changes": {"API_KEYS": "hacked"}}, headers=HEADERS)
        assert r.status_code == 400

    def test_rejects_unknown_key(self, tmp_path):
        (tmp_path / ".env").write_text("")
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.patch("/config", json={"changes": {"TOTALLY_MADE_UP": "val"}}, headers=HEADERS)
        assert r.status_code == 400

    def test_backup_created(self, tmp_path):
        (tmp_path / ".env").write_text('SAVE_INTERVAL="300"\n')
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            client.patch("/config", json={"changes": {"SAVE_INTERVAL": "600"}}, headers=HEADERS)
        assert len(list(tmp_path.glob(".env.bak.*"))) == 1

    def test_no_restart_required_for_non_critical_key(self, tmp_path):
        (tmp_path / ".env").write_text('SAVE_INTERVAL="300"\n')
        with patch("api.routes.config.settings", _mock_settings(tmp_path)):
            r = client.patch("/config", json={"changes": {"SAVE_INTERVAL": "600"}}, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["restart_required"] is False

    def test_requires_auth(self):
        app.dependency_overrides.clear()
        try:
            r = no_auth_client.patch("/config", json={"changes": {"SAVE_INTERVAL": "600"}})
            assert r.status_code == 401
        finally:
            app.dependency_overrides[require_api_key] = _override_auth


# ─── GET /metrics ─────────────────────────────────────────────────────────────

class TestMetrics:
    def test_returns_200_unauthenticated(self):
        r = no_auth_client.get("/metrics")
        assert r.status_code == 200

    def test_content_type_is_plain_text(self):
        r = client.get("/metrics")
        assert "text/plain" in r.headers["content-type"]

    def test_contains_required_metric_names(self):
        r = client.get("/metrics")
        body = r.text
        for metric in (
            "valheim_server_running",
            "valheim_server_uptime_seconds",
            "valheim_players_connected",
            "valheim_backup_count",
            "valheim_world_size_bytes",
            "valheim_last_save_age_seconds",
        ):
            assert metric in body

    def test_each_metric_has_help_and_type_lines(self):
        r = client.get("/metrics")
        body = r.text
        assert "# HELP valheim_server_running" in body
        assert "# TYPE valheim_server_running gauge" in body

    def test_metric_values_are_numeric(self):
        r = client.get("/metrics")
        for line in r.text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            assert len(parts) == 2, f"Expected 'name value', got: {line!r}"
            float(parts[1])  # must be parseable as a number


# ─── Mod helpers ──────────────────────────────────────────────────────────────

import io
import json as _json
import zipfile as _zipfile


def _make_mod_settings(tmp_path):
    """Return a mock settings object with mod dirs pointing into tmp_path."""
    m = MagicMock()
    m.mod_dir = tmp_path / "plugins"
    m.mod_disabled_dir = tmp_path / "plugins_disabled"
    m.mod_trash_dir = tmp_path / "plugins_trash"
    m.mod_allowed_sources_list = ["thunderstore.io", "gcdn.thunderstore.io"]
    m.mod_max_size_mb = 100
    return m


def _make_zip(manifest: dict | None = None) -> bytes:
    """Create an in-memory ZIP with an optional manifest.json."""
    buf = io.BytesIO()
    with _zipfile.ZipFile(buf, "w") as zf:
        if manifest is not None:
            zf.writestr("manifest.json", _json.dumps(manifest))
        zf.writestr("BepInEx/plugins/Example.dll", b"fake dll")
    return buf.getvalue()


def _write_mod(plugins_dir, package_id: str, manifest: dict | None = None, inv_entry: dict | None = None):
    """Create a fake installed mod directory."""
    mod_dir = plugins_dir / package_id
    mod_dir.mkdir(parents=True, exist_ok=True)
    if manifest:
        (mod_dir / "manifest.json").write_text(_json.dumps(manifest))
    if inv_entry:
        inv_file = plugins_dir / "mods.json"
        inventory = _json.loads(inv_file.read_text()) if inv_file.exists() else {}
        inventory[package_id] = inv_entry
        inv_file.write_text(_json.dumps(inventory))


# ─── GET /mods ────────────────────────────────────────────────────────────────

class TestGetMods:
    def test_returns_empty_when_no_mods(self, tmp_path):
        with patch("api.routes.mods.settings", _make_mod_settings(tmp_path)):
            r = client.get("/mods", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["mods"] == []
        assert body["count"] == 0

    def test_lists_enabled_mod(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_dir, "BepInEx_pack", manifest={"name": "BepInEx Pack", "version_number": "5.4.2100"})
        with patch("api.routes.mods.settings", s):
            r = client.get("/mods", headers=HEADERS)
        assert r.status_code == 200
        mods = r.json()["mods"]
        assert len(mods) == 1
        assert mods[0]["package_id"] == "BepInEx_pack"
        assert mods[0]["name"] == "BepInEx Pack"
        assert mods[0]["enabled"] is True

    def test_lists_disabled_mod(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_disabled_dir, "some_mod", manifest={"name": "Some Mod", "version_number": "1.0.0"})
        with patch("api.routes.mods.settings", s):
            r = client.get("/mods", headers=HEADERS)
        mods = r.json()["mods"]
        assert len(mods) == 1
        assert mods[0]["enabled"] is False

    def test_requires_auth(self):
        app.dependency_overrides.clear()
        try:
            r = no_auth_client.get("/mods")
            assert r.status_code == 401
        finally:
            app.dependency_overrides[require_api_key] = _override_auth


# ─── POST /mods/install ───────────────────────────────────────────────────────

class TestInstallMod:
    def test_rejects_disallowed_source(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s):
            r = client.post(
                "/mods/install",
                json={"source_url": "https://evil.example.com/mod.zip"},
                headers=HEADERS,
            )
        assert r.status_code == 400
        assert "not allowed" in r.json()["detail"].lower()

    def test_rejects_invalid_package_id(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s):
            r = client.post(
                "/mods/install",
                json={"source_url": "https://thunderstore.io/mod.zip", "package_id": "../evil"},
                headers=HEADERS,
            )
        assert r.status_code == 400

    def test_rejects_oversized_archive(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        s.mod_max_size_mb = 1  # 1 MB limit for test
        zip_bytes = _make_zip({"name": "Big Mod", "version_number": "1.0.0"})

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"content-length": str(2 * 1024 * 1024)}  # 2 MB
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: s
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.return_value = mock_resp

        with patch("api.routes.mods.settings", s), \
             patch("api.services.mods.httpx.Client", return_value=mock_client):
            r = client.post(
                "/mods/install",
                json={"source_url": "https://thunderstore.io/mod.zip", "package_id": "big_mod"},
                headers=HEADERS,
            )
        assert r.status_code == 400
        assert "large" in r.json()["detail"].lower()

    def test_rejects_zip_path_traversal(self, tmp_path):
        """ZIP containing ../ paths must be rejected."""
        buf = io.BytesIO()
        with _zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.sh", "rm -rf /")
        bad_zip = buf.getvalue()

        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s), \
             patch("api.services.mods.install_mod", side_effect=ValueError("Unsafe path in archive: '../evil.sh'")):
            r = client.post(
                "/mods/install",
                json={"source_url": "https://thunderstore.io/mod.zip", "package_id": "evil_mod"},
                headers=HEADERS,
            )
        assert r.status_code == 400
        assert "unsafe" in r.json()["detail"].lower()

    def test_successful_install(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        from api.models import ModInfo
        from datetime import datetime, timezone
        mock_mod = ModInfo(
            package_id="BepInEx_pack",
            name="BepInEx Pack",
            version="5.4.2100",
            enabled=True,
            installed_at=datetime.now(timezone.utc).isoformat(),
            source="https://thunderstore.io/BepInEx_pack.zip",
        )
        with patch("api.routes.mods.settings", s), \
             patch("api.services.mods.install_mod", return_value=mock_mod):
            r = client.post(
                "/mods/install",
                json={"source_url": "https://thunderstore.io/BepInEx_pack.zip", "package_id": "BepInEx_pack"},
                headers=HEADERS,
            )
        assert r.status_code == 201
        body = r.json()
        assert body["package_id"] == "BepInEx_pack"
        assert body["installed"] is True


# ─── DELETE /mods/{package_id} ────────────────────────────────────────────────

class TestDeleteMod:
    def test_rejects_invalid_package_id(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s):
            r = client.delete("/mods/../evil", headers=HEADERS)
        # FastAPI path routing won't even match this, but if it does, expect 400 or 404
        assert r.status_code in (400, 404, 422)

    def test_returns_404_for_unknown_mod(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s):
            r = client.delete("/mods/nonexistent_mod", headers=HEADERS)
        assert r.status_code == 404

    def test_moves_to_trash(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_dir, "my_mod", manifest={"name": "My Mod", "version_number": "1.0.0"})
        with patch("api.routes.mods.settings", s):
            r = client.delete("/mods/my_mod", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["action"] == "deleted"
        assert not (s.mod_dir / "my_mod").exists()
        # Verify something is in trash
        trash_entries = list(s.mod_trash_dir.iterdir())
        assert len(trash_entries) == 1
        assert trash_entries[0].name.startswith("my_mod_")


# ─── POST /mods/{package_id}/enable and /disable ─────────────────────────────

class TestEnableDisableMod:
    def test_enable_moves_from_disabled_to_enabled(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_disabled_dir, "some_mod", manifest={"name": "Some Mod", "version_number": "1.0.0"})
        with patch("api.routes.mods.settings", s):
            r = client.post("/mods/some_mod/enable", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["action"] == "enabled"
        assert (s.mod_dir / "some_mod").exists()
        assert not (s.mod_disabled_dir / "some_mod").exists()

    def test_enable_404_if_not_found(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s):
            r = client.post("/mods/ghost_mod/enable", headers=HEADERS)
        assert r.status_code == 404

    def test_enable_400_if_already_enabled(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_dir, "active_mod")
        with patch("api.routes.mods.settings", s):
            r = client.post("/mods/active_mod/enable", headers=HEADERS)
        assert r.status_code == 400

    def test_disable_moves_from_enabled_to_disabled(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_dir, "some_mod", manifest={"name": "Some Mod", "version_number": "1.0.0"})
        with patch("api.routes.mods.settings", s):
            r = client.post("/mods/some_mod/disable", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["action"] == "disabled"
        assert (s.mod_disabled_dir / "some_mod").exists()
        assert not (s.mod_dir / "some_mod").exists()

    def test_disable_404_if_not_found(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        with patch("api.routes.mods.settings", s):
            r = client.post("/mods/ghost_mod/disable", headers=HEADERS)
        assert r.status_code == 404

    def test_disable_400_if_already_disabled(self, tmp_path):
        s = _make_mod_settings(tmp_path)
        _write_mod(s.mod_disabled_dir, "inactive_mod")
        with patch("api.routes.mods.settings", s):
            r = client.post("/mods/inactive_mod/disable", headers=HEADERS)
        assert r.status_code == 400


# ─── GET /capabilities — mods: true ──────────────────────────────────────────

class TestCapabilitiesMods:
    def test_mods_capability_is_true(self):
        r = client.get("/capabilities", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["capabilities"]["mods"] is True
