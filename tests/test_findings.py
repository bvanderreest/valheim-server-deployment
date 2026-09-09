"""Tests for the derived findings.

The findings replaced hand-written prose about how Valheim behaves. Prose could
only ever be wrong in one direction; a computed judgement can be wrong in
several, and the dangerous one is a verdict that cannot change. So the first
thing tested here is that **every verdict is reachable** — an "ok" that is
always "ok" is not a finding, it is a decoration.
"""
import pytest

from api.services import findings as F
from api.services import performance as perf


def _saves(vals, start=1_000_000.0, gap=1800.0, zdos=419858, total=4200.0):
    return [{"kind": "save", "epoch": start + i * gap, "ms": float(v), "exact": True,
             "total_ms": total, "objects": None, "zdos": zdos}
            for i, v in enumerate(vals)]


def _gcs(vals, start=1_000_000.0, gap=3600.0, objs=206963):
    return [{"kind": "gc", "epoch": start + i * gap, "ms": float(v), "exact": False,
             "total_ms": None, "objects": objs, "zdos": None}
            for i, v in enumerate(vals)]


def _find(out, id_):
    return next(f for f in out if f["id"] == id_)


# ── the verdicts must all be reachable ────────────────────────────────────────

def test_cpu_drift_reports_ok_when_the_machine_is_steady():
    f = F._hw_cpu(_saves([500, 510, 495, 505, 500, 498, 502, 505]))
    assert f["verdict"] == F.OK
    assert "not the problem" in f["headline"]


def test_cpu_drift_reports_a_problem_when_the_machine_slows():
    f = F._hw_cpu(_saves([500, 500, 500, 500, 900, 950, 920, 940]))
    assert f["verdict"] == F.PROBLEM
    assert "1.8" in f["headline"] or "slowed" in f["headline"]


def test_cpu_drift_says_unknown_rather_than_guessing_from_three_saves():
    """The failure that matters: 'steady' from a tiny sample gets believed."""
    f = F._hw_cpu(_saves([500, 510, 495]))
    assert f["verdict"] == F.UNKNOWN
    assert f["evidence"][0]["value"] == "3"


def test_cpu_drift_says_when_the_world_grew_too():
    """A slowdown that is really the world getting bigger must not be reported
    as the machine degrading."""
    rows = _saves([500, 500, 500, 500, 900, 950, 920, 940])
    for r in rows[4:]:
        r["zdos"] = 800000
    f = F._hw_cpu(rows)
    assert "world also grew" in f["headline"]


def test_jitter_catches_contention_a_mean_would_hide():
    """Same mean, wildly different spread — the case an average cannot see."""
    steady = F._hw_jitter(_saves([500, 500, 500, 500, 500, 500, 500, 500]))
    erratic = F._hw_jitter(_saves([200, 800, 250, 750, 300, 700, 220, 780]))
    assert steady["verdict"] == F.OK
    assert erratic["verdict"] == F.PROBLEM
    assert "competing for the CPU" in erratic["headline"]


def test_disk_io_uses_the_non_blocking_remainder():
    slow = _saves([500] * 8, total=4200.0)
    for r in slow[4:]:
        r["total_ms"] = 9000.0
    f = F._hw_disk_io(slow)
    assert f["verdict"] == F.PROBLEM
    assert "storage path" in f["headline"]


def test_disk_space_scales_its_units():
    """Valheim's save-block floor is 43 MB. Rendered as GB it reads as zero —
    which is the one number on that row that must not look like nothing."""
    disk = [{"epoch": 0.0, "free": 200_000_000_000, "block_below": 43_101_570},
            {"epoch": 86400.0, "free": 199_900_000_000, "block_below": 43_101_570}]
    f = F._hw_disk_space(disk, 24)
    floor = next(e for e in f["evidence"] if "blocks saves" in e["label"])
    assert floor["value"] == "43 MB"


def test_disk_space_flags_a_volume_that_is_filling():
    disk = [{"epoch": 0.0, "free": 20_000_000_000, "block_below": 43_101_570},
            {"epoch": 86400.0, "free": 18_000_000_000, "block_below": 43_101_570}]
    f = F._hw_disk_space(disk, 24)
    assert f["verdict"] in (F.WATCH, F.PROBLEM)
    assert "days" in f["headline"]


# ── network ───────────────────────────────────────────────────────────────────

def test_relay_reports_ok_with_no_incidents():
    """The all-clear must be reachable, or the panel is a noise floor."""
    f = F._net_relay([], 6.0)
    assert f["verdict"] == F.OK
    assert f["evidence"][0]["value"] == "0"


def test_relay_clusters_a_burst_into_one_outage():
    """Six failures over 92 seconds is ONE outage, not six. Counting events
    instead of outages turns a single blip into an emergency."""
    burst = [{"epoch": 1000.0 + d, "kind": "relay-lost"}
             for d in (0, 7, 25, 40, 60, 92)]
    f = F._net_relay(burst, 6.0)
    assert f["evidence"][0]["value"] == "1"     # outages
    assert f["evidence"][1]["value"] == "6"     # raw events
    assert "92 s" in f["headline"]


def test_relay_outage_time_is_sent_as_an_epoch_not_a_string():
    """The server is in AU and half the group is not — a time formatted here
    would be right for one of them."""
    f = F._net_relay([{"epoch": 1788869226.0, "kind": "relay-lost"}], 6.0)
    started = next(e for e in f["evidence"] if e["label"] == "Started")
    assert started["epoch"] == 1788869226.0


