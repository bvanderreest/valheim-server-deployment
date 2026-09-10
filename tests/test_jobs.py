"""Tests for the job runner.

The runner replaced `subprocess.run(capture_output=True, timeout=300)`. Both of
those flags caused a real failure, so both have a test named after it:

  * output was discarded  -> the console could not show progress, and a backup
    that took 21 s sat on "Backing up…" forever
  * timeout=300           -> a Valheim major-version update (backup + ~2 GB
    download + validate + a migration that may take 900 s) was SIGKILLed
    mid-flight

Everything here drives a real subprocess. Mocking Popen would test the mock.
"""
import textwrap
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import jobs as J


@pytest.fixture(autouse=True)
def _clean_registry():
    J._jobs.clear()
    yield
    J._jobs.clear()


def _script(tmp_path, body: str):
    p = tmp_path / "fake-manager.sh"
    p.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    p.chmod(0o755)
    return p


def _use(monkeypatch, tmp_path, script):
    """`manager_script` and `script_dir` are read-only properties on Settings,
    so swap the whole settings object the module reads."""
    monkeypatch.setattr(J, "settings", SimpleNamespace(
        manager_script=script, script_dir=tmp_path))


def _run(monkeypatch, tmp_path, body: str, action: str = "backup", wait: float = 10.0):
    script = _script(tmp_path, body)
    _use(monkeypatch, tmp_path, script)
    job = J.start(action)
    deadline = time.time() + wait
    while job.state == J.RUNNING and time.time() < deadline:
        time.sleep(0.05)
    return job


def test_output_is_captured_line_by_line_not_discarded(monkeypatch, tmp_path):
    """The whole point: the script narrates itself and we keep every word."""
    job = _run(monkeypatch, tmp_path, """
        echo "[backup] Creating backup for world: CrowsNest"
        echo "[backup] Layout: flat"
        echo "[backup] Creating /srv/valheim/backups/world-CrowsNest-x.tar.gz…"
        echo "[backup] OK — 140M, integrity verified."
    """)
    assert job.state == J.SUCCEEDED
    assert job.exit_code == 0
    assert any("integrity verified" in l for l in job.lines)
    assert job.line_count == 4


