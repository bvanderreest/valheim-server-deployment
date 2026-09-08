"""Tests for GET/PATCH /modifiers — gameplay configuration (#77).

These cover the three things that actually matter for this endpoint:
  1. It parses the real modifiers.conf shape, ignoring commented-out entries.
  2. It rejects anything not on the allow-list — these values become
     `-modifier`/`-setkey` arguments on a process launch.
  3. A write preserves the file's operator-facing comments.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.auth import require_api_key
from api.main import app
from api.services import modifiers as mod

TEST_KEY = "test-api-key"
app.dependency_overrides[require_api_key] = lambda: TEST_KEY
client = TestClient(app)
HEADERS = {"X-API-Key": TEST_KEY}



SAMPLE = '''#!/usr/bin/env bash
# Valheim server manager — Game modifiers and presets
# IMPORTANT COMMENT THAT MUST SURVIVE A ROUND TRIP

PRESET="normal"

########################################
#            MODIFIERS                 #
########################################
# Combat: veryeasy | easy | hard | veryhard
ENABLE_MODIFIERS=true
MODIFIERS=(
    "Combat=easy"
    "DeathPenalty=easy"
    "Resources=more"
    "Raids=less"
    "Portals=casual"
)

########################################
#             SETKEYS                  #
########################################
SETKEYS=(
    # --- Map & Navigation ---
    # "nomap"                # commented out - must be ignored
    # "nobuildcost"          # also commented
)
'''


@pytest.fixture
def conf(tmp_path, monkeypatch):
    p = tmp_path / "modifiers.conf"
    p.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr("api.routes.modifiers._conf_path", lambda: p)
    return p


# ─── Parsing ─────────────────────────────────────────────────────────────────

def test_get_parses_current_values(conf):
    r = client.get("/modifiers", headers=HEADERS)
    assert r.status_code == 200
    d = r.json()
    assert d["preset"] == "normal"
    assert d["enable_modifiers"] is True
    assert d["modifiers"] == {
        "Combat": "easy", "DeathPenalty": "easy",
        "Resources": "more", "Raids": "less", "Portals": "casual",
    }
    assert d["restart_required"] is True


def test_commented_setkeys_are_not_active(conf):
    """The example file ships every setkey commented out. A parser that
    ignores the '#' would silently enable irreversible world settings."""
    d = client.get("/modifiers", headers=HEADERS).json()
    assert d["setkeys"]["toggles"] == []
    assert d["setkeys"]["numeric"] == {}


def test_get_advertises_valid_options(conf):
    o = client.get("/modifiers", headers=HEADERS).json()["options"]
    assert "hardcore" in o["presets"]
    assert o["modifiers"]["Portals"] == ["casual", "hard", "veryhard"]
    assert len(o["toggles"]) == 18
    assert len(o["numeric"]) == 12
    assert o["numeric_default"] == 100
    assert "deathdeleteItems" in o["irreversible_toggles"]


# ─── Validation (argument-injection surface) ─────────────────────────────────

@pytest.mark.parametrize("payload,frag", [
    ({"preset": "impossible"},                      "Unknown preset"),
    ({"modifiers": {"Combat": "nightmare"}},        "Invalid value"),
    ({"modifiers": {"Bogus": "easy"}},              "Unknown modifier category"),
    ({"setkeys": {"toggles": ["rm -rf /"]}},        "Unknown setkey toggle"),
    ({"setkeys": {"numeric": {"Nope": 100}}},       "Unknown numeric setkey"),
    ({"setkeys": {"numeric": {"EnemyDamage": 99999}}}, "out of range"),
    ({"setkeys": {"numeric": {"EnemyDamage": "abc"}}}, "must be an integer"),
])
def test_patch_rejects_bad_input(conf, payload, frag):
    r = client.patch("/modifiers", json=payload, headers=HEADERS)
    assert r.status_code == 422
    assert frag in r.json()["detail"]


def test_patch_rejects_empty_payload(conf):
    assert client.patch("/modifiers", json={}, headers=HEADERS).status_code == 422


# ─── Writing ─────────────────────────────────────────────────────────────────

def test_patch_round_trip(conf):
    r = client.patch("/modifiers", headers=HEADERS, json={
        "preset": "hard",
        "modifiers": {"Combat": "veryhard", "Resources": "less"},
        "setkeys": {"toggles": ["nomap", "passivemobs"],
                    "numeric": {"EnemyDamage": 200, "StaminaRate": 0}},
    })
    assert r.status_code == 200
    applied = r.json()["applied"]
    assert applied["preset"] == "hard"
    assert applied["modifiers"] == {"Combat": "veryhard", "Resources": "less"}
    assert applied["setkeys"]["toggles"] == ["nomap", "passivemobs"]
    assert applied["setkeys"]["numeric"] == {"EnemyDamage": 200, "StaminaRate": 0}
    assert r.json()["restart_required"] is True

    # And it is genuinely on disk, not just echoed back.
    again = client.get("/modifiers", headers=HEADERS).json()
    assert again["preset"] == "hard"
    assert again["setkeys"]["numeric"]["EnemyDamage"] == 200


def test_write_preserves_comments(conf):
    client.patch("/modifiers", headers=HEADERS, json={"preset": "casual"})
    text = conf.read_text(encoding="utf-8")
    assert "IMPORTANT COMMENT THAT MUST SURVIVE A ROUND TRIP" in text
    assert "#            MODIFIERS                 #" in text
    assert "Combat: veryeasy | easy | hard | veryhard" in text


def test_clearing_all_modifiers_disables_the_flag(conf):
    """ENABLE_MODIFIERS=true with an empty array reads as a bug to the next
    person who opens the file."""
    client.patch("/modifiers", headers=HEADERS, json={"modifiers": {}})
    d = client.get("/modifiers", headers=HEADERS).json()
    assert d["modifiers"] == {}
    assert d["enable_modifiers"] is False


def test_irreversible_toggles_are_warned_about(conf):
    r = client.patch("/modifiers", headers=HEADERS,
                     json={"setkeys": {"toggles": ["deathdeleteItems"]}})
    warnings = r.json()["warnings"]
    assert any("deathdeleteItems" in w and "cannot be undone" in w for w in warnings)


def test_write_makes_a_backup(conf):
    client.patch("/modifiers", headers=HEADERS, json={"preset": "easy"})
    assert list(conf.parent.glob("modifiers.conf.bak-*")), "no backup written"


def test_empty_preset_is_allowed(conf):
    r = client.patch("/modifiers", headers=HEADERS, json={"preset": ""})
    assert r.status_code == 200
    assert r.json()["applied"]["preset"] == ""


# ─── Auth ────────────────────────────────────────────────────────────────────

def test_requires_auth(conf):
    bare = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(require_api_key, None)
    try:
        assert bare.get("/modifiers").status_code == 401
    finally:
        app.dependency_overrides[require_api_key] = lambda: TEST_KEY
