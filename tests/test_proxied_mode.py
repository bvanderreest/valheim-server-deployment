"""The console must not show its lock screen when it is served through the Portal.

This is the Portal's central promise — "through the Portal that screen never
appears" — and it shipped broken: the console gated on localStorage, so behind
the Portal it asked for a key the user does not have, to reach an API that was
already answering.

The test is end-to-end in a real browser, because the bug lived entirely in
client-side boot logic that no request-level assertion would have caught. Both
directions are checked: unproxied MUST still lock, or this would be a way to
turn the lock screen off rather than a way to detect the Portal.
"""
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "api" / "static"
CHROME = Path.home() / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
LIBS = Path("/tmp/claude-1000/-home-coder-repos-vdrGames") / \
    "1036da3c-dd51-4715-821f-ee09b5fe13e3/scratchpad/libs/root/usr/lib/x86_64-linux-gnu"

pytestmark = pytest.mark.skipif(
    not CHROME.exists(), reason="headless chromium not present in this environment")

_STATUS = {"running": True, "server_label": "Lowood-AU", "world": "CrowsNest",
           "players": {"count": 0, "names": []}, "uptime_seconds": 1234,
           "version": "l-1.0.7", "backups": {"count": 6, "keep": 6},
           "world_size_bytes": 12962792, "last_save": None, "mods": [],
           "restart_required": False, "cpu_percent": 3.1, "mem_percent": 22.0}


def _handler(require_key: bool):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p in ("/s/test/", "/s/test/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html")
            if p == "/s/test/health":
                return self._send(200, {"status": "ok", "server_label": "Lowood-AU"})
            if p.startswith("/s/test/v1/"):
                # The Portal injects X-API-Key upstream, so a proxied console
                # reaches a key-required endpoint without sending one.
                if require_key and not self.headers.get("X-API-Key"):
                    return self._send(401, {"detail": "Invalid or missing X-API-Key"})
                if p.endswith("/status"):
                    return self._send(200, _STATUS)
                return self._send(200, {})
            self._send(404, {})
    return H


def _serve(require_key: bool):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = HTTPServer(("127.0.0.1", port), _handler(require_key))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


def _dom(port: int) -> str:
    """Load the console in a real browser and dump the DOM it settled on."""
    env = dict(os.environ)
    if LIBS.is_dir():
        env["LD_LIBRARY_PATH"] = str(LIBS)
    out = subprocess.run(
        [str(CHROME), "--headless", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=9000", "--dump-dom",
         f"http://127.0.0.1:{port}/s/test/"],
        capture_output=True, text=True, timeout=120, env=env)
    return out.stdout


def _locked(dom: str) -> bool:
    """The lock overlay is dismissed by setting the `hidden` attribute."""
    i = dom.find('id="lock"')
    assert i != -1, "the lock element is missing from the page entirely"
    tag = dom[dom.rindex("<div", 0, i):dom.index(">", i) + 1]
    return "hidden" not in tag


def test_proxied_console_skips_the_lock_screen():
    """A 200 on a key-required endpoint without a key means something upstream
    authenticated us — which is exactly what the Portal does."""
    srv, port = _serve(require_key=False)
    try:
        assert not _locked(_dom(port)), (
            "the console showed its lock screen while proxied — it is asking for "
            "a key the user does not have, to reach an API already answering")
    finally:
        srv.shutdown()


def test_unproxied_console_still_locks():
    """The other direction, and the one that stops this being a way to switch
    the lock screen off. Served directly, the API 401s without a key, so the
    console must still demand one."""
    srv, port = _serve(require_key=True)
    try:
        assert _locked(_dom(port)), (
            "the console skipped its lock screen against an API that rejects "
            "unauthenticated calls — every request would 401")
    finally:
        srv.shutdown()
