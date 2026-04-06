# Sprint 004 — API Uplift Phase 3: Mod Management

**Status:** IN REVIEW
**Branch:** `feature/sprint-004-api-uplift-phase3`
**Milestone:** Sprint 004 — API Uplift Phase 3: Mods (Gitea Milestone #20)
**Version Target:** v0.5.0
**Started:** 2026-04-05
**Closed:** —

---

## Goal

Implement Phase 3 of the API uplift — full mod management. List, install, remove, and toggle mods via the API. All external downloads must be validated and sandboxed.

---

## Tasks

| # | Task | Status | Issue |
|---|------|--------|-------|
| 1 | `GET /mods` — list from `BepInEx/plugins/`, parse `manifest.json`, read `mods.json` inventory | [x] | |
| 2 | `POST /mods/install` — async, URL allowlist, size check, path-traversal scan, temp dir extraction, inventory update | [x] | |
| 3 | `DELETE /mods/{package_id}` — move to `trash/`, update inventory | [x] | |
| 4 | `POST /mods/{package_id}/enable` — move from `plugins_disabled/` to `plugins/` | [x] | |
| 5 | `POST /mods/{package_id}/disable` — move from `plugins/` to `plugins_disabled/` | [x] | |
| 6 | New `api/routes/mods.py` with all handlers | [x] | |
| 7 | New `api/services/mods.py` — manifest parsing, inventory management, filesystem ops | [x] | |
| 8 | Add `httpx` and `aiofiles` to `api/requirements.txt` | [x] | |
| 9 | Add mod config variables to `api/config.py` (`MOD_DIR`, `MOD_DISABLED_DIR`, `MOD_TRASH_DIR`, `MOD_ALLOWED_SOURCES`, `MOD_MAX_SIZE_MB`) | [x] | |
| 10 | Update `GET /capabilities` — set `mods: true` | [x] | |
| 11 | Unit tests — manifest parsing, URL allowlist, path-traversal rejection | [x] | |
| 12 | Integration tests — install flow (mock), removal, enable/disable | [x] | |
| 13 | Security tests — SSRF rejection, oversized archive, path traversal ZIP | [x] | |

---

## Acceptance Criteria

- [ ] `GET /mods` returns installed mods with name, version, enabled state, source, installed_at
- [ ] `POST /mods/install` accepts only `thunderstore.io` and `gcdn.thunderstore.io` source URLs
- [ ] Archives >100MB are rejected before extraction
- [ ] ZIP files containing `../` paths are rejected
- [ ] Extraction happens in a temp directory — never directly in the live plugins dir
- [ ] `DELETE /mods/{id}` moves to `trash/` (not permanent delete)
- [ ] Enable/disable correctly moves mod between `plugins/` and `plugins_disabled/`
- [ ] All 8 mod security checklist items from uplift spec pass
- [ ] `GET /capabilities` returns `"mods": true`
- [ ] `package_id` validated against a strict pattern (no arbitrary filesystem paths)

---

## Notes

Corresponds to Phase 3 of the Valheim API Uplift Specification (v1.0, 2026-03-26).
BepInEx must be installed on the server as a prerequisite for mod management to function.
