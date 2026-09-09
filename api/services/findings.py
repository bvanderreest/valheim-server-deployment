"""Derived findings — what the numbers MEAN for hardware, network and config.

The Performance view used to carry prose I wrote about how Valheim behaves.
That is a footnote, not a finding: it says the same thing whatever the server
is doing, and it goes stale the moment anything changes. This module replaces
it with judgements computed from the log, each one carrying the numbers that
produced it so the operator can disagree with the conclusion and still use the
evidence.

Three domains, because those are the three different things an operator can do
something about:

  hardware        is the machine doing the same work at the same speed?
  network         is this server's own link to the PlayFab relay healthy?
  configuration   are the settings causing freezes that need not happen?

Every finding must be able to come back **ok**. A panel that can only report
problems is a noise floor, not a report — so "ruled out" is a first-class
verdict here, and it is the one the operator is usually looking for.

Every finding must also be able to come back **unknown**. Saying "steady" from
four samples is worse than saying nothing, because it gets believed.

## The method these tests share

Almost every hardware question here is the same question: *the server did
identical work twice — did it take the same time?* This world's ZDO count is
effectively fixed, so a save is a repeatable benchmark that runs every
SAVE_INTERVAL for free. Split the window in half, compare the medians, and a
drift means the machine changed, not the workload. That is the only way a log
can distinguish "the server got slower" from "the world got bigger".
"""

from __future__ import annotations

import statistics as st
from typing import Optional

# Verdicts, worst-first when sorting for display.
PROBLEM, WATCH, OK, UNKNOWN = "problem", "watch", "ok", "unknown"
_RANK = {PROBLEM: 0, WATCH: 1, UNKNOWN: 2, OK: 3}

# A drift of this much in median time-for-identical-work is worth showing.
# Below 1.25 is inside the noise a shared host produces anyway; above 1.5 the
# machine has genuinely changed under us.
DRIFT_WATCH, DRIFT_PROBLEM = 1.25, 1.5
# Coefficient of variation. Repeating identical work on an uncontended machine
# lands within ~15%; past 30% something else is competing for the CPU.
CV_WATCH, CV_PROBLEM = 0.15, 0.30
# Minimum samples per half before a trend claim is allowed to be made at all.
MIN_HALF = 4
# Disk runway, in days, before free space is worth raising.
DISK_WATCH_DAYS, DISK_PROBLEM_DAYS = 90, 30


def _f(domain: str, id_: str, verdict: str, headline: str,
       evidence: list[tuple], method: str) -> dict:
    """Evidence rows are (label, value) or (label, value, epoch).

    An epoch is carried as a number rather than pre-formatted, because the
    server's clock is not the reader's — a time rendered here would be right
    for Brisbane and wrong for everyone in the Netherlands.
    """
    rows = []
    for r in evidence:
        rows.append({"label": r[0], "value": r[1],
                     "epoch": r[2] if len(r) > 2 else None})
    return {
        "domain": domain,
        "id": id_,
        "verdict": verdict,
        "headline": headline,
        "evidence": rows,
        "method": method,
    }


def _halves(rows: list[dict], key: str) -> tuple[Optional[float], Optional[float], int, int]:
    """Median of `key` over the first and second half of the window, by time."""
    rows = sorted(rows, key=lambda r: r["epoch"])
    vals = [r for r in rows if r.get(key) is not None]
    if len(vals) < MIN_HALF * 2:
        return None, None, len(vals), 0
    mid = len(vals) // 2
    a, b = vals[:mid], vals[mid:]
    return st.median(r[key] for r in a), st.median(r[key] for r in b), len(a), len(b)


def _drift_verdict(ratio: float) -> str:
    if ratio >= DRIFT_PROBLEM or ratio <= 1 / DRIFT_PROBLEM:
        return PROBLEM
    if ratio >= DRIFT_WATCH or ratio <= 1 / DRIFT_WATCH:
        return WATCH
    return OK


