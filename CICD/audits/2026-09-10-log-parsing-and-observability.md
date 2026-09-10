# Record — 1.0 log parsing, observability, and what a real session exposed

**Date:** 2026-09-10 · **Server:** Lowood-AU (`l-1.0.7`, network 39, world `CrowsNest`)
**Trigger:** the first real player joined, and almost nothing the console showed was right.

> **Bottom line.** Valheim 1.0 rewrote its log and broke **five** parsers, one at a time, while
> the test suite stayed green throughout — every fixture in it was written against 0.221 output,
> so the tests agreed with the code about a format the server had stopped producing. All five are
> fixed, the formats now live in one module, and the fixtures come from a real session. Separately,
> the log was already reporting a refused login, the server's own stop-saving disk threshold and a
> five-stage save breakdown, none of which reached a screen. Those are now surfaced.

## 1. What was broken, and how it hid

| # | Broke on 1.0 | Symptom the operator saw | PR |
|---|---|---|---|
| 1 | world directory layout | world size reported `0` | #106 |
| 2 | save-completion line | `Last save —`, `A save takes —` | #108 |
| 3 | both blocking-half lines | `valheim_save_stall_seconds` stuck at `-1` | #111 |
| 4 | console gated on `localStorage` | Portal iframe showed the API-key lock screen | #107 |
| 5 | player count = connects − disconnects | `count: 0` while naming a player who was on | #109 |

```
0.221.x   World saved ( 4404.237ms )
1.0       World save (5/5) done. Total time [124ms]

0.221.x   PrepareSave: clone done in 286ms          |  ZDOExtraData.PrepareSave done in 301 ms
1.0       GetSaveClonePerChunk… [4ms]               |  …PrepareSave done [327ms]
```

**Why five and not one:** each was fixed where it was found, in a private copy. `performance.py`
had already been made dual-format — in *its own* copy — while `metrics.py` sat a build behind and
nobody checked whether the two agreed. The formats now live in `api/services/logfmt.py` and every
consumer imports them.

⚠️ **The two save "totals" are different measurements.** 0.221 reported the whole save; 1.0's
covers the write only, with the blocking prep reported separately and *before* it. Measured here:
**331 ms freeze, 101 ms write.** `124 ms` against `4404 ms` is a change of definition, not a 35×
speed-up. Stated at the top of `logfmt.py`.

## 2. Two counting traps, both real, one caused by the fix for the other

1. Player count was `Server: New peer connected` minus `RPC_Disconnect`. **A join that fails the
   password check logs a disconnect with no matching connect**, so one mistyped password offset
   the count for the rest of the session. It read `0` while naming the player who was standing in
   the world — a count and a name list that contradict each other are one inference and one
   observation, and the observation was right.
2. Trusting the server's own `now N player(s)` is **also** wrong: it counts *sockets*, and Valheim
   holds a socket open for a reconnect. Against the post-session log the first fix reported
   `1 player named Getge` with nobody on. `Destroying abandoned non persistent zdo` is the real
   "gone" signal; character state decides, and the socket tally only covers
   connected-but-not-yet-spawned.

## 3. What the log was already saying, and nobody was reading

- `Peer … has wrong password` — a refused join. Support signal *and* security signal.
- `Available space to current user: N. Saving is blocked if below: M` — **the server stops saving
  below M**, and that failure would have been completely silent. 183 GB free against a 30 MB floor.
- The five save stages, so the freeze can be separated from the write.
- `Retry join-code check` loops — nobody can connect by code while the server looks healthy.

Now on `GET /v1/activity` and the console: **Recent activity**, **Disk headroom** (against the
server's own thresholds, not an invented percentage), **save phase breakdown**, and a **player
roster** with last-seen.

## 4. Freezes, measured

```
save blocking half   median 287 ms   p90 352 ms   max 595 ms      2×/hour
Unity asset sweep    median 629 ms   p90 672 ms   max 908 ms      lands after ~every other save
```

So the worst case is **~0.95 s**, not 0.33 s. A second of frozen world is noticeable in combat.
It is **not growing** — ZDO count is pinned at 419,858 across every archived log — and there is no
server-side tunable: the ZDO prepare is a full pass over every object, paid whether or not
anything changed (proven: 0 dirty chunks, still 252–327 ms).

**The world is already 55% of the way to a 1 s freeze** (`1 s at 764,769 objects`). The new
`world-growth` finding watches for movement and deliberately refuses to answer on a short window
or a sub-0.5% change — the real world moved 419,858 → 419,854 in a day, and extrapolating that
produces a confident number about nothing.

## 5. A near-miss worth recording

Committing a real log to this **public** repo nearly published a personal Steam id. The redaction
used `\b7656\d{13}\b`; the id appears as `Steam_76561198210919477`; **`\b` does not match after an
underscore**, so it never fired. The verification then counted the *same* pattern and reported
zero — wrong in both directions, and it read as success.

`tests/test_fixture_hygiene.py` now scans every committed log for the *shapes* of identifiers —
Steam ids, base64 blobs, GUIDs, and any routable IP outside the RFC 5737 documentation ranges.
Both leak types were confirmed to fail the tests when reintroduced.

## 6. Still open

| | |
|---|---|
| **#114** | **10 relay outages in 48 h, longest 92 s** — the only finding claiming player-visible harm, and more important than anything above |
| **#115** | Rotate the server password — published in 54 public commits, and the first real login failed on it |
| *(ops)* | Every API deploy stops at `sudo systemctl restart valheim-api` — no passwordless sudo for `vdrgaming` |

## 7. Verification

**272 pytest + 20 shell + 2 browser**, all green on `main`. Every fix was confirmed to fail with
itself reverted. The UI was driven in a real browser against the real endpoint and screenshotted,
not asserted against markup. Live after deploy:

```
save_stall 0.332   save #16 froze 332 ms / wrote 101 ms
roster     Getge, last seen 10:08:57      disk ok, 183.0 GB
findings   11 registered — problem 1, watch 1, ok 9
```

That spread matters: a findings engine that only ever says OK is a noise floor, not a report.
