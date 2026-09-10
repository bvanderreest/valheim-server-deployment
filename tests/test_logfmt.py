"""Both save formats, from real logs.

Valheim 1.0 renamed the save-completion line and NOTHING matched it, so
`last_save` was null and `A save takes` was blank on every 1.0 server. The
existing suite stayed green throughout, because every fixture in it was written
against 0.221 output — the tests agreed with the code about a format the server
had stopped producing.

The 1.0 lines below are copied verbatim from /srv/valheim/logs on the live
server, 2026-09-10.
"""
import pytest

from api.services import logfmt

# ── verbatim from the running 1.0 server ─────────────────────────────────────
LIVE_1_0 = """09/10/2026 09:21:11: Sending message to save player profiles
09/10/2026 09:21:11: GetSaveClonePerChunk. Calculated number of actual chunk files: 19  Number of dirty chunks to save: 0 [3ms]
09/10/2026 09:21:11: PrepareSave: ZDOExtraData.PrepareSave done [264ms]
09/10/2026 09:21:11:  ### Save World Thread Started! ### 
09/10/2026 09:21:11: SaveSystem.Reload for World is done [15ms]
09/10/2026 09:21:11: World save (1/5) Cloud & Backup checks done [15ms] => Save number 12
09/10/2026 09:21:11: World save (2/5) Chunks writing done [21ms]
09/10/2026 09:21:11: World save (3/5) DB2 writing done [60ms]
09/10/2026 09:21:11: World save (4/5) FWL writing done [11ms]
09/10/2026 09:21:11: World save (5/5) done. Total time [124ms]""".splitlines()

# ── from the archived 0.221 logs ─────────────────────────────────────────────
LEGACY = "09/09/2026 10:25:07: World saved ( 4404.237ms )"


def test_the_one_completion_line_in_a_real_1_0_save_is_found():
    """Exactly one — the four intermediate stage lines are not completions, and
    counting them would multiply every save."""
    done = [l for l in LIVE_1_0 if logfmt.is_save_done(l)]
    assert len(done) == 1, f"matched {len(done)}: {done}"
    assert "(5/5) done" in done[0]


@pytest.mark.parametrize("line,expected", [
    ("09/10/2026 09:21:11: World save (5/5) done. Total time [124ms]", 124.0),
    ("09/09/2026 10:25:07: World saved ( 4404.237ms )", 4404.237),
])
def test_both_builds_report_a_total(line, expected):
    assert logfmt.save_total_ms(line) == expected


@pytest.mark.parametrize("line", [
    "09/10/2026 09:21:11: World save (3/5) DB2 writing done [60ms]",
    "09/10/2026 09:21:11: World save (1/5) Cloud & Backup checks done [15ms] => Save number 12",
    "09/10/2026 09:21:11: Sending message to save player profiles",
    "09/10/2026 09:21:11: PrepareSave: ZDOExtraData.PrepareSave done [264ms]",
])
def test_stage_lines_are_not_completions(line):
    assert not logfmt.is_save_done(line)
    assert logfmt.save_total_ms(line) is None


def test_the_timestamp_parses_as_us_order():
    """06/25 is proof: 25 cannot be a month."""
    from datetime import datetime
    m = logfmt.RE_TIMESTAMP.search("06/25/2026 10:25:07: World saved ( 1ms )")
    assert m
    dt = datetime.strptime(m.group(0), logfmt.TIMESTAMP_FORMAT)
    assert (dt.month, dt.day) == (6, 25)


# ── the endpoint fields the console actually renders ─────────────────────────

def test_status_reports_last_save_and_duration_from_a_1_0_log(tmp_path, monkeypatch):
    """`Last save —` and `A save takes —` were the operator-visible symptom.

    Both come from /status, and both were None on a 1.0 server because the
    parsers were looking for a line the build no longer writes.
    """
    log = tmp_path / "valheim-server.log"
    log.write_text("\n".join(LIVE_1_0) + "\n")

    from api.routes import server as srv
    monkeypatch.setattr(srv.settings, "_logfile", log, raising=False)

    assert srv._get_last_save() == "2026-09-10T09:21:11Z", "Last save is still blank"
    assert srv._save_seconds() == 0.12, "A save takes is still blank"


def test_metrics_reports_the_same_save_from_a_1_0_log(tmp_path, monkeypatch):
    log = tmp_path / "valheim-server.log"
    log.write_text("\n".join(LIVE_1_0) + "\n")
    from api.routes import metrics as met
    monkeypatch.setattr(met.settings, "_logfile", log, raising=False)

    assert met._stall_metrics()["save_duration_seconds"] == pytest.approx(0.124)
    # -1 is this module's "never observed"; a real age is a positive number
    assert met._last_save_age_seconds() > 0
