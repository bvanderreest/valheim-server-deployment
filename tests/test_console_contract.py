"""Static invariants of the shipped console.

These are not style rules. Each one is a bug that reached a live server.
"""
import re
from pathlib import Path

import pytest

CONSOLE = Path(__file__).resolve().parents[1] / "api" / "static" / "index.html"
HTML = CONSOLE.read_text(encoding="utf-8")

# Everything above this marker is the demo's fake server; everything below runs
# against whatever API actually answered.
_BOUNDARY = "/* ===================== AUTH ===================== */"


def _live_region() -> str:
    i = HTML.index(_BOUNDARY)
    return HTML[i:]


def test_live_code_never_reads_the_mock_server_state():
    """The bug: the Overview showed 'Backups kept: 7 of 6' on a server whose
    BACKUPS_KEEP is 12.

    `S` is the DEMO's in-page fake server. Reading `S.config.BACKUPS_KEEP` from
    a live render mixes a real numerator with the demo's denominator, and the
    result is a number that looks broken and can never be right. The same line
    took SAVE_INTERVAL from the mock, which happened to match and so hid it.
    """
    live = _live_region()
    base = HTML.index(_BOUNDARY)
    offenders = []
    for m in re.finditer(r"S\.(config|version|extras|mod)\b", live):
        line_start = live.rfind("\n", 0, m.start()) + 1
        line_end = live.find("\n", m.start())
        line = live[line_start: line_end if line_end != -1 else len(live)]
        # A deliberate demo fallback is marked inline; a comment is not code.
        if "demo-fallback" in line or line.lstrip().startswith(("//", "*", "/*")):
            continue
        offenders.append(f"line {HTML[:base + m.start()].count(chr(10)) + 1}: {line.strip()[:90]}")
    assert not offenders, (
        "live rendering must read /config or /status, never the mock's state:\n  "
        + "\n  ".join(offenders)
    )


def test_the_mock_still_exists_so_the_boundary_test_means_something():
    """Guards the guard: if `S` were renamed or the marker moved, the test above
    would pass by finding nothing and stop protecting anything."""
    assert _BOUNDARY in HTML
    assert re.search(r"^const S = \{", HTML, re.M), "the mock state object is gone"
    above = HTML[: HTML.index(_BOUNDARY)]
    assert "S.config." in above, "no mock-side usage left — has the mock moved?"


def test_no_undated_claim_about_a_future_game_update():
    """Copy written the day before 1.0 shipped told the operator the update was
    'tomorrow'. It was still saying that after 1.0 landed. Undated statements in
    UI copy go stale silently — nothing fails, it just quietly lies."""
    stale = re.findall(r"(?i)\b(tomorrow's|today's|next week's)\s+[^<`\"]{0,40}update", HTML)
    assert not stale, f"time-relative copy will go stale: {stale}"


@pytest.mark.parametrize("needle", [
    "renderFindings",      # performance findings
    "followJob",           # job stream
    "data-view=\"performance\"",
])
def test_key_surfaces_are_present(needle):
    """A crude smoke check that a bad merge has not dropped a whole feature."""
    assert needle in HTML


_TEXT = CONSOLE.read_text(encoding="utf-8")


# ── the activity panels ──────────────────────────────────────────────────────
# Added after a real session: the server logged a refused login, a join, a leave
# and its own stop-saving threshold, and the console showed none of it.

def test_the_console_asks_for_activity():
    assert "/activity" in _TEXT, "the console never requests the activity endpoint"


@pytest.mark.parametrize("mount", ["o-feed", "o-disk", "o-phases", "o-diskfill"])
def test_every_activity_mount_point_exists(mount):
    """renderFeed/renderDisk/renderSavePhases each target one id. A renamed or
    missing id fails silently — the panel just stays on 'Reading the log…'."""
    assert f'id="{mount}"' in _TEXT, f"#{mount} is missing from the markup"


def test_the_disk_panel_can_show_every_state():
    """A panel that can only ever say 'Healthy' is decoration. The blocked case
    is the one that matters: below that threshold the server stops saving."""
    for state in ("warning", "blocked"):
        assert state in _TEXT, f"the disk panel has no {state} state"
    assert "STOPPED SAVING" in _TEXT, "the blocked state does not say what it means"


def test_the_phase_breakdown_distinguishes_blocking_from_writing():
    """A single total hides which part players feel."""
    assert 'data-blocking=' in _TEXT
    assert "freeze the world" in _TEXT


def test_a_refused_login_is_worded_as_a_refusal():
    """It is the event that prompted all of this and it must not read as noise."""
    assert "auth_failed" in _TEXT
    assert "wrong password" in _TEXT.lower()


# ── the player roster ────────────────────────────────────────────────────────

def test_the_players_panel_renders_a_roster():
    assert "renderRoster" in _TEXT
    assert 'class="roster"' in _TEXT


def test_the_roster_shows_both_states():
    """'active now' and a last-seen time. A roster that can only say one of
    them is a list of names."""
    assert "active now" in _TEXT
    assert "last seen" in _TEXT


def test_last_seen_is_relative_and_bounded():
    """since() must cover minutes through days, or every departed player reads
    the same."""
    for unit in ("just now", "min ago", "h ago", "d ago"):
        assert unit in _TEXT, f"since() has no {unit!r} case"


def test_the_held_socket_is_explained_rather_than_shown_as_a_wrong_number():
    """The server's leave event fires while it may still hold the socket, so
    its count has often not dropped. Printing it bare reads as a bug."""
    assert "socket is held" in _TEXT
