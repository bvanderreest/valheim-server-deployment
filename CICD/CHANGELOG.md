# Changelog

All notable changes to this project will be documented here.

Format: `## [vX.Y.Z] — YYYY-MM-DD · Sprint NNN`

---

<!-- Entries added by Claude during sprint completion -->

## [Unreleased] — 2026-09-10

### Fixed — Valheim 1.0 log parsing (five parsers, all silently blind)
- World directory layout, save-completion line, and both blocking-half lines (#106, #108, #111)
- Console showed the API-key lock screen when proxied through the Portal (#107)
- Player count derived from unpaired connect/disconnect events, then from a socket tally that
  outlives the player (#109)
- Formats consolidated into `api/services/logfmt.py`; every consumer imports them

### Added
- `GET /v1/activity` — typed event timeline: joins, leaves, refused logins, staged saves, disk
  headroom against the server's own stop-saving threshold (#110)
- Console: Recent activity, Disk headroom, save phase breakdown, player roster with last-seen
  (#110, #112)
- `world-growth` finding — projects the object count toward a felt freeze, and refuses to answer
  on noise (#113)
- `tests/test_fixture_hygiene.py` — shape-based scan of committed logs for real identifiers (#112)

### Notes
- ⚠️ 1.0's save "total" covers the write only; 0.221's covered the whole save. 124 ms vs 4404 ms
  is a change of definition, not a speed-up.
- Record: `CICD/audits/2026-09-10-log-parsing-and-observability.md`

---

## [v0.2.0] — 2026-03-27 · Sprint 001

Shell layer hardened and verified against the project spec.

**Files changed:**
- `valheim-server-manager.sh` — preflight_check added; start() ordering fixed; all commands audited against spec
- `backup-automation.sh` — backup fixes and verification
- `helpers.sh` — reviewed and verified
- `valheim-monitor.sh` — reviewed and verified

**Issues closed:** #5, #6, #7, #8, #9

---

## [v0.3.0-dev] — 2026-03-30 · Sprint 002 (ACTIVE)

API Uplift Phase 1 — CoreHost contract compliance and API quality improvements.
Sprint in progress; version will be finalised on merge.

**Files changed:**
- `api/models.py` — added `ConnectionInfo` model; `PlayerInfo` gains `max` field; `StatusResponse` restructured
- `api/config.py` — added `max_players`, `api_docs_enabled` settings; `cors_origins` default changed from `*` to `""`
- `api/main.py` — `/docs` and `/redoc` gated by `API_DOCS_ENABLED` setting
- `api/routes/server.py` — `connection` object in `/status`; ISO 8601 `last_save`; session-anchored player tracking; real LAN IP detection; `GET /capabilities` added

**Issues closed:** #14, #15, #16, #27, #39, #40, #41, #42

---
