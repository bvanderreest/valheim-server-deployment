# Valheim-Server-Deployment · CI/CD & Sprint Tracking

> Central directory for all sprint planning, issue tracking, pipeline status,
> versioning, and audit records. Everything that affects the product lifecycle
> lives here.

---

## Directory Structure

```
CICD/
├── README.md                      ← This file — conventions and index
├── CHANGELOG.md                   ← Versioned history of every release
│
├── sprints/
│   ├── SPRINT-001.md              ← Add sprint files as sprints are created
│
├── audits/                        ← Immutable review records (UX, security, dependency)
│
└── pipeline/
    └── CI-STATUS.md               ← CI/CD pipeline health, deploy log, environment checklist
```

---

## Conventions

### Sprint Lifecycle

```
PLANNED → ACTIVE → IN REVIEW → CLOSED
```

- A sprint file is created before work begins and locked (no edits to past sprints)
- Each sprint has a version target, goal statement, and a task table
- Tasks use the status column: `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` cancelled
- When a sprint closes, update its status header and record the actual close date

### Sprint Git Workflow — MANDATORY

**Each sprint runs on its own branch. `main` is never committed to directly.**

| Step | Who | Action |
|------|-----|--------|
| Before sprint work begins | Claude | `git checkout -b feature/sprint-NNN-<slug>` |
| During sprint | Claude | Commits on feature branch only |
| Sprint tasks complete | Claude | Push branch, set sprint to `IN REVIEW`, stop |
| Validation | **Human** | Review acceptance criteria on the branch |
| Merge to main | **Human** | Merges PR on Gitea after validation |
| Close sprint | **Human** | Sets sprint Status to `CLOSED`, closes verified issues |

> Claude must never merge to `main`, rebase onto `main`, or push to `main`.
> Sprint completion is only confirmed by a real person.

Branch naming: `feature/sprint-NNN-<slug>` (e.g. `feature/sprint-001-foundation`)

### Issue Register

- All issues tracked in Gitea Issues (milestones correspond to sprints)
- Status: `Open` · `In Progress` · `Review` · `Blocked` · `Closed`
- Closed issues are never deleted — they form the audit trail

### Versioning (SemVer)

```
MAJOR.MINOR.PATCH
```

- `PATCH` — bug fix, copy tweak, style adjustment
- `MINOR` — new feature or page, no breaking schema change
- `MAJOR` — breaking change, auth change, or full replacement

Current version: **v0.1.0**

### Changelog Discipline

Every change recorded in `CHANGELOG.md` must include:
- Version bump
- Date
- Sprint reference
- Files changed (list)
- Linked issue IDs (if applicable)

### Audit Records

Any non-trivial review (UX audit, security review, dependency audit) gets its own
file in `audits/` named `YYYY-MM-DD-<type>.md`. These are immutable once written.

---

## Quick Reference — Current Sprint

**Sprint 002 — API Uplift Phase 1: Reshaping + Capabilities**
Target: v0.3.0 · Status: ACTIVE
Branch: `feature/sprint-002-api-uplift-phase1`

---

## Product Roadmap

| Sprint | Goal | Version | Status |
|--------|------|---------|--------|
| 001 | Shell Layer & Stability | v0.2.0 | CLOSED |
| 002 | API Uplift Phase 1: Reshaping + Capabilities | v0.3.0 | ACTIVE |
| 003 | API Uplift Phase 2: Config Management | v0.4.0 | PLANNED |
| 004 | API Uplift Phase 3: Mod Management | v0.5.0 | PLANNED |
| 005 | Resilience, Backup & Crossplay | v0.6.0 | PLANNED |
| 006 | Documentation & Release | v1.0.0 | PLANNED |
