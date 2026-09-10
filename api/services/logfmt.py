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