def _ms(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v/1000:.2f} s" if v >= 1000 else f"{round(v)} ms"


def _gb(b: Optional[float]) -> str:
    """Scale the unit to the number. Valheim's save-block floor is 43 MB, and
    rendering it as "0.0 GB" made the one figure that matters look like zero."""
    if b is None:
        return "—"
    b = abs(b)
    if b >= 1_000_000_000:
        return f"{b/1_000_000_000:.1f} GB"
    if b >= 1_000_000:
        return f"{b/1_000_000:.0f} MB"
    return f"{b/1_000:.0f} kB"


# ── hardware ──────────────────────────────────────────────────────────────────

def _hw_cpu(saves: list[dict]) -> dict:
    """Same work, same speed? The core hardware test."""
    a, b, na, nb = _halves(saves, "ms")
    zdos = [s["zdos"] for s in saves if s.get("zdos")]
    zspan = f"{min(zdos):,} → {max(zdos):,}" if zdos else "unknown"
    if a is None or not a:
        return _f("hardware", "cpu-drift", UNKNOWN,
                  "Not enough saves yet to say whether the machine is holding its speed.",
                  [("Saves in window", str(len(saves))),
                   ("Needed", f"{MIN_HALF*2} for a first-half / second-half comparison")],
                  "Compares the median save stall across the two halves of the window.")
    ratio = b / a
    v = _drift_verdict(ratio)
    zdo_moved = bool(zdos) and max(zdos) > min(zdos) * 1.02
    head = {
        OK: "Hardware is not the problem — identical work is taking the same time.",
        WATCH: f"Saves are taking {abs(ratio-1)*100:.0f}% {'longer' if ratio > 1 else 'less'} than earlier in the window.",
        PROBLEM: f"The machine has slowed: the same save now takes {ratio:.2f}× what it did.",
    }[v]
    if v != OK and zdo_moved:
        head += " The world also grew, so some of this is workload, not the machine."
    return _f("hardware", "cpu-drift", v, head,
              [("First half (median stall)", f"{_ms(a)} over {na} saves"),
               ("Second half", f"{_ms(b)} over {nb} saves"),
               ("Change", f"{ratio:.2f}×"),
               ("World objects across window", zspan),
               ("Threshold", f"watch at {DRIFT_WATCH:.2f}×, problem at {DRIFT_PROBLEM:.2f}×")],
              "The save stall is CPU-bound and the world size barely moves, so a save is a "
              "benchmark that repeats itself for free. Comparing its median across the two "
              "halves of the window separates 'the machine changed' from 'the world grew'.")


def _hw_jitter(saves: list[dict]) -> dict:
    """Contention shows up as spread, not as a slower average."""
    vals = [s["ms"] for s in saves if s.get("ms") is not None]
    if len(vals) < MIN_HALF * 2:
        return _f("hardware", "cpu-jitter", UNKNOWN,
                  "Not enough saves yet to measure how consistent the machine is.",
                  [("Saves in window", str(len(vals)))],
                  "Needs several repeats of the same work to have a spread at all.")
    mean, sd = st.mean(vals), st.pstdev(vals)
    cv = sd / mean if mean else 0
    v = PROBLEM if cv >= CV_PROBLEM else WATCH if cv >= CV_WATCH else OK
    head = {
        OK: "The machine is steady — the same save takes the same time every time.",
        WATCH: "Save times are more variable than a quiet machine produces.",
        PROBLEM: "Save times are erratic — something else is competing for the CPU.",
    }[v]
    return _f("hardware", "cpu-jitter", v, head,
              [("Mean stall", _ms(mean)), ("Spread (σ)", _ms(sd)),
               ("Variation", f"{cv*100:.0f}%"),
               ("Fastest / slowest", f"{_ms(min(vals))} / {_ms(max(vals))}"),
               ("Samples", str(len(vals))),
               ("Threshold", f"watch at {CV_WATCH*100:.0f}%, problem at {CV_PROBLEM*100:.0f}%")],
              "Identical work repeated on an uncontended machine lands in a tight band. A wide "
              "spread at a normal average is the signature of a noisy neighbour or a starved "
              "core — which a mean alone hides completely.")


