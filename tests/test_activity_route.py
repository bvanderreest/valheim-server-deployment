"""The /activity contract, served from the real session fixture."""
import pathlib

import pytest

from fastapi.testclient import TestClient  # noqa: E402

from api.auth import require_api_key  # noqa: E402
from api.config import settings  # noqa: E402
from api.main import app  # noqa: E402

TEST_KEY = "test-api-key"

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "session-1.0-real.log"


@pytest.fixture
def client(tmp_path, monkeypatch):
    log = tmp_path / "valheim-server.log"
    log.write_text(FIXTURE.read_text(errors="replace"))
    monkeypatch.setattr(settings, "_logfile", log, raising=False)
    app.dependency_overrides[require_api_key] = lambda: TEST_KEY
    yield TestClient(app)
    app.dependency_overrides.pop(require_api_key, None)


@pytest.fixture
def unauthed(tmp_path, monkeypatch):
    """Real auth, not the override.

    tests/test_api.py installs app.dependency_overrides[require_api_key] at
    MODULE IMPORT time and never removes it, so by the time this runs every
    request is already authenticated. It has to be cleared explicitly or this
    test silently checks nothing.
    """
    log = tmp_path / "valheim-server.log"
    log.write_text(FIXTURE.read_text(errors="replace"))
    monkeypatch.setattr(settings, "_logfile", log, raising=False)
    saved = app.dependency_overrides.pop(require_api_key, None)
    yield TestClient(app, raise_server_exceptions=False)
    if saved is not None:
        app.dependency_overrides[require_api_key] = saved


def _get(client, path="/v1/activity", **params):
    return client.get(path, params=params, headers={"X-API-Key": TEST_KEY})


def test_activity_requires_a_key(unauthed):
    """It exposes who tried to log in and failed. That is not public."""
    assert unauthed.get("/v1/activity").status_code == 401


@pytest.mark.parametrize("path", ["/activity", "/v1/activity"])
def test_both_mounts_answer(client, path):
    assert _get(client, path).status_code == 200


def test_the_refused_login_is_in_the_payload(client):
    d = _get(client).json()
    assert len(d["auth_failures"]) == 1
    assert d["auth_failures"][0]["kind"] == "auth_failed"


def test_disk_carries_the_servers_own_stop_saving_threshold(client):
    d = _get(client).json()["disk"]
    assert d["state"] in ("ok", "warning", "blocked")
    assert d["blocked_below_bytes"] > 0, "without this the UI has to invent a threshold"


def test_the_last_save_is_phased_and_splits_freeze_from_write(client):
    s = _get(client).json()["last_save"]
    assert [p["name"] for p in s["phases"]][:2] == ["Clone chunks", "Prepare ZDOs"]
    assert all(p["blocking"] for p in s["phases"][:2])
    assert not any(p["blocking"] for p in s["phases"][2:])
    assert s["blocking_ms"] > 0 and s["total_ms"] > 0


def test_limit_is_bounded(client):
    assert _get(client, limit=1).status_code == 200
    assert len(_get(client, limit=1).json()["events"]) == 1
    assert _get(client, limit=0).status_code == 422
    assert _get(client, limit=9999).status_code == 422
