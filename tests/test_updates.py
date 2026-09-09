"""Tests for GET /updates — "is a server update waiting?".

The important behaviour is the failure mode: when Steam cannot be reached,
the answer must never look like "up to date". That is the failure that lets a
server sit stale for weeks while a dashboard shows green.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.auth import require_api_key
from api.main import app
import api.routes.updates as upd

TEST_KEY = "test-api-key"
app.dependency_overrides[require_api_key] = lambda: TEST_KEY
client = TestClient(app, raise_server_exceptions=False)
HEADERS = {"X-API-Key": TEST_KEY}

BRANCHES = {
    "public": {"buildid": "21981590", "timeupdated": "1771576792"},
    "default_pre1_0": {"buildid": "21981590", "description": "Last stable build before 1.0", "pwdrequired": "0"},
}


@pytest.fixture(autouse=True)
def _clear_cache():
    upd._cache.update(at=0.0, data=None)
    yield
    upd._cache.update(at=0.0, data=None)


async def _fake_branches():
    return BRANCHES


def test_reports_up_to_date_when_ids_match():
    with patch.object(upd, "_remote_branches", _fake_branches), \
         patch.object(upd, "_installed_buildid", lambda: "21981590"):
        d = client.get("/v1/updates", headers=HEADERS).json()
    assert d["update_available"] is False
    assert d["installed_buildid"] == d["available_buildid"] == "21981590"


def test_reports_update_when_ids_differ():
    with patch.object(upd, "_remote_branches", _fake_branches), \
         patch.object(upd, "_installed_buildid", lambda: "20000000"):
        d = client.get("/v1/updates", headers=HEADERS).json()
    assert d["update_available"] is True


def test_unknown_is_not_the_same_as_up_to_date():
    """If the local build id cannot be read, the answer is None — not False.
    Conflating 'unknown' with 'current' is how a stale server looks healthy."""
    with patch.object(upd, "_remote_branches", _fake_branches), \
         patch.object(upd, "_installed_buildid", lambda: None):
        d = client.get("/v1/updates", headers=HEADERS).json()
    assert d["update_available"] is None


def test_steam_unreachable_is_an_error_not_a_green_light():
    async def boom():
        raise RuntimeError("connection refused")
    with patch.object(upd, "_remote_branches", boom), \
         patch.object(upd, "_installed_buildid", lambda: "21981590"):
        r = client.get("/v1/updates", headers=HEADERS)
    assert r.status_code == 503
    assert "Steam" in r.json()["detail"]


def test_falls_back_to_cache_when_steam_goes_down():
    """A Steam blip should degrade to stale-but-useful, not to an error."""
    async def boom():
        raise RuntimeError("down")
    with patch.object(upd, "_remote_branches", _fake_branches), \
         patch.object(upd, "_installed_buildid", lambda: "21981590"):
        assert client.get("/v1/updates", headers=HEADERS).status_code == 200
    with patch.object(upd, "_remote_branches", boom), \
         patch.object(upd, "_installed_buildid", lambda: "21981590"):
        d = client.get("/v1/updates", headers=HEADERS).json()
    assert d["cached"] is True
    assert d["update_available"] is False


def test_rollback_branches_are_listed():
    with patch.object(upd, "_remote_branches", _fake_branches), \
         patch.object(upd, "_installed_buildid", lambda: "21981590"):
        d = client.get("/v1/updates", headers=HEADERS).json()
    names = [b["branch"] for b in d["rollback_branches"]]
    assert "default_pre1_0" in names and "public" not in names


def test_requires_auth():
    bare = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(require_api_key, None)
    try:
        assert bare.get("/v1/updates").status_code == 401
    finally:
        app.dependency_overrides[require_api_key] = lambda: TEST_KEY
