"""Tests for the public-repo hardening: CORS, docs gating, route versioning.

Covers #78, #79, #80. Each asserts BOTH directions where that is meaningful —
a gate that is only ever tested in its permissive state is not a gate.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

from api.auth import require_api_key
from api.main import app

TEST_KEY = "test-api-key"
app.dependency_overrides[require_api_key] = lambda: TEST_KEY
client = TestClient(app)
HEADERS = {"X-API-Key": TEST_KEY}



# ─── #80 route versioning ────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/status", "/capabilities", "/config", "/mods", "/modifiers"])
def test_v1_and_bare_paths_both_resolve(path):
    """Legacy bare paths must keep working alongside /v1."""
    bare = client.get(path, headers=HEADERS)
    v1 = client.get(f"/v1{path}", headers=HEADERS)
    assert bare.status_code != 404, f"{path} disappeared"
    assert v1.status_code != 404, f"/v1{path} not mounted"
    assert bare.status_code == v1.status_code


def test_health_is_not_versioned():
    """/health is an infrastructure probe, not part of the contract."""
    assert client.get("/health").status_code == 200
    assert client.get("/v1/health").status_code == 404


def test_v1_requires_auth_too():
    bare = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(require_api_key, None)
    try:
        assert bare.get("/v1/status").status_code == 401
    finally:
        app.dependency_overrides[require_api_key] = lambda: TEST_KEY


# ─── #79 docs gating ─────────────────────────────────────────────────────────

def test_openapi_is_gated_with_docs(monkeypatch):
    """The schema must not be served while the UI is hidden. FastAPI does not
    do this by itself — openapi_url is independent of docs_url."""
    import api.config as cfg
    monkeypatch.setattr(cfg.settings, "api_docs_enabled", False)
    import api.main as m
    reloaded = importlib.reload(m)
    c = TestClient(reloaded.app, raise_server_exceptions=False)
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(p).status_code == 404, f"{p} exposed while docs disabled"


def test_all_three_present_when_enabled(monkeypatch):
    import api.config as cfg
    monkeypatch.setattr(cfg.settings, "api_docs_enabled", True)
    import api.main as m
    reloaded = importlib.reload(m)
    c = TestClient(reloaded.app, raise_server_exceptions=False)
    for p in ("/docs", "/openapi.json"):
        assert c.get(p).status_code == 200, f"{p} missing while docs enabled"


# ─── #78 CORS ────────────────────────────────────────────────────────────────

def test_wildcard_cors_is_rejected_at_startup(monkeypatch):
    """'*' + credentials is rejected by every browser; shipping it is a
    wildcard on an API that can stop and reconfigure the server."""
    import api.config as cfg
    monkeypatch.setattr(cfg.settings, "cors_origins", "*")
    monkeypatch.setattr(cfg.settings, "api_enabled", True)
    monkeypatch.setattr(cfg.settings, "api_keys", "k" * 16)
    import api.main as m
    reloaded = importlib.reload(m)
    with pytest.raises(RuntimeError, match=r'CORS_ORIGINS.*not allowed'):
        with TestClient(reloaded.app):
            pass


def test_explicit_origin_is_accepted(monkeypatch):
    import api.config as cfg
    monkeypatch.setattr(cfg.settings, "cors_origins", "https://valheim.example.com")
    assert cfg.settings.cors_origins_list == ["https://valheim.example.com"]
    assert "*" not in cfg.settings.cors_origins_list


def test_credentials_are_not_enabled():
    """Auth is a header, so credentialed CORS buys nothing and is what makes a
    wildcard dangerous."""
    from starlette.middleware.cors import CORSMiddleware
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS middleware missing"
    assert cors[0].kwargs.get("allow_credentials") is False


# ─── #33 web console ─────────────────────────────────────────────────────────

def test_console_is_served_at_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert r.headers.get("cache-control") == "no-store"


def test_console_is_public_but_the_api_is_not():
    """The page is only markup; everything it can DO still needs the key."""
    bare = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(require_api_key, None)
    try:
        assert bare.get("/").status_code == 200
        assert bare.get("/v1/status").status_code == 401
        assert bare.get("/v1/modifiers").status_code == 401
    finally:
        app.dependency_overrides[require_api_key] = lambda: TEST_KEY


def test_console_targets_the_versioned_routes():
    """A console pinned to the legacy bare paths would silently miss /v1."""
    html = client.get("/").text
    assert "const API_BASE = '/v1'" in html


def test_console_is_a_wellformed_document():
    html = client.get("/").text
    for tag in ("<!doctype html>", "<html", "</html>", "<head>", "</head>", "<body>", "</body>"):
        assert tag in html.lower() or tag in html, f"missing {tag}"
    assert html.count("<script>") == html.count("</script>")


def test_console_declares_no_hardcoded_key():
    """A shipped console must not carry a credential — this repo is public."""
    html = client.get("/").text
    import re
    assert not re.search(r'X-API-Key["\']\s*:\s*["\'][A-Za-z0-9]{16,}', html)


# ─── /status extras (what the console needs and cannot derive) ───────────────

def test_status_extras_carries_console_fields():
    """The console reads extras.rss_mb, extras.save_seconds and
    extras.backups. When those were absent the Process and World cards
    rendered EMPTY against the live server while every test passed."""
    d = client.get("/v1/status", headers=HEADERS).json()
    extras = d["extras"]
    for k in ("rss_mb", "save_seconds", "world_objects", "world_bytes", "backups", "crossplay", "public"):
        assert k in extras, f"extras missing {k}"
    assert isinstance(extras["backups"], list)


def test_backups_entries_have_age_and_size():
    """Backup AGE is the thing that matters, so each entry must carry a
    timestamp the UI can render, not just a filename."""
    for b in client.get("/v1/status", headers=HEADERS).json()["extras"]["backups"]:
        assert {"name", "bytes", "modified"} <= set(b)


def test_console_ago_handles_iso_strings():
    """last_save is ISO 8601; the console used to subtract it from a number
    and render 'NaN h NaN min ago'."""
    html = client.get("/").text
    assert "Date.parse(t)" in html
    assert "Number.isFinite(ms)" in html
