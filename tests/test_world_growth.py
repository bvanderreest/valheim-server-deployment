"""The world-growth finding.

`world-size` says what a save costs at today's object count. This says whether
that count is moving, because the level only becomes a problem by moving and
nothing else would notice — you would find out from someone complaining.

Measured on the real server: ~420k objects buys a ~290 ms freeze, and a Unity
asset sweep lands on top of roughly every other save for another ~650 ms. One
second of frozen world is the point a player stops calling it "a bit of lag",
which is where STALL_PAIN_MS comes from.
"""
import pytest

from api.services import findings as F


def _saves(pairs, start=1_000_000.0, step=1800.0):
    """(zdos, ms) in time order, one save every 30 minutes."""
    return [{"epoch": start + i * step, "zdos": z, "ms": ms}
            for i, (z, ms) in enumerate(pairs)]


def _find(saves, span_hours):
    return F._cfg_world_growth(saves, span_hours)


# ── refusing to answer ───────────────────────────────────────────────────────

def test_too_few_saves_is_unknown():
    """Four samples cannot support a trend claim, and saying 'steady' from them
    is worse than saying nothing because it gets believed."""
    f = _find(_saves([(419_000, 290)] * 3), 24.0)
    assert f["verdict"] == F.UNKNOWN
    assert "not enough" in f["headline"].lower()


def test_a_short_window_is_unknown_even_with_plenty_of_samples():
    """A 2-hour window extrapolated to days invents a number."""
    f = _find(_saves([(419_000 + i * 50, 290) for i in range(20)]), 2.0)
    assert f["verdict"] == F.UNKNOWN
    assert "too short" in f["headline"].lower()


def test_noise_is_not_reported_as_growth():
    """A played-in world gains and loses objects constantly. The real server
    moved 419,858 -> 419,854 in a day; extrapolating that is nonsense."""
    real = [(419_858, 252), (419_858, 264), (419_858, 256), (419_854, 289),
            (419_854, 327), (419_854, 322), (419_858, 251), (419_856, 268),
            (419_854, 301), (419_858, 275)]
    f = _find(_saves(real), 24.0)
    assert f["verdict"] == F.OK
    assert "steady" in f["headline"].lower()
    assert "objects/day" not in f["headline"], "a flat world must not be given a growth rate"


# ── the trend it exists to catch ─────────────────────────────────────────────

def test_steady_growth_toward_the_pain_point_is_raised():
    """Enough growth that a 1 s freeze arrives within a month."""
    # ~0.69 us/object, so 1 s is ~1.45M objects. From 1.4M, +20k/save over
    # 24 h of half-hourly saves is a very fast fill.
    rows = _saves([(1_400_000 + i * 4_000, 970 + i) for i in range(20)])
    f = _find(rows, 24.0)
    assert f["verdict"] in (F.PROBLEM, F.WATCH)
    assert "objects/day" in f["headline"]


def test_imminent_growth_is_a_problem_not_a_watch():
    rows = _saves([(1_400_000 + i * 8_000, 970 + i) for i in range(20)])
    f = _find(rows, 24.0)
    assert f["verdict"] == F.PROBLEM


def test_slow_growth_far_from_the_pain_point_is_ok():
    """Growing, but centuries away. Raising this would be noise."""
    rows = _saves([(419_858 + i * 60, 290) for i in range(20)])
    f = _find(rows, 24.0)
    assert f["verdict"] == F.OK


def test_a_shrinking_world_is_ok_and_says_so():
    rows = _saves([(500_000 - i * 500, 350) for i in range(20)])
    f = _find(rows, 24.0)
    assert f["verdict"] == F.OK
    assert "shrink" in f["headline"].lower()


# ── the numbers it reports ───────────────────────────────────────────────────

def test_it_reports_where_the_pain_point_actually_is():
    """Derived from THIS server's cost per object, not a constant."""
    rows = _saves([(420_000, 290)] * 10)
    ev = {r["label"]: r["value"] for r in _find(rows, 24.0)["evidence"]}
    label = next(k for k in ev if "reaches" in k)
    at = int(ev[label].split()[0].replace(",", ""))
    # 290 ms / 420k objects => 1 s at roughly 1.45M
    assert 1_400_000 < at < 1_500_000, at


def test_every_verdict_is_reachable():
    """A finding that can only ever say OK is decoration."""
    seen = {
        _find(_saves([(419_000, 290)] * 3), 24.0)["verdict"],
        _find(_saves([(419_858, 290)] * 10), 24.0)["verdict"],
        _find(_saves([(1_400_000 + i * 4_000, 970) for i in range(20)]), 24.0)["verdict"],
        _find(_saves([(1_400_000 + i * 8_000, 970) for i in range(20)]), 24.0)["verdict"],
    }
    assert {F.UNKNOWN, F.OK, F.PROBLEM} <= seen, seen
