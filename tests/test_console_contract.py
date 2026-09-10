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
