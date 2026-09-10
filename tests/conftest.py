"""Shared test setup.

Two pieces of module-level state make this suite order-dependent unless it is
reset between tests, and an order-dependent test is worse than no test — it
fails for reasons unrelated to the code under test:

1. `api.auth._auth_failures` — a real, deliberate rate limiter (5 failed auth
   attempts per IP per 15 minutes). Every test that asserts a 401 records a
   failure, so after five of them across the suite the next one gets 429 and
   the failure looks like broken auth. It is not: it is the rate limiter
   working exactly as designed.

2. `app.dependency_overrides` — several tests remove the auth override to check
   the unauthenticated path, and a test that fails mid-way would leave it
   removed for everything after it.
"""
import pytest

from api.auth import require_api_key
from api.main import app

TEST_KEY = "test-api-key"


@pytest.fixture(autouse=True)
def _isolate_auth_state():
    import api.auth as auth

    auth._auth_failures.clear()
    app.dependency_overrides[require_api_key] = lambda: TEST_KEY
    yield
    auth._auth_failures.clear()
    app.dependency_overrides[require_api_key] = lambda: TEST_KEY


@pytest.fixture(autouse=True)
def _no_real_manager_script(tmp_path_factory):
    """No test may execute the real valheim-server-manager.sh.

    `POST /server/{action}` now spawns a tracked subprocess. Left alone, the
    suite would run the PRODUCTION script — start, stop, backup, update — against
    whatever machine the tests happen to be on. That was already true of the old
    `subprocess.run` path; the job runner just made it visible by keeping the
    processes around.

    Point the runner at a harmless stand-in that prints plausible stage lines,
    and clear the registry between tests so one test's running job cannot make
    the next one's action return 409.
    """
    from types import SimpleNamespace

    from api.services import jobs as jobsvc

    d = tmp_path_factory.mktemp("fake-manager")
    script = d / "valheim-server-manager.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        'echo "[${1:-noop}] stand-in for tests — the real script is never run here"\n'
        "exit 0\n"
    )
    script.chmod(0o755)

    real = jobsvc.settings
    jobsvc.settings = SimpleNamespace(manager_script=script, script_dir=d)
    jobsvc._jobs.clear()
    yield
    for j in list(jobsvc._jobs):
        if j.state == jobsvc.RUNNING:
            j.kill("test teardown")
    jobsvc._jobs.clear()
    jobsvc.settings = real
