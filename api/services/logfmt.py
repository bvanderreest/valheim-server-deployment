"""One place that knows what Valheim's log lines look like.

Valheim 1.0 rewrote the save lines and this is the THIRD parser to break on it
(after the PrepareSave pair and the world-directory layout). Each was fixed
where it was found, so the next rewrite would have broken a fourth. The formats
live here now, and every consumer imports them.

The save-completion line, both builds:

    0.221.x   09/09/2026 10:25:07: World saved ( 4404.237ms )
    1.0       09/10/2026 09:21:11: World save (5/5) done. Total time [124ms]

⚠️ These two numbers are NOT the same measurement. In 0.221 the figure was the
whole save, dominated by writing one monolithic .db. In 1.0 saving is chunked
and staged, and "Total time" covers stages 1–5 — the write — with the blocking
PrepareSave work reported separately and BEFORE it. A 1.0 total of 124ms against
a 0.221 total of 4404ms is a change of definition, not a 35x speed-up, and
anything trending one against the other is comparing different things.
"""

from __future__ import annotations

import re

# Group 1 = 0.221 total, group 2 = 1.0 total. Exactly one ever matches.
RE_SAVE_DONE = re.compile(
    r"World saved \(\s*([0-9.]+)\s*ms\s*\)"                 # 0.221.x
    r"|World save \(5/5\) done\. Total time \[\s*([0-9.]+)\s*ms\s*\]"  # 1.0
)

# Cheap pre-filter for "did a save finish on this line", for the hot paths that
# scan a whole file before caring about the number.
SAVE_DONE_HINTS = ("World saved", "World save (5/5) done")

# The timestamp Valheim stamps on every line. US order — proven by archived
# entries like 06/25/2026, where 25 cannot be a month.
RE_TIMESTAMP = re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}")
TIMESTAMP_FORMAT = "%m/%d/%Y %H:%M:%S"


def is_save_done(line: str) -> bool:
    """True if this line marks a completed world save, on either build."""
    return any(h in line for h in SAVE_DONE_HINTS)


def save_total_ms(line: str) -> float | None:
    """The save's reported total in milliseconds, or None if not such a line.

    See the module docstring before trending this across the 1.0 boundary.
    """
    m = RE_SAVE_DONE.search(line)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ── the rest of the vocabulary ───────────────────────────────────────────────
# Everything below was in a real session's log and surfaced nowhere. The one
# that prompted this: a player failed the password check, was thrown out, and
# the only trace was a line nobody read.

RE_NOW_PLAYERS = re.compile(r"now (\d+) player\(s\)")
RE_CONNECTIONS = re.compile(r"\bConnections (\d+) ZDOS:(\d+)\s+sent:(\d+) recv:(\d+)")

RE_JOINED = re.compile(r'Player joined server "([^"]*)".*?now (\d+) player\(s\)')
RE_LEFT = re.compile(r'Player connection lost server "([^"]*)".*?now (\d+) player\(s\)')

# A rejected join. The peer id is PlayFab's — as much identity as the server
# has before authentication, but enough to tell one person retrying from
# several people trying.
RE_AUTH_FAILED = re.compile(r"Peer (\S+) has wrong password")

# "<name> : <zdo>:<n>"; 0:0 is a character with no ZDO — logged out or dead.
RE_ZDOID = re.compile(r"Got character ZDOID from (.+?) : (-?\d+):(-?\d+)")

# ⭐ The server polices its own free space and states BOTH thresholds on every
# save. Below `blocked` IT STOPS SAVING. Nothing here read it.
RE_DISK = re.compile(
    r"Available space to current user: (\d+)\. "
    r"Saving is blocked if below: (\d+) bytes\. "
    r"Warnings are given if below: (\d+)")

# The five save stages, 1.0 only. `Save number` is monotonic, so a stage 1 with
# no matching stage 5 is a save that did not finish.
RE_SAVE_STAGE = re.compile(
    r"World save \((\d)/5\) (.+?) \[\s*([0-9.]+)\s*ms\s*\]"
    r"(?:\s*=> Save number (\d+))?")
RE_PREPARE_ZDO = re.compile(r"PrepareSave: ZDOExtraData\.PrepareSave done \[\s*(\d+)\s*ms\s*\]")
RE_PREPARE_CHUNKS = re.compile(
    r"GetSaveClonePerChunk\..*?actual chunk files: (\d+)\s+"
    r"Number of dirty chunks to save: (\d+) \[\s*(\d+)\s*ms\s*\]")

# Join-code lifecycle. A retry loop here means nobody can connect by code even
# though the server is up and perfectly healthy.
RE_SESSION_REGISTERED = re.compile(r'Session "([^"]*)" registered with join code (\d+)')
RE_SESSION_ACTIVE = re.compile(
    r'Session "([^"]*)" with join code (\d+) and IP (\S+) is active with (\d+) player\(s\)')
RE_JOINCODE_RETRY = re.compile(r"Retry join-code check (\d+)")

RE_WORLD_LOAD = re.compile(r"ZNet\.LoadWorld: (\S+) \(([^)]*)\), save number (\d+)")

# When a player drops, Valheim may HOLD THE SOCKET for a reconnect window — and
# during it `now N player(s)` still counts them. The character's ZDO being
# destroyed is the signal that they are really gone.
RE_KEEP_SOCKET = re.compile(r"Keep socket for (\S+), try to reconnect before timeout")
RE_ZDO_ABANDONED = re.compile(
    r"Destroying abandoned non persistent zdo (-?\d+:-?\d+) owner (-?\d+)")