def _hw_disk_io(saves: list[dict]) -> dict:
    """The non-blocking remainder of a save is the disk doing the writing."""
    rows = [dict(s, io=s["total_ms"] - s["ms"])
            for s in saves if s.get("total_ms") is not None and s.get("ms") is not None]
    a, b, na, nb = _halves(rows, "io")
    if a is None or not a:
        return _f("hardware", "disk-io", UNKNOWN,
                  "Not enough completed saves to judge disk write time.",
                  [("Saves with a total", str(len(rows)))],
                  "Uses `World saved (Nms)` minus the blocking part — the remainder is the write.")
    ratio = b / a
    v = _drift_verdict(ratio)
    head = {
        OK: "Disk is keeping up — write time is flat.",
        WATCH: f"World writes are taking {abs(ratio-1)*100:.0f}% {'longer' if ratio > 1 else 'less'} than earlier.",
        PROBLEM: f"Disk writes have slowed to {ratio:.2f}× — the storage path is degrading.",
    }[v]
    return _f("hardware", "disk-io", v, head,
              [("First half (median write)", f"{_ms(a)} over {na} saves"),
               ("Second half", f"{_ms(b)} over {nb} saves"),
               ("Change", f"{ratio:.2f}×"),
               ("Note", "This runs off the main thread — it is not a freeze, it is disk health")],
              "`World saved (Nms)` covers the whole save; the PrepareSave part is CPU on the main "
              "thread. The difference is the background write, which is the only pure disk signal "
              "the log offers.")


def _hw_disk_space(disk: list[dict], span_hours: float) -> dict:
    if len(disk) < 2:
        return _f("hardware", "disk-space", UNKNOWN, "No disk-space samples in this window.",
                  [], "Valheim logs free space before every save.")
    first, last = disk[0], disk[-1]
    free, floor = last["free"], last["block_below"]
    hours = max(0.01, (last["epoch"] - first["epoch"]) / 3600)
    per_day = (first["free"] - last["free"]) / hours * 24
    days = (free - floor) / per_day if per_day > 0 else None
    v = OK if days is None or days > DISK_WATCH_DAYS else (
        WATCH if days > DISK_PROBLEM_DAYS else PROBLEM)
    head = ("Disk space is not a factor." if v == OK
            else f"Free space runs out in about {days:.0f} days at the current rate.")
    return _f("hardware", "disk-space", v, head,
              [("Free now", _gb(free)),
               ("Valheim blocks saves below", _gb(floor)),
               ("Change", f"{_gb(abs(per_day))}/day {'used' if per_day > 0 else 'freed'}"),
               ("Runway", "indefinite at this rate" if days is None else f"~{days:.0f} days"),
               ("Measured over", f"{hours:.1f} h, {len(disk)} samples")],
              "Read from the `Available space` line Valheim writes before every save, so the "
              "figure is the game's own view of the volume it saves to — not the host's.")


def _hw_gc(gcs: list[dict]) -> dict:
    a, b, na, nb = _halves(gcs, "ms")
    objs = [g["objects"] for g in gcs if g.get("objects")]
    if a is None or not a:
        return _f("hardware", "gc-drift", UNKNOWN,
                  "Not enough GC pauses in this window to trend them.",
                  [("GC pauses", str(len(gcs))), ("Cadence", "roughly one an hour")],
                  "Needs several hours of log; a shorter window cannot see a trend.")
    ratio = b / a
    v = _drift_verdict(ratio)
    steady = bool(objs) and max(objs) <= min(objs) * 1.02
    head = {
        OK: "GC pauses are stable — no memory pressure building.",
        WATCH: f"GC pauses have moved {abs(ratio-1)*100:.0f}%.",
        PROBLEM: f"GC pauses have grown {ratio:.2f}× — objects are accumulating.",
    }[v]
    return _f("hardware", "gc-drift", v, head,
              [("First half (median)", f"{_ms(a)} over {na} pauses"),
               ("Second half", f"{_ms(b)} over {nb} pauses"),
               ("Change", f"{ratio:.2f}×"),
               ("Loaded objects", f"{min(objs):,} → {max(objs):,}" if objs else "unknown"),
               ("Object count", "flat" if steady else "moving")],
              "A GC pause is dominated by walking the object graph. If the pause grows while the "
              "object count does not, something is retaining references — which is the only "
              "leak signal available without attaching a profiler.")


