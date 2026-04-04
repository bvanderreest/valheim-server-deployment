# Sprint 002 — API Uplift Phase 1: Reshaping + Capabilities

**Status:** IN REVIEW
**Branch:** `feature/sprint-002-api-uplift-phase1`
**Milestone:** Sprint 002 — API Uplift Phase 1 (Gitea Milestone #18)
**Version Target:** v0.3.0
**Started:** 2026-03-30
**Closed:** —

---

## Goal

Implement Phase 1 of the Unified Game Server API uplift. Additive changes only — reshape existing endpoint responses and add the `GET /capabilities` discovery endpoint. No breaking changes to existing consumers.

---

## Tasks

| # | Task | Status | Issue |
|---|------|--------|-------|
| 1 | `GET /status` — add `connection` object, `players.max`, ISO 8601 `last_save`, `extras`, `_deprecated` block | [x] | #39 #40 #41 |
| 2 | `GET /logs` — wrap response in `{ lines, count, log_file }` | [x] | |
| 3 | `GET /logs/stream` — structured SSE `{ line, timestamp }` per event | [x] | |
| 4 | `POST /server/{action}` — add `action` field to response | [x] | |
| 5 | `GET /capabilities` — new endpoint, static response (`config: false, mods: false`) | [x] | #42 |
| 6 | Update Pydantic models for all changed responses | [x] | |
| 7 | Unit tests — response shape, backward-compatibility, ISO 8601 date format | [x] | |

---

## Acceptance Criteria

- [x] `GET /status` returns unified shape: `connection` object, `players.max`, ISO 8601 `last_save`, `_deprecated` block with legacy fields preserved
- [x] `GET /logs` returns `{ lines: [...], count: N, log_file: "..." }`
- [x] `GET /logs/stream` SSE events are `data: {"line": "...", "timestamp": "..."}`
- [x] `POST /server/{action}` response includes `"action": "<action_name>"`
- [x] `GET /capabilities` returns correct capability set (`config: false, mods: false`)
- [x] All existing consumers continue to work (top-level legacy fields still present in `/status`)
- [x] Unit tests pass (21/21)

---

## Notes

Corresponds to Phase 1 of the Valheim API Uplift Specification (v1.0, 2026-03-26).