def test_traffic_is_unknown_rather_than_zero_when_nobody_played():
    f = F._net_traffic([{"epoch": 0.0, "players": 0, "sent": 0, "recv": 0}], 6.0)
    assert f["verdict"] == F.UNKNOWN
    assert "Nobody has been on" in f["headline"]


# ── configuration ─────────────────────────────────────────────────────────────

def test_cadence_catches_a_setting_that_is_not_being_applied():
    """The most common reason a config change 'does nothing': the running
    server is not reading the .env you edited."""
    f = F._cfg_cadence(_saves([500] * 6, gap=300), interval_s=1800)
    assert f["verdict"] == F.PROBLEM
    assert "not what is driving them" in f["headline"]


def test_cadence_is_ok_when_saves_match_the_setting():
    f = F._cfg_cadence(_saves([500] * 6, gap=1800), interval_s=1800)
    assert f["verdict"] == F.OK


def test_budget_quantifies_the_lever_at_other_intervals():
    f = F._cfg_budget(_saves([600] * 6, gap=1800), _gcs([630] * 3), interval_s=1800)
    labels = {e["label"]: e["value"] for e in f["evidence"]}
    assert labels["Saves per hour (from config)"] == "2.0"
    assert "If SAVE_INTERVAL were 5 min" in labels
    # 600ms twelve times an hour is 7.2s — the state this server was in.
    assert "7.20 s" in labels["If SAVE_INTERVAL were 5 min"]


def test_world_size_projects_when_the_stall_reaches_a_second():
    f = F._cfg_world(_saves([550] * 6, zdos=419858))
    labels = {e["label"]: e["value"] for e in f["evidence"]}
    assert labels["World objects"] == "419,858"
    assert labels["Would reach 1 s at"] == "763,378 objects"


# ── the whole set ─────────────────────────────────────────────────────────────

def test_compute_returns_all_three_domains_worst_first():
    out = F.compute(_saves([500] * 8), _gcs([600] * 8), [], [],
                    [{"epoch": 1000.0, "kind": "relay-lost"}], 6.0, 1800)
    assert {f["domain"] for f in out} == {"hardware", "network", "configuration"}
    ranks = [F._RANK[f["verdict"]] for f in out]
    assert ranks == sorted(ranks), "worst findings must sort first"


def test_every_finding_carries_evidence_and_a_method():
    """A verdict with no numbers under it is prose again — which is the thing
    this module exists to replace."""
    out = F.compute(_saves([500] * 8), _gcs([600] * 8),
                    [{"epoch": 0.0, "free": 2_000_000_000, "block_below": 43_101_570},
                     {"epoch": 3600.0, "free": 1_999_000_000, "block_below": 43_101_570}],
                    [{"epoch": 0.0, "players": 2, "sent": 1000, "recv": 900},
                     {"epoch": 3600.0, "players": 2, "sent": 900000, "recv": 800000}],
                    [], 6.0, 1800)
    for f in out:
        assert f["method"], f"{f['id']} has no method"
        assert f["verdict"] in (F.OK, F.WATCH, F.PROBLEM, F.UNKNOWN)
        if f["verdict"] != F.UNKNOWN:
            assert f["evidence"], f"{f['id']} states a verdict with no evidence"


# ── against the real log shapes ───────────────────────────────────────────────

REAL = """09/08/2026 13:24:29: Available space to current user: 183901323264. Saving is blocked if below: 43101570 bytes. Warnings are given if below: 86203140
09/08/2026 13:24:29: PrepareSave: clone done in 226ms
09/08/2026 13:24:30: PrepareSave: ZDOExtraData.PrepareSave done in 296 ms
09/08/2026 13:24:30: World save writing starting
09/08/2026 13:24:34: Saved 419858 ZDOs
09/08/2026 13:24:34: World saved ( 4657.204ms )
09/08/2026 22:07:06: Game server connected failed
09/08/2026 22:07:13: Game server connected failed
09/09/2026 01:08:41: Sending PlayFab login request (attempt 3)
09/09/2026 01:08:42: Sending PlayFab login request (attempt 1)
09/09/2026 08:22:23:  Connections 2 ZDOS:419858  sent:154238 recv:98211
""".splitlines(keepends=True)


def test_parses_every_signal_the_findings_need():
    p = perf.parse_all(REAL)
    save = [e for e in p["events"] if e["kind"] == "save"][0]
    assert save["ms"] == 226 + 296
    assert save["zdos"] == 419858, "workload must be attached or drift is unattributable"
    assert save["total_ms"] == pytest.approx(4657.204)
    assert p["disk"][0]["free"] == 183901323264
    assert p["disk"][0]["block_below"] == 43101570
    assert [i["kind"] for i in p["incidents"]] == ["relay-lost", "relay-lost", "playfab-retry"]
    assert p["net"][0]["players"] == 2 and p["net"][0]["sent"] == 154238


def test_first_login_attempt_is_not_an_incident():
    """`attempt 1` is the normal path. Counting it would report an outage on
    every clean start."""
    p = perf.parse_all(["09/09/2026 01:08:42: Sending PlayFab login request (attempt 1)\n"])
    assert p["incidents"] == []