# ── network ───────────────────────────────────────────────────────────────────

def _net_relay(incidents: list[dict], span_hours: float) -> dict:
    """This server's own link to PlayFab. NOT any player's connection."""
    if not incidents:
        return _f("network", "relay", OK,
                  "This server's link to the PlayFab relay was clean for the whole window.",
                  [("Connection failures", "0"),
                   ("Login retries", "0"),
                   ("Window", f"{span_hours:.1f} h")],
                  "Counts `Game server connected failed` and PlayFab login attempts past the "
                  "first. Both mean the SERVER could not reach the relay — which is the only "
                  "part of the network path this log can see.")
    # Cluster: anything more than five minutes from the last event is a new outage.
    groups: list[list[dict]] = []
    for i in sorted(incidents, key=lambda x: x["epoch"]):
        if groups and i["epoch"] - groups[-1][-1]["epoch"] <= 300:
            groups[-1].append(i)
        else:
            groups.append([i])
    worst = max(groups, key=len)
    dur = worst[-1]["epoch"] - worst[0]["epoch"]
    v = PROBLEM if len(groups) > 2 or dur > 120 else WATCH
    return _f("network", "relay", v,
              f"{len(groups)} relay {'outage' if len(groups) == 1 else 'outages'} on this server's "
              f"own link — the longest lasted {dur:.0f} s.",
              [("Outages", str(len(groups))),
               ("Total events", str(len(incidents))),
               ("Longest", f"{dur:.0f} s, {len(worst)} events"),
               ("Started", "", worst[0]["epoch"]),
               ("Kinds", ", ".join(sorted({i['kind'] for i in incidents})))],
              "During one of these nobody can join and crossplay traffic is disrupted — and it "
              "looks exactly like 'the server is broken' from a player's side. It is the server's "
              "uplink, not the host.")


def _net_traffic(net: list[dict], span_hours: float) -> dict:
    seen = [n for n in net if n.get("players")]
    if not seen:
        return _f("network", "traffic", UNKNOWN,
                  "Nobody has been on, so there is no traffic to judge.",
                  [("Samples with players", "0"),
                   ("Samples total", str(len(net)))],
                  "Per-player throughput comes from the periodic `Connections` line. It needs "
                  "someone actually playing.")
    first, last = seen[0], seen[-1]
    hours = max(0.01, (last["epoch"] - first["epoch"]) / 3600)
    sent = (last["sent"] - first["sent"]) / hours / 3600
    recv = (last["recv"] - first["recv"]) / hours / 3600
    peak = max(n["players"] for n in seen)
    per = sent / peak if peak else 0
    return _f("network", "traffic", OK,
              f"Peak {peak} player{'s' if peak != 1 else ''}, about "
              f"{per/1024:.1f} KB/s out each.",
              [("Sent", f"{sent/1024:.1f} KB/s"), ("Received", f"{recv/1024:.1f} KB/s"),
               ("Peak players", str(peak)),
               ("Per player (out)", f"{per/1024:.1f} KB/s"),
               ("Measured over", f"{hours:.1f} h")],
              "Valheim's own byte counters. This is what LEFT the server — it cannot see what "
              "arrived, so a player's lag with healthy figures here points at their path, not ours.")


# ── configuration ─────────────────────────────────────────────────────────────

