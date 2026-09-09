"""Tests for the stall HISTORY endpoint that backs the console's timeline.

Same rule as test_metrics_stalls.py: every log line below is copied verbatim
from /srv/valheim/logs on the running server. Every log-parsing bug this repo
has shipped came from a regex written against an imagined format.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import performance as perf

# Verbatim. Note the GC block has NO timestamp of its own — that is Unity
# writing to stdout unprefixed, and it is the reason `exact` exists.
REAL_LOG = """09/09/2026 10:25:02: PrepareSave: clone done in 256ms
09/09/2026 10:25:03: PrepareSave: ZDOExtraData.PrepareSave done in 337 ms
09/09/2026 10:25:03: World save writing starting
09/09/2026 10:25:07: Saved 419858 ZDOs
09/09/2026 10:25:07: World saved ( 4404.237ms )
09/09/2026 10:25:13:  Connections 0 ZDOS:419858  sent:0 recv:0
09/09/2026 10:55:02: PrepareSave: clone done in 156ms
09/09/2026 10:55:03: PrepareSave: ZDOExtraData.PrepareSave done in 292 ms
09/09/2026 10:55:06: World saved ( 3469.851ms )
09/09/2026 10:55:13:  Connections 2 ZDOS:419858  sent:154238 recv:98211
Unloading 1 unused Assets to reduce memory usage. Loaded Objects now: 206963.
Total: 660.936870 ms (FindLiveObjects: 39.809871 ms CreateObjectMapping: 87.483483 ms MarkObjects: 532.180128 ms  DeleteObjects: 1.461416 ms)
""".splitlines(keepends=True)


def _epoch(s: str) -> float:
    """Interpret a log timestamp the way the parser does — server-local."""
    return datetime.strptime(s, "%m/%d/%Y %H:%M:%S").timestamp()


def test_parses_both_event_kinds():
    events, ctx, (first, last) = perf.parse_events(REAL_LOG)
    kinds = [e["kind"] for e in events]
    assert kinds == ["save", "save", "gc"]

    assert events[0]["ms"] == 256 + 337
    assert events[1]["ms"] == 156 + 292
    assert events[2]["ms"] == pytest.approx(660.93687)

    assert ctx["world_zdos"] == 419858
    assert ctx["loaded_objects"] == 206963
    assert ctx["players"] == 2
    assert ctx["net_sent_bytes"] == 154238
    assert first == _epoch("09/09/2026 10:25:02")
    assert last == _epoch("09/09/2026 10:55:13")


def test_stall_is_the_blocking_part_not_the_whole_save():
    """Reporting the 4.4s `World saved` figure as a freeze overstates what
    players feel by ~7x. The stall and the total are different numbers and
    both must survive to the UI."""
    events, _, _ = perf.parse_events(REAL_LOG)
    save = events[0]
    assert save["ms"] == 593
    assert save["total_ms"] == pytest.approx(4404.237)
    assert save["ms"] < save["total_ms"] / 5


def test_save_events_are_exact_and_gc_events_are_not():
    events, _, _ = perf.parse_events(REAL_LOG)
    assert [e["exact"] for e in events] == [True, True, False]
    # The GC event inherits the last timestamp seen above it.
    assert events[2]["epoch"] == _epoch("09/09/2026 10:55:13")


def test_events_are_spaced_by_the_save_interval():
    """TZ-independent: the gap between the two saves is what the log says."""
    events, _, _ = perf.parse_events(REAL_LOG)
    assert events[1]["epoch"] - events[0]["epoch"] == 30 * 60


def test_world_saved_far_from_its_preparesave_is_not_attributed():
    """A torn or interleaved log must not glue a total onto an unrelated save."""
    torn = [
        "09/09/2026 10:25:02: PrepareSave: clone done in 256ms\n",
        "09/09/2026 10:25:03: PrepareSave: ZDOExtraData.PrepareSave done in 337 ms\n",
        "09/09/2026 10:40:00: World saved ( 4404.237ms )\n",
    ]
    events, _, _ = perf.parse_events(torn)
    assert events[0]["total_ms"] is None


def test_event_before_any_timestamp_is_dropped():
    """A GC at process start has no timestamp above it. It cannot be placed on
    a timeline, and inventing a time would put a fake mark under a real
    complaint."""
    startup = [
        "Unloading 170 unused Assets to reduce memory usage. Loaded Objects now: 2417.\n",
        "Total: 3.633322 ms (FindLiveObjects: 0.181956 ms CreateObjectMapping: 0.056300 ms"
        " MarkObjects: 3.072940 ms  DeleteObjects: 0.321658 ms)\n",
    ]
    events, _, _ = perf.parse_events(startup)
    assert events == []


def test_rate_is_over_observed_span_not_requested_window(monkeypatch):
    """The bug this guards: dividing 2 saves by a 6h window gives 0.33/hour for
    a server that has actually been up 30 minutes and saved twice — a 36x
    understatement, and the console would report a stall problem as absent."""
    monkeypatch.setattr(perf, "_tail_lines", lambda n=perf.MAX_TAIL_LINES: REAL_LOG)
    out = perf.collect(6.0, now=_epoch("09/09/2026 11:00:00"))
    assert out["observed_hours"] == pytest.approx(0.5030555, abs=1e-4)
    assert out["save"]["count"] == 2
    assert out["save"]["per_hour"] == pytest.approx(3.98, abs=0.02)


def test_events_outside_the_window_are_excluded(monkeypatch):
    monkeypatch.setattr(perf, "_tail_lines", lambda n=perf.MAX_TAIL_LINES: REAL_LOG)
    out = perf.collect(0.25, now=_epoch("09/09/2026 11:00:00"))
    assert out["save"]["count"] == 1  # only the 10:55 one is inside 15 minutes


def test_no_data_reports_unknown_not_zero(monkeypatch):
    """`0 stalls per hour` and `we cannot say` are different claims. A console
    that renders the second as the first tells the operator hardware is ruled
    out when nothing was measured."""
    monkeypatch.setattr(perf, "_tail_lines", lambda n=perf.MAX_TAIL_LINES: [])
    out = perf.collect(6.0)
    assert out["save"]["count"] == 0
    assert out["save"]["per_hour"] is None
    assert out["blocked_ms_per_hour"] is None
    assert out["observed_hours"] == 0


def test_endpoint_is_key_gated(monkeypatch):
    """The stall history says who is on the server and when — it is behind the
    key like everything else, not open like /metrics."""
    from api.auth import require_api_key

    monkeypatch.setattr(perf, "_tail_lines", lambda n=perf.MAX_TAIL_LINES: REAL_LOG)
    app.dependency_overrides.pop(require_api_key, None)
    try:
        assert TestClient(app).get("/v1/performance").status_code == 401
    finally:
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"


def test_endpoint_answers_under_v1(monkeypatch):
    monkeypatch.setattr(perf, "_tail_lines", lambda n=perf.MAX_TAIL_LINES: REAL_LOG)
    c = TestClient(app)
    r = c.get("/v1/performance?hours=24")
    assert r.status_code == 200
    b = r.json()
    assert [e["kind"] for e in b["events"]] == ["save", "save", "gc"]
    assert b["save"]["p50_ms"] in (448.0, 593.0)
    assert b["context"]["world_zdos"] == 419858
    assert b["save_interval_s"] is not None


def test_window_is_bounded():
    c = TestClient(app)
    assert c.get("/v1/performance?hours=999").status_code == 422
    assert c.get("/v1/performance?hours=0").status_code == 422
