# Sprint 003 — API Uplift Phase 2: Config Management

**Status:** IN REVIEW
**Branch:** `feature/sprint-003-api-uplift-phase2`
**Milestone:** Sprint 003 — API Uplift Phase 2: Config (Gitea Milestone #19)
**Version Target:** v0.4.0
**Started:** 2026-04-05
**Closed:** —

---

## Goal

Implement Phase 2 of the API uplift — server configuration read and write via the API. All writes must be atomic, backed up, validated, and must never expose API secrets.

---

## Tasks

| # | Task | Status | Issue |
|---|------|--------|-------|
| 1 | API lifecycle in `valheim-server-manager.sh` — co-start/stop, stats section, usage reference | [x] | #60 |
| 2 | `GET /config` — read `.env`, mask `password`, apply exclusion list | [ ] | #43 |
| 3 | `PATCH /config` — validate editable keys, atomic write, file lock, backup `.env.bak.<ts>` | [ ] | #43 |
| 4 | New `api/routes/config.py` with both handlers | [ ] | #43 |
| 5 | Config read/write helpers + exclusion list in `api/config.py` | [ ] | #43 |
| 6 | New Pydantic models: `ConfigResponse`, `ConfigUpdateRequest`, `ConfigUpdateResponse` | [ ] | #43 |
| 7 | Update `GET /capabilities` — set `config: true` | [ ] | #43 |
| 8 | Unit tests — exclusion, masking, validation, out-of-range rejection | [ ] | #43 |
| 9 | Integration tests — config round-trip, backup creation | [ ] | #43 |
| 10 | Security tests — excluded key write rejection, no path leak in errors | [ ] | #43 |
| 11 | `GET /metrics` — Prometheus text format, unauthenticated | [x] | #26 |

---

## Acceptance Criteria

- [ ] `GET /config` never returns `API_KEYS`, `API_ENABLED`, `API_HOST`, `API_PORT`, `CORS_ORIGINS`, `LOG_DIR`
- [ ] `password` field is masked as `"****"` in `GET /config`
- [ ] `PATCH /config` rejects any key not in `editable_keys` with HTTP 400
- [ ] `.env` writes use atomic rename (temp file → rename)
- [ ] `.env` writes use file locking
- [ ] `.env.bak.<timestamp>` created before every write; max 10 retained
- [ ] Sensitive values never appear in API logs
- [ ] All 8 config security checklist items from uplift spec pass
- [ ] `GET /capabilities` returns `"config": true`

---

## Notes

Corresponds to Phase 2 of the Valheim API Uplift Specification (v1.0, 2026-03-26).
Security considerations: exclusion-list approach (deny by default, not allow-list) is mandatory.
