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
