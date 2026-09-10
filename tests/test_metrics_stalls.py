"""Tests for the main-thread stall metrics.

These exist to answer one operational question: when a player reports lag, did
the SERVER freeze at that moment? If it did not, the problem is that player's
network — which is the argument a geographically spread group always has.

The parser is tested against REAL log lines copied from the running server,
because every log-parsing bug in this repo so far came from a regex written
against an imagined format rather than an observed one.
"""
import api.routes.metrics as met

# Verbatim from /srv/valheim/logs/valheim-server.log
REAL_LOG = """09/09/2026 09:34:13: PrepareSave: clone done in 286ms
09/09/2026 09:34:13: PrepareSave: ZDOExtraData.PrepareSave done in 301 ms
09/09/2026 09:34:13: World save writing starting
09/09/2026 09:34:17: Saved 419858 ZDOs
09/09/2026 09:34:18: World saved ( 4208.269ms )
Unloading 93784 unused Assets to reduce memory usage. Loaded Objects now: 207153.
Total: 458.769652 ms (FindLiveObjects: 51.929540 ms CreateObjectMapping: 146.191548 ms MarkObjects: 184.389735 ms  DeleteObjects: 76.256633 ms)
09/09/2026 09:44:31:  Connections 2 ZDOS:419858  sent:154238 recv:98211
""".splitlines(keepends=True)


def test_parses_real_log_lines(monkeypatch):
    monkeypatch.setattr(met, "_tail_lines", lambda n=3000: REAL_LOG)
    m = met._stall_metrics()
    # the freeze players feel: 286 + 301 ms
    assert abs(m["save_stall_seconds"] - 0.587) < 0.001
    assert abs(m["save_duration_seconds"] - 4.208269) < 0.001
    assert abs(m["gc_pause_seconds"] - 0.458769652) < 0.001
    assert m["loaded_objects"] == 207153
    assert m["world_zdos"] == 419858
    assert m["net_sent_bytes"] == 154238
    assert m["net_recv_bytes"] == 98211


def test_stall_is_smaller_than_total_save():
    """The stall is the BLOCKING part. Reporting the 4.2s total as a freeze
    would overstate what players experience by ~7x."""
    import types
    met._tail_lines = lambda n=3000: REAL_LOG
    m = met._stall_metrics()
    assert m["save_stall_seconds"] < m["save_duration_seconds"]


def test_missing_data_is_minus_one_not_zero(monkeypatch):
    """0 is a legitimate value for several of these. Returning 0 for 'not
    observed' would read as 'no stall' — a dashboard that lies."""
    monkeypatch.setattr(met, "_tail_lines", lambda n=3000: [])
    m = met._stall_metrics()
    for k, v in m.items():
        assert v == -1, f"{k} should be -1 when unobserved, got {v}"


def test_endpoint_exposes_every_gauge():
    from fastapi.testclient import TestClient
    from api.main import app
    body = TestClient(app).get("/v1/metrics").text
    for name in (
        "valheim_save_stall_seconds",
        "valheim_save_duration_seconds",
        "valheim_gc_pause_seconds",
        "valheim_loaded_objects",
        "valheim_world_zdos",
        "valheim_net_sent_bytes",
        "valheim_net_recv_bytes",
        "valheim_process_rss_bytes",
    ):
        assert f"# TYPE {name} gauge" in body, f"missing {name}"


def test_metrics_needs_no_key():
    """A scraper must not hold a credential that can stop the server."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.auth import require_api_key
    bare = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(require_api_key, None)
    try:
        assert bare.get("/v1/metrics").status_code == 200
    finally:
        app.dependency_overrides[require_api_key] = lambda: "test-api-key"


# ── World size and ZDO count across both builds ───────────────────────────────
# Valheim 1.0 moved the world from a flat `<World>.db` into a `<World>/`
# directory of .chunk files. /status was layout-aware; /metrics carried its own
# flat-only copy and silently reported 0 while /status reported 12,962,792 on
# the same server. Two implementations of one question drifted, exactly as they
# always do.

def test_metrics_world_size_matches_status_not_a_second_implementation():
    """They must be the SAME function, not two that agree today."""
    import api.routes.metrics as met
    import api.routes.server as srv

    assert met._status_world_bytes is srv._world_bytes, (
        "metrics must delegate to the /status implementation"
    )


def test_world_size_reads_a_chunked_1_0_world(tmp_path, monkeypatch):
    import api.routes.server as srv

    wl = tmp_path / "worlds_local" / "CrowsNest"
    wl.mkdir(parents=True)
    (wl / "00_00__0_1.chunk").write_bytes(b"x" * 1000)
    (wl / "14_1c__2_1.chunk").write_bytes(b"y" * 2000)
    (wl / "_main.4.db2").write_bytes(b"z" * 500)
    monkeypatch.setattr(srv.settings, "savedir", tmp_path, raising=False)
    monkeypatch.setattr(srv.settings, "world_name", "CrowsNest", raising=False)
    assert srv._world_bytes() == 3500


def test_world_size_still_reads_a_flat_0221_world(tmp_path, monkeypatch):
    """rollback() targets default_pre1_0, so the flat layout is still live."""
    import api.routes.server as srv

    wl = tmp_path / "worlds_local"
    wl.mkdir(parents=True)
    (wl / "CrowsNest.db").write_bytes(b"x" * 4242)
    monkeypatch.setattr(srv.settings, "savedir", tmp_path, raising=False)
    monkeypatch.setattr(srv.settings, "world_name", "CrowsNest", raising=False)
    assert srv._world_bytes() == 4242


def test_zdo_count_reads_both_build_formats(monkeypatch):
    """1.0 reports the count thousands-separated and lower-case, in a different
    line. Reading only the 0.221 form left world_objects at None on every
    updated server."""
    import api.routes.server as srv

    for line, expected in [
        ("09/09/2026 10:25:07: Saved 419858 ZDOs", 419858),
        ("09/10/2026 03:54:00: ZDOMan.LoadChunks - Starting to load 419,858 zdos"
         " from 20 Chunks. SessionID: 2211697597, WorldVersion: 41 [DeepNorth]", 419858),
    ]:
        monkeypatch.setattr(srv, "_tail_log", lambda n=400, _l=line: [_l])
        assert srv._world_objects() == expected, line[:60]


def test_the_old_zdo_pattern_alone_would_have_missed_1_0():
    """Names the regression."""
    import re
    old = re.compile(r"Saved (\d+) ZDOs")
    assert not old.search("ZDOMan.LoadChunks - Starting to load 419,858 zdos from 20 Chunks")