# How far a gap may sit from the run's median and still count as the same
# cadence. Wide enough to absorb a save delayed by a busy tick, narrow enough
# that 5 min and 30 min never land in the same run.
CADENCE_TOLERANCE = 0.25


def _current_regime(gaps: list[float]) -> list[float]:
    """The most recent contiguous run of gaps that share a cadence.

    Walks backwards from the newest gap, keeping each one that sits within
    CADENCE_TOLERANCE of the run's median so far, and stops at the first that
    does not. That finds the cadence in force NOW however few samples it has —
    which a fixed count cannot: with ten taken from either side of a change,
    the median lands between the two and describes neither.
    """
    run: list[float] = []
    for g in reversed(gaps):
        if run:
            med = st.median(run)
            if abs(g - med) > CADENCE_TOLERANCE * max(g, med):
                break
        run.append(g)
    run.reverse()
    return run


def _cfg_cadence(saves: list[dict], interval_s: Optional[int]) -> dict:
    """Is the running server actually honouring SAVE_INTERVAL?

    Judged on the most recent run of gaps that SHARE a cadence, not on the
    window's median and not on a fixed count of recent gaps. Both of those were
    tried against the live server and both reported a correct setting as wrong:

      whole-window median   5 min vs a 30 min setting -> PROBLEM, because 250
                            of 260 gaps predated the change
      last 10 gaps          17.5 min vs 30 -> WATCH, because ten gaps straddled
                            the change and the median landed between the two

    A false alarm is worse than no check: it sends the operator to fix a setting
    that is already right, wearing the same authoritative chip as a real finding.

    A cadence change inside the window is itself worth saying, so it is
    reported as evidence rather than allowed to poison the verdict.
    """
    ordered = sorted(saves, key=lambda s: s["epoch"])
    gaps = [ordered[i + 1]["epoch"] - ordered[i]["epoch"] for i in range(len(ordered) - 1)]
    gaps = [g for g in gaps if g > 0]
    if not gaps or not interval_s:
        return _f("configuration", "save-cadence", UNKNOWN,
                  "Not enough saves to check the cadence against the setting.",
                  [("Saves", str(len(saves))), ("SAVE_INTERVAL", str(interval_s or "unknown"))],
                  "Compares the observed gap between saves with the configured interval.")

    recent = _current_regime(gaps)
    if len(recent) < 2:
        return _f("configuration", "save-cadence", UNKNOWN,
                  "The save cadence changed too recently to judge it yet.",
                  [("Saves at the current cadence", str(len(recent) + 1)),
                   ("SAVE_INTERVAL", f"{interval_s/60:.0f} min"),
                   ("Needed", "two gaps at the new cadence")],
                  "Only gaps at the CURRENT cadence can be compared with the current setting, "
                  "and there are not enough of them yet. Saying 'misconfigured' from a sample "
                  "that straddles the change is how a correct server gets reported as broken.")
    med = st.median(recent)
    ratio = med / interval_s
    v = OK if 0.9 <= ratio <= 1.1 else WATCH if 0.5 <= ratio <= 1.5 else PROBLEM

    earlier = gaps[:len(gaps) - len(recent)]
    changed = None
    if len(earlier) >= 3:
        emed = st.median(earlier)
        if abs(emed - med) > 0.25 * max(emed, med):
            changed = emed

    if v == OK:
        head = "Saves are landing exactly on the configured interval."
        if changed:
            head += (f" The cadence changed during this window — it was every "
                     f"{changed/60:.0f} min earlier on.")
    else:
        head = (f"Saves are landing every {med/60:.0f} min, but SAVE_INTERVAL is "
                f"{interval_s/60:.0f} min — the setting is not what is driving them.")

    ev = [("Current cadence", f"{med/60:.1f} min over the last {len(recent)} gaps"),
          ("SAVE_INTERVAL", f"{interval_s/60:.0f} min"),
          ("Ratio", f"{ratio:.2f}×")]
    if changed:
        ev.append(("Earlier in this window", f"{changed/60:.1f} min over {len(earlier)} gaps"))
    ev.append(("Gaps in window", str(len(gaps))))
    return _f("configuration", "save-cadence", v, head, ev,
              "Judged on the most recent gaps, because a window can span a config change and "
              "the older gaps then describe a setting no longer in force. If recent and "
              "configured disagree, the running server is not using the .env you are reading — "
              "the single most common reason a config change appears to do nothing.")


