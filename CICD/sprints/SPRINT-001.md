# Sprint 001 — Shell Layer & Stability

**Status:** CLOSED
**Branch:** `feature/sprint-001-shell-stability`
**Milestone:** Sprint 001 — Shell Layer & Stability (Gitea Milestone #15)
**Version Target:** v0.2.0
**Started:** 2026-03-27
**Closed:** 2026-03-27

---

## Goal

Audit and complete the Bash management layer against the project spec. Verify the three-layer configuration system is fully functional. Ensure all helper scripts are working correctly.

---

## Tasks

| # | Task | Status | Issue |
|---|------|--------|-------|
| 1 | Audit all `valheim-server-manager.sh` commands against spec | [x] | #5 |
| 2 | Verify three-layer config system (config.conf → .env → modifiers.conf) | [x] | #6 |
| 3 | Review and verify `helpers.sh` | [x] | #7 |
| 4 | Review and verify `backup-automation.sh` | [x] | #8 |
| 5 | Review and verify `valheim-monitor.sh` | [x] | #9 |

---

## Acceptance Criteria

- [x] All `valheim-server-manager.sh` commands (deploy, start, stop, restart, update, backup, stats, logs) behave as specified in `project.md`
- [x] Three-layer config system loads and overrides correctly
- [x] `backup-automation.sh` runs cleanly via cron
- [x] `valheim-monitor.sh` outputs correct plain text and JSON
- [x] No regressions from existing functionality

---

## Notes

Foundation sprint. Establishes a verified baseline before API uplift work begins in Sprint 002.
