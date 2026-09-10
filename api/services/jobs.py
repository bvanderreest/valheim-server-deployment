"""Long-running actions as tracked, streamable jobs.

Replaces `subprocess.run(capture_output=True, timeout=300)`, which had two
faults that between them made the console a black box that also breaks things:

  * `capture_output=True` buffers stdout until the process exits and then
    discards it on success. The manager script narrates itself in detail —
    `[update] Taking a pre-update backup…`, `[backup] OK — 140M, integrity
    verified.` — and every line of it was thrown away. The console was left
    inferring progress from `/status` diffs, which is why a backup that took
    21 seconds could sit on "Backing up…" indefinitely.

  * `timeout=300` SIGKILLs the child at five minutes. A Valheim major-version
    update is a pre-update backup, a ~2 GB SteamCMD download and validate, then
    a start that waits up to START_TIMEOUT (900 s) for the world migration.
    Killing SteamCMD mid-write, or a migration mid-flight, is how a world gets
    corrupted.

So: `Popen` with line-wise reads, no arbitrary deadline, output retained and
fanned out to subscribers, and the stage the action has reached derived from
the lines the script already prints.

State lives in this module. That is consistent with how the API already works —
`api/auth.py` documents that the rate limiter is correct only under
`--workers 1`, and the systemd unit runs exactly that.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from typing import Optional

from ..config import settings

# Terminal states.
RUNNING, SUCCEEDED, FAILED, KILLED = "running", "succeeded", "failed", "killed"

# How many finished jobs to keep addressable. Small: this is a breadcrumb trail
# for the console, not an audit log.
MAX_JOBS = 20
# Lines retained per job. A SteamCMD validate is chatty; this is enough to hold
# a whole update with room to spare.
MAX_LINES = 4000

# A backstop, NOT a deadline. Nothing here should ever hit it — it exists so a
# genuinely wedged process cannot pin a slot forever. Comfortably longer than
# START_TIMEOUT (900s) plus a full download.
JOB_HARD_LIMIT_S = 3 * 3600

# SteamCMD and the manager's progress bar both emit ANSI. Strip it before
# matching or every pattern has to tolerate colour codes.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\r")


def strip_ansi(line: str) -> str:
    return _ANSI.sub("", line).rstrip("\n")


class Stage:
    __slots__ = ("key", "label", "state", "started_at", "ended_at", "detail", "percent")

    def __init__(self, key: str, label: str):
        self.key, self.label = key, label
        self.state = "pending"  # pending | active | done | failed | skipped
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.detail: Optional[str] = None
        self.percent: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "state": self.state,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "detail": self.detail, "percent": self.percent,
        }


# ── Stage definitions ─────────────────────────────────────────────────────────
# Each entry is (key, label, enter-pattern). Entering a stage closes every
# earlier one that is still open — the script is strictly sequential, so a later
# marker is proof the earlier work finished.
#
# Every pattern below is a string the script (or SteamCMD) ACTUALLY prints;
# they were taken from a real 1.0 update transcript, not from reading the source
# and hoping.

_STAGES: dict[str, list[tuple[str, str, str]]] = {
    "backup": [
        ("read",    "Reading world",  r"^\[backup\] Creating backup for world:"),
        ("archive", "Archiving",      r"^\[backup\] Creating .*\.tar\.gz"),
        ("verify",  "Verifying",      r"^\[backup\] OK —"),
    ],
    "stop": [
        ("signal",  "Signalling server", r"^\[stop\] SIGINT"),
        ("wait",    "Waiting for exit",  r"^\[stop\] (Timeout|Force)"),
        ("stopped", "Stopped",           r"^\[stop\] Stopped\."),
    ],
    "start": [
        ("rotate",   "Rotating log",     r"^\[rotate_log\]"),
        ("guard",    "Checking world",   r"^\[guard\]"),
        ("preflight", "Pre-flight",      r"^\[preflight\] Checking"),
        ("launch",   "Launching",        r"Valheim Server Starting|^\s*Pre-flight\s+\["),
        ("world",    "Loading world",    r"^\s*(World|Steam)\s+\["),
        ("network",  "Connecting",       r"^\s*(Network|Crossplay)\s+\["),
        ("ready",    "Ready",            r"^\s*Status:\s+Started"),
    ],
    "update": [
        ("stop",     "Stopping server",   r"^\[update\] Stopping"),
        ("backup",   "Pre-update backup", r"^\[update\] Taking a pre-update backup"),
        ("steam",    "Checking Steam",    r"^\[update\] Checking Steam connectivity"),
        ("download", "Downloading",       r"Update state \(0x[0-9a-f]+\) (downloading|preallocating)"),
        ("verify",   "Verifying install", r"Update state \(0x[0-9a-f]+\) verifying"),
        ("install",  "Installing",        r"Update state \(0x[0-9a-f]+\) committing|^Success! App"),
        ("restart",  "Restarting server", r"^\[update\] (Restarting server|Starting server)"),
        ("done",     "Done",              r"^\[update\] (Done\.|Build changed|NOTE: build id did not change)"),
    ],
}
_STAGES["restart"] = _STAGES["stop"] + _STAGES["start"]

# Lines that carry a percentage for whatever stage is active.
_PCT = [
    re.compile(r"Update state \(0x[0-9a-f]+\) [a-z ]+, progress: ([0-9.]+)"),
    re.compile(r"^\s*\S.*\[[█░ ]+\]\s+(\d+)%"),
]
# Lines worth surfacing as the active stage's one-line detail.
_DETAIL = re.compile(
    r"^\[(?:backup|update|guard|preflight|stop|rotate_log)\]\s+(.*)$|"
    r"^\s*│\s*(.*)$|"
    r"^(Success! App .*)$"
)
# A failure the script announces but which does not necessarily set a non-zero
# exit — worth marking the stage failed regardless.
_FAILMARK = re.compile(r"\bFAILED\b|^\[\w+\] (ERROR|ABORTING)|^\[update\] Error:")


class Job:
    def __init__(self, action: str, argv: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.action = action
        self.argv = argv
        self.state = RUNNING
        self.started_at = time.time()
        self.ended_at: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.error: Optional[str] = None
        self.lines: deque[str] = deque(maxlen=MAX_LINES)
        self.line_count = 0
        self.stages = [Stage(k, lbl) for k, lbl, _ in _STAGES.get(action, [])]
        self._patterns = [(k, re.compile(p)) for k, _, p in _STAGES.get(action, [])]
        self._subs: list[asyncio.Queue] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    # ── stage bookkeeping ────────────────────────────────────────────────────
    def _stage(self, key: str) -> Optional[Stage]:
        return next((s for s in self.stages if s.key == key), None)

    @property
    def active_stage(self) -> Optional[Stage]:
        return next((s for s in self.stages if s.state == "active"), None)

    def _enter(self, key: str, when: float) -> None:
        target = self._stage(key)
        if target is None or target.state in ("done", "failed"):
            return
        idx = self.stages.index(target)
        # Everything before this one must be finished — the script is sequential,
        # so a later marker is proof. Stages never reached are `skipped`, which
        # is a different claim from `done` and is shown differently.
        for s in self.stages[:idx]:
            if s.state == "active":
                s.state, s.ended_at = "done", when
            elif s.state == "pending":
                s.state = "skipped"
        if target.state == "pending":
            target.state, target.started_at = "active", when

    def _apply(self, line: str, when: float) -> None:
        for key, pat in self._patterns:
            if pat.search(line):
                self._enter(key, when)
                break
        act = self.active_stage
        if act is None:
            return
        for p in _PCT:
            if (m := p.search(line)):
                try:
                    act.percent = max(0.0, min(100.0, float(m.group(1))))
                except ValueError:
                    pass
                break
        if (m := _DETAIL.match(line)):
            d = next((g for g in m.groups() if g), None)
            if d:
                act.detail = d[:160]
        if _FAILMARK.search(line):
            act.state, act.ended_at = "failed", when

    def _finish(self, state: str, code: Optional[int], err: Optional[str] = None) -> None:
        now = time.time()
        self.state, self.exit_code, self.ended_at, self.error = state, code, now, err
        for s in self.stages:
            if s.state == "active":
                s.state, s.ended_at = ("done" if state == SUCCEEDED else "failed"), now
            elif s.state == "pending":
                s.state = "skipped"

    # ── fan-out ──────────────────────────────────────────────────────────────
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def _emit(self, event: dict) -> None:
        loop = self._loop
        if loop is None:
            return
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                pass  # loop gone; the stream is being torn down anyway

    # ── the run itself ───────────────────────────────────────────────────────
    def _run(self) -> None:
        try:
            self._proc = subprocess.Popen(
                self.argv,
                cwd=str(settings.script_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # one ordered stream; the script writes to both
                stdin=subprocess.DEVNULL,   # rollback() has a read -p; never let it block
                text=True,
                bufsize=1,                  # line buffered
                start_new_session=True,     # own process group, so a kill takes children too
            )
        except OSError as exc:
            self._finish(FAILED, None, f"could not start: {exc}")
            self._emit({"type": "end", "job": self.summary()})
            return

        deadline = time.time() + JOB_HARD_LIMIT_S
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            when = time.time()
            if when > deadline:
                self.kill("exceeded the hard limit")
                break
            for part in strip_ansi(raw).split("\n"):
                if not part.strip():
                    continue
                self.lines.append(part)
                self.line_count += 1
                self._apply(part, when)
                self._emit({"type": "line", "line": part, "at": when,
                            "stages": [s.as_dict() for s in self.stages]})

        code = self._proc.wait()
        if self.state == RUNNING:
            self._finish(SUCCEEDED if code == 0 else FAILED, code)
        self._emit({"type": "end", "job": self.summary()})

    def kill(self, why: str) -> bool:
        p = self._proc
        if p is None or p.poll() is not None:
            return False
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return False
        self._finish(KILLED, None, why)
        return True

    # ── views ────────────────────────────────────────────────────────────────
    def summary(self) -> dict:
        return {
            "id": self.id, "action": self.action, "state": self.state,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "exit_code": self.exit_code, "error": self.error,
            "line_count": self.line_count,
            "stages": [s.as_dict() for s in self.stages],
        }

    def detail(self, tail: Optional[int] = None) -> dict:
        out = self.summary()
        lines = list(self.lines)
        out["lines"] = lines[-tail:] if tail else lines
        out["truncated"] = self.line_count > len(lines)
        return out


# ── registry ──────────────────────────────────────────────────────────────────
_jobs: "deque[Job]" = deque(maxlen=MAX_JOBS)
_reg_lock = threading.Lock()


def get(job_id: str) -> Optional[Job]:
    with _reg_lock:
        return next((j for j in _jobs if j.id == job_id), None)


def recent(limit: int = 10) -> list[Job]:
    with _reg_lock:
        return list(_jobs)[-limit:][::-1]


def active_for(action: Optional[str] = None) -> Optional[Job]:
    """A running job, optionally for one action. Used to refuse a duplicate."""
    with _reg_lock:
        for j in reversed(_jobs):
            if j.state == RUNNING and (action is None or j.action == action):
                return j
    return None


def start(action: str, args: Optional[list[str]] = None,
          loop: Optional[asyncio.AbstractEventLoop] = None) -> Job:
    argv = [str(settings.manager_script), action] + list(args or [])
    job = Job(action, argv)
    job._loop = loop
    with _reg_lock:
        _jobs.append(job)
    threading.Thread(target=job._run, name=f"job-{job.id}", daemon=True).start()
    return job
