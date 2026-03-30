# Changelog

All notable changes to this project will be documented here.

Format: `## [vX.Y.Z] — YYYY-MM-DD · Sprint NNN`

---

<!-- Entries added by Claude during sprint completion -->

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
