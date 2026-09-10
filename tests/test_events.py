"""The event timeline, against a real session log.

`tests/fixtures/session-1.0-real.log` is an unedited copy of
/srv/valheim/logs/valheim-server.log taken 2026-09-10, covering the session in
which a player mistyped the password, was refused, rejoined, and played.

It is SANITISED: this repo is public, and the raw log carries the operator's
public IP, the live join code, PlayFab peer ids and lobby tokens. Those are
replaced with structurally identical fakes; every line shape and timing that
the parsers read is untouched. That
session is the reason this module exists: everything below was in the log and
none of it reached a screen.
"""
from pathlib import Path

import pytest

from api.services.events import parse

LOG = (Path(__file__).parent / "fixtures" / "session-1.0-real.log").read_text(
    errors="replace").splitlines()


@pytest.fixture(scope="module")
def t():
    return parse(LOG)


def test_the_refused_join_is_visible(t):
    """The whole point. A player could not get in and nothing said so."""
    fails = t["auth_failures"]
    assert len(fails) == 1
    assert fails[0]["peer"] == "playfab/AAAA1111BBBB2222"
    assert fails[0]["at"].startswith("2026-09-10T")


def test_joins_and_leaves_carry_the_servers_own_count(t):
    kinds = [e["kind"] for e in t["events"]]
    assert "join" in kinds and "leave" in kinds
    joins = [e for e in t["events"] if e["kind"] == "join"]
    assert joins[-1]["players"] == 1, "the server's own tally, not a derived one"


def test_disk_headroom_is_read_with_the_servers_own_thresholds(t):
    """Below `blocked_below_bytes` the server STOPS SAVING. Nothing read this."""
    d = t["disk"]
    assert d["free_bytes"] > 0
    assert d["blocked_below_bytes"] > 0
    assert d["warn_below_bytes"] > d["blocked_below_bytes"]
    assert d["state"] == "ok"


@pytest.mark.parametrize("free,expected", [
    (10_000_000, "blocked"),      # under the stop-saving line
    (45_000_000, "warning"),      # under the warn line, above the stop line
    (999_000_000, "ok"),
])
def test_the_disk_state_can_reach_every_value(free, expected):
    """A state that can only ever be 'ok' is not a check."""
    line = (f"09/10/2026 09:51:11: Available space to current user: {free}. "
            f"Saving is blocked if below: 30119888 bytes. "
            f"Warnings are given if below: 60239776")
    assert parse([line])["disk"]["state"] == expected


def test_every_save_is_broken_into_phases(t):
    assert len(t["saves"]) == 8
    for s in t["saves"]:
        names = [p["name"] for p in s["phases"]]
        assert names[:2] == ["Clone chunks", "Prepare ZDOs"], names
        assert "DB2 writing" in names
        assert s["total_ms"] > 0


def test_blocking_time_is_separated_from_write_time(t):
    """The distinction that matters to a player: blocking work freezes the
    world, the write does not. On this server the blocking part is the larger
    of the two, which is invisible if you only report a total."""
    s = t["last_save"]
    assert s["blocking_ms"] > 0
    assert s["blocking_ms"] == sum(p["ms"] for p in s["phases"] if p["blocking"])
    assert s["total_ms"] == pytest.approx(181.0)
    assert s["blocking_ms"] > s["total_ms"], (
        "on this sample the freeze is longer than the write; if that stops "
        "being true the sample changed, not the code")


def test_the_public_address_and_join_code_are_recovered(t):
    assert t["session"]["join_code"] == "123456"
    assert t["session"]["public_addr"] == "203.0.113.10:2456"


def test_join_code_retries_are_counted(t):
    """A retry loop means nobody can connect by code while the server looks
    perfectly healthy."""
    assert t["join_code_retries"] == 2


def test_an_unfinished_save_is_reported_as_in_progress():
    """Stage 1 seen, stage 5 never arrived."""
    partial = [
        "09/10/2026 09:51:11: GetSaveClonePerChunk. Calculated number of actual chunk files: 19  Number of dirty chunks to save: 0 [4ms]",
        "09/10/2026 09:51:11: PrepareSave: ZDOExtraData.PrepareSave done [256ms]",
        "09/10/2026 09:51:11: World save (1/5) Cloud & Backup checks done [19ms] => Save number 13",
    ]
    out = parse(partial)
    assert out["save_in_progress"] is True
    assert out["last_save"] is None


def test_a_finished_save_is_not_in_progress(t):
    assert t["save_in_progress"] is False
