#!/usr/bin/env bash
# .gitea/setup-labels-milestones.sh
#
# BOOTSTRAP SCRIPT — run once after creating the repo to provision labels and
# seed the initial milestones. Re-run to add new labels (idempotent).
#
# After bootstrap, ongoing milestone creation is handled by Claude Code via the
# Gitea API as part of sprint planning (see CLAUDE.md → "When Starting a New Sprint").
# Labels rarely change, but if you add new ones, add them here and re-run.
#
# Prerequisites:
#   - GITEA_URL and GITEA_TOKEN set in environment (or .env.local)
#   - curl and jq installed
#
# Usage:
#   source .env.local && bash .gitea/setup-labels-milestones.sh
#
#   Or with explicit values:
#   GITEA_URL=http://localhost:3000 GITEA_REPO=michael/galera GITEA_TOKEN=xxx bash .gitea/setup-labels-milestones.sh
#
#   Or override repo as argument:
#   bash .gitea/setup-labels-milestones.sh michael/galera

set -euo pipefail

# --- Config ---
REPO="${1:-${GITEA_REPO:?Set GITEA_REPO or pass owner/repo as argument}}"
API="${GITEA_URL:?Set GITEA_URL}/api/v1/repos/${REPO}"
AUTH="Authorization: token ${GITEA_TOKEN:?Set GITEA_TOKEN}"
CT="Content-Type: application/json"

# --- Helpers ---
create_label() {
  local name="$1" colour="$2" description="$3"

  # Check if label already exists (case-insensitive search)
  existing=$(curl -s -H "$AUTH" "${API}/labels" | jq -r --arg n "$name" '.[] | select(.name == $n) | .name')
  if [ -n "$existing" ]; then
    echo "  ✓ Label already exists: $name"
    return
  fi

  curl -s -X POST -H "$AUTH" -H "$CT" "${API}/labels" \
    -d "{\"name\":\"${name}\",\"color\":\"${colour}\",\"description\":\"${description}\"}" \
    | jq -r '"  + Created label: \(.name) (\(.id))"'
}

create_milestone() {
  local title="$1" description="$2" due_date="${3:-}"

  existing=$(curl -s -H "$AUTH" "${API}/milestones" | jq -r --arg t "$title" '.[] | select(.title == $t) | .title')
  if [ -n "$existing" ]; then
    echo "  ✓ Milestone already exists: $title"
    return
  fi

  local body="{\"title\":\"${title}\",\"description\":\"${description}\"}"
  if [ -n "$due_date" ]; then
    body="{\"title\":\"${title}\",\"description\":\"${description}\",\"due_on\":\"${due_date}T23:59:59Z\"}"
  fi

  curl -s -X POST -H "$AUTH" -H "$CT" "${API}/milestones" \
    -d "$body" \
    | jq -r '"  + Created milestone: \(.title) (\(.id))"'
}

# --- Labels ---
echo ""
echo "=== Creating Labels ==="
echo ""

echo "--- Type ---"
create_label "bug"        "#d73a4a" "Something isn't working"
create_label "feature"    "#0075ca" "New functionality"
create_label "ux"         "#a2eeef" "User experience issue"
create_label "chore"      "#bfd4f2" "Maintenance, refactor, tooling"
create_label "security"   "#b60205" "Security-related issue"
create_label "data"       "#f9d0c4" "Seed data, ETL, ingest pipeline"
create_label "docs"       "#0e8a16" "Documentation only"

echo ""
echo "--- Priority ---"
create_label "P0-critical" "#b60205" "Blocks sprint — fix immediately"
create_label "P1-high"     "#d93f0b" "Must fix this sprint"
create_label "P2-medium"   "#fbca04" "Should fix this sprint"
create_label "P3-low"      "#0e8a16" "Nice to have — can defer"

echo ""
echo "--- Area ---"
create_label "area/auth"     "#c5def5" "Auth, onboarding, age gate"
create_label "area/scan"     "#c5def5" "Camera, ML Kit, barcode"
create_label "area/humidor"  "#c5def5" "Humidor / collection management"
create_label "area/review"   "#c5def5" "Log session, ratings, flavour wheel"
create_label "area/discover" "#c5def5" "Browse, search, recommendations"
create_label "area/social"   "#c5def5" "Profiles, follows, feed"
create_label "area/cigar-db" "#c5def5" "Cigar/brand data, knowledge pages"
create_label "area/admin"    "#c5def5" "Moderation, ingest review"
create_label "area/api"      "#c5def5" "API routes, data layer"
create_label "area/mobile"   "#c5def5" "Mobile-specific (Expo/RN)"
create_label "area/web"      "#c5def5" "Web-specific (Next.js)"
create_label "area/infra"    "#c5def5" "CI/CD, deploy, Supabase config"

echo ""
echo "--- Workflow ---"
create_label "sit/found"     "#e4e669" "Found during system integration test"
create_label "sit/retest"    "#fef2c0" "Fix applied — needs retest"
create_label "needs-design"  "#d4c5f9" "Requires design decision before dev"
create_label "blocked"       "#000000" "Blocked by external dependency"
create_label "wont-fix"      "#ffffff" "Acknowledged but will not address"

echo ""
echo "--- Source ---"
create_label "source/claude" "#1d76db" "Found by Claude Code during dev or SIT"
create_label "source/dev"    "#5319e7" "Found by developer during validation"
create_label "source/uat"    "#f9826c" "Found by UAT tester during acceptance testing"

echo ""
echo "--- Triage ---"
create_label "triage/new"        "#ff7619" "Newly logged — not yet reviewed by Claude Code"
create_label "triage/confirmed"  "#0e8a16" "Claude Code has validated the issue"
create_label "triage/duplicate"  "#cfd3d7" "Duplicate of an existing issue"
create_label "triage/needs-info" "#fbca04" "Insufficient detail — clarification requested"

# --- Milestones (seed data — future milestones created by Claude Code) ---
echo ""
echo "=== Creating Seed Milestones ==="
echo "(Future sprint milestones will be created by Claude Code during sprint planning)"
echo ""

create_milestone \
  "Sprint 001 — Initial Setup" \
  "v0.2.0 · Foundation sprint. Replace this description after running project initialisation."

create_milestone \
  "Backlog" \
  "Unprioritised work not assigned to a sprint. Review during sprint planning."

# --- Summary ---
echo ""
echo "=== Done ==="
echo ""
echo "Next steps:"
echo "  1. Run: curl -s -H \"$AUTH\" ${API}/labels | jq '.[] | {id, name}'"
echo "     to get label IDs for reference"
echo "  2. Open Claude Code — it will read PROJECT.md and propose your sprint plan"
echo ""