def _cfg_budget(saves: list[dict], gcs: list[dict], interval_s: Optional[int]) -> dict:
    if not saves:
        return _f("configuration", "freeze-budget", UNKNOWN,
                  "No saves in the window, so there is no freeze budget to attribute.",
                  [], "Multiplies the typical stall by how often the config makes it happen.")
    med = st.median(s["ms"] for s in saves)
    per_hour = 3600 / interval_s if interval_s else None
    cost = med * per_hour if per_hour else None
    gc_med = st.median(g["ms"] for g in gcs) if gcs else None
    gc_cost = gc_med if gc_med else 0  # ~1/hour, measured
    ev = [("Typical save stall", _ms(med)),
          ("Saves per hour (from config)", f"{per_hour:.1f}" if per_hour else "—"),
          ("Frozen per hour by saves", _ms(cost) if cost else "—"),
          ("Frozen per hour by GC", _ms(gc_cost) if gc_cost else "—")]
    if interval_s:
        for mins in (5, 15, 30, 60):
            if mins * 60 != interval_s:
                ev.append((f"If SAVE_INTERVAL were {mins} min",
                           f"{_ms(med * 3600 / (mins*60))}/hour frozen"))
    total = (cost or 0) + gc_cost
    v = OK if total < 3000 else WATCH if total < 8000 else PROBLEM
    return _f("configuration", "freeze-budget", v,
              f"Your settings cost about {_ms(cost)} of freeze an hour; GC adds {_ms(gc_cost)} "
              f"that no setting can remove.",
              ev,
              "The only freeze you control is how OFTEN a save happens. How LONG each one takes "
              "is the world's size, and that only shrinks by demolishing things.")


def _cfg_world(saves: list[dict]) -> dict:
    rows = [s for s in saves if s.get("zdos")]
    if not rows:
        return _f("configuration", "world-size", UNKNOWN,
                  "No ZDO count seen in this window.", [],
                  "Reads the object count Valheim reports with each save.")
    zdos = st.median(r["zdos"] for r in rows)
    med = st.median(r["ms"] for r in rows)
    per100k = med / (zdos / 100_000)
    at1s = 100_000 * (1000 / per100k)
    return _f("configuration", "world-size", OK if med < 1000 else WATCH,
              f"Each save blocks {_ms(med)} for {zdos:,.0f} objects — "
              f"{_ms(per100k)} per 100k.",
              [("World objects", f"{zdos:,.0f}"),
               ("Cost per 100k objects", _ms(per100k)),
               ("Current stall", _ms(med)),
               ("Would reach 1 s at", f"{at1s:,.0f} objects")],
              "Save stall scales with the object count, so this is the number that decides how "
              "bad a freeze gets. Building more raises it; nothing else does.")


def compute(saves: list[dict], gcs: list[dict], disk: list[dict], net: list[dict],
            incidents: list[dict], span_hours: float, interval_s: Optional[int]) -> list[dict]:
    out = [
        _hw_cpu(saves), _hw_jitter(saves), _hw_disk_io(saves),
        _hw_disk_space(disk, span_hours), _hw_gc(gcs),
        _net_relay(incidents, span_hours), _net_traffic(net, span_hours),
        _cfg_cadence(saves, interval_s), _cfg_budget(saves, gcs, interval_s),
        _cfg_world(saves),
    ]
    return sorted(out, key=lambda f: (_RANK[f["verdict"]], f["domain"], f["id"]))