def test_a_long_action_is_not_killed_at_five_minutes(monkeypatch, tmp_path):
    """The regression that would have corrupted a world.

    Not waiting five real minutes — asserting the runner sets no deadline
    anywhere near it, and that the only limit is the deliberate backstop.
    """
    assert J.JOB_HARD_LIMIT_S >= 3600, "a Valheim migration alone can take 900s"

    # Inspect the AST, not the text — the first version of this test matched
    # the word "timeout=300" in this module's own docstring, which explains the
    # bug. A grep-based guard that its own documentation can trip is worthless.
    import ast
    tree = ast.parse(open(J.__file__).read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = ast.unparse(node.func)
        assert fn != "subprocess.run", "run() buffers output and imposes a deadline; use Popen"
        if fn == "subprocess.Popen":
            kwargs = {k.arg for k in node.keywords}
            assert "timeout" not in kwargs, "Popen must not carry a deadline"
            assert kwargs >= {"stdout", "stderr", "stdin"}, (
                "all three streams must be set explicitly: an inherited stdin "
                "lets rollback()'s `read -p` block forever")


def test_stages_advance_from_the_lines_the_script_already_prints(monkeypatch, tmp_path):
    job = _run(monkeypatch, tmp_path, """
        echo "[backup] Creating backup for world: CrowsNest"
        echo "[backup] Creating /tmp/world-x.tar.gz…"
        echo "[backup] OK — 140M, integrity verified."
    """)
    states = {s.key: s.state for s in job.stages}
    assert states == {"read": "done", "archive": "done", "verify": "done"}


def test_a_stage_never_reached_is_skipped_not_done(monkeypatch, tmp_path):
    """'skipped' and 'done' are different claims. Marking an unreached stage
    done would tell the operator work happened that never did."""
    job = _run(monkeypatch, tmp_path, """
        echo "[backup] Creating backup for world: CrowsNest"
        echo "[backup] ERROR: tar failed."
        exit 1
    """)
    assert job.state == J.FAILED
    assert job.exit_code == 1
    by = {s.key: s.state for s in job.stages}
    assert by["read"] == "failed"
    assert by["verify"] == "skipped"


def test_steamcmd_percentages_land_on_the_active_stage(monkeypatch, tmp_path):
    job = _run(monkeypatch, tmp_path, """
        echo "[update] Checking Steam connectivity via api.steamcmd.net..."
        echo " Update state (0x61) downloading, progress: 43.21 (860M / 1990M)"
        echo " Update state (0x61) downloading, progress: 89.85 (1788M / 1990M)"
    """, action="update")
    dl = next(s for s in job.stages if s.key == "download")
    assert dl.state == "active" or dl.state == "done"
    assert dl.percent == pytest.approx(89.85)


def test_ansi_and_carriage_returns_are_stripped(monkeypatch, tmp_path):
    """SteamCMD and the manager's progress bar both emit ANSI; unstripped, every
    pattern silently stops matching."""
    assert J.strip_ansi("\x1b[0m Update state (0x61) downloading\r") == " Update state (0x61) downloading"
    job = _run(monkeypatch, tmp_path, r"""
        printf '\033[0m[backup] OK \xe2\x80\x94 140M, integrity verified.\r\n'
    """)
    assert any(l.startswith("[backup] OK") for l in job.lines), job.lines


def test_stdin_is_closed_so_a_read_prompt_cannot_hang_the_job(monkeypatch, tmp_path):
    """rollback() has a `read -r -p`. Inheriting a terminal would make it block
    forever, or take SIGTTIN and stop. DEVNULL makes read fail immediately."""
    job = _run(monkeypatch, tmp_path, """
        read -r -p "Continue? (y/N): " reply || true
        echo "did-not-hang reply='${reply:-}'"
    """, wait=6.0)
    assert job.state == J.SUCCEEDED
    assert any("did-not-hang" in l for l in job.lines)


def test_a_second_action_is_refused_while_one_is_running(monkeypatch, tmp_path):
    """Two POSTs used to yield two 202s and two subprocesses."""
    _use(monkeypatch, tmp_path, _script(tmp_path, "sleep 3\n"))
    first = J.start("backup")
    time.sleep(0.3)
    assert J.active_for() is not None
    assert J.active_for().id == first.id
    first.kill("test teardown")


def test_registry_keeps_recent_jobs_and_forgets_the_rest(monkeypatch, tmp_path):
    _use(monkeypatch, tmp_path, _script(tmp_path, "true\n"))
    ids = [J.start("backup").id for _ in range(J.MAX_JOBS + 5)]
    time.sleep(0.6)
    assert len(J.recent(J.MAX_JOBS + 10)) == J.MAX_JOBS
    assert J.get(ids[-1]) is not None
    assert J.get(ids[0]) is None


# ── HTTP surface ──────────────────────────────────────────────────────────────

def test_action_returns_a_job_id_to_follow():
    c = TestClient(app)
    r = c.post("/v1/server/backup")
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"], "without an id the console has nothing to follow"
    assert c.get(f"/v1/jobs/{body['job_id']}").status_code == 200


def test_unknown_job_is_404_with_a_useful_reason():
    c = TestClient(app)
    r = c.get("/v1/jobs/deadbeefcafe")
    assert r.status_code == 404
    assert "do not survive" in r.json()["detail"]


def test_capabilities_advertise_the_stream():
    c = TestClient(app)
    caps = c.get("/v1/capabilities").json()["capabilities"]
    assert caps["job_stream"] is True


def test_job_list_is_newest_first():
    c = TestClient(app)
    c.post("/v1/server/backup")
    time.sleep(0.4)
    c.post("/v1/server/backup")
    time.sleep(0.4)
    jobs = c.get("/v1/jobs").json()["jobs"]
    if len(jobs) >= 2:
        assert jobs[0]["started_at"] >= jobs[1]["started_at"]


def test_the_suite_never_points_at_the_real_manager_script():
    """A guard on the guard.

    If the conftest fixture ever stops applying, the suite silently starts
    running the production script — start, stop, backup, update — on whatever
    machine CI happens to be. That would not fail a test; it would just do it.
    """
    from pathlib import Path

    from api.services import jobs as jobsvc

    in_use = Path(str(jobsvc.settings.manager_script)).resolve()
    real = (Path(__file__).resolve().parents[1] / "valheim-server-manager.sh").resolve()
    assert in_use != real, "tests are wired to the REAL manager script"
    assert not str(in_use).startswith(str(real.parent) + "/valheim-server-manager")
