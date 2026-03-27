# Sprint 005 — Resilience, Backup & Crossplay

**Status:** PLANNED
**Branch:** `feature/sprint-005-resilience-backup-crossplay`
**Milestone:** Sprint 005 — Resilience, Backup & Crossplay (Gitea Milestone #21)
**Version Target:** v0.6.0
**Started:** —
**Closed:** —

---

## Goal

End-to-end verification of the non-API layers: world corruption guard, backup retention, crossplay pre-flight checks, smoke tests, nginx reverse proxy config, and systemd service.

---

## Tasks

| # | Task | Status | Issue |
|---|------|--------|-------|
| 1 | End-to-end test of world corruption guard (`guard_world`) — missing/zero-size file recovery | [ ] | |
| 2 | Verify backup retention pruning (`BACKUPS_KEEP`) in `backup-automation.sh` | [ ] | |
| 3 | Verify in-game auto-backup flags (`-saveinterval`, `-backups`, `-backupshort`, `-backuplong`) are passed at launch | [ ] | |
| 4 | PlayFab/crossplay pre-flight library verification — all required libs checked | [ ] | |
| 5 | Verify `-crossplay` launch flag behaviour when `CROSSPLAY=true` | [ ] | |
| 6 | Complete `.gitea/smoke-test.sh` coverage | [ ] | |
| 7 | nginx reverse proxy config for API | [ ] | |
| 8 | Verify `valheim-api.service` systemd unit file is correct | [ ] | |

---

## Acceptance Criteria

- [ ] Server start with missing `.db` or `.fwl` file triggers automatic restore from most recent backup
- [ ] Backup pruning correctly retains exactly `BACKUPS_KEEP` archives
- [ ] All in-game auto-backup flags appear in the server launch command
- [ ] Pre-flight aborts with clear error if PlayFab libs are missing
- [ ] Smoke test script covers: deploy, start, stats, backup, stop
- [ ] nginx config proxies API requests and handles SSL termination
- [ ] `systemctl start valheim-api` brings up the API process

---

## Notes

No new features in this sprint — this is verification and hardening of existing functionality.
