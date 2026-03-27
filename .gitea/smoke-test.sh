#!/usr/bin/env bash
# .gitea/smoke-test.sh
#
# Validates that Claude Code can perform all required Gitea API operations.
# Run this BEFORE starting sprint work or onboarding UAT testers.
#
# Tests: auth, list labels, list milestones, create issue, update labels,
#        add comment, search issues, move milestone, and clean up.
#
# Prerequisites:
#   - GITEA_URL, GITEA_REPO, and GITEA_TOKEN set in environment (or .env.local)
#   - curl and jq installed
#   - Labels and milestones already created
#
# Usage:
#   source .env.local && bash .gitea/smoke-test.sh
#
#   Or with explicit values:
#   GITEA_URL=http://localhost:3000 GITEA_REPO=michael/galera GITEA_TOKEN=xxx bash .gitea/smoke-test.sh
#
#   Or override repo as argument:
#   bash .gitea/smoke-test.sh michael/galera

set -euo pipefail

# Allow CLI argument to override GITEA_REPO
REPO="${1:-${GITEA_REPO:?Set GITEA_REPO or pass owner/repo as argument}}"
API="${GITEA_URL:?Set GITEA_URL}/api/v1/repos/${REPO}"
AUTH="Authorization: token ${GITEA_TOKEN:?Set GITEA_TOKEN}"
CT="Content-Type: application/json"

PASS=0
FAIL=0
TEST_ISSUE_NUMBER=""

# --- Helpers ---

pass() {
  echo "  ✅ $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  ❌ $1"
  echo "     $2"
  FAIL=$((FAIL + 1))
}

# --- Tests ---

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Gitea API Smoke Test — Claude Project Scaffold ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Repo: ${REPO}"
echo "  URL:  ${GITEA_URL}"
echo ""

# -------------------------------------------------------
echo "── 1. Authentication ──"
# -------------------------------------------------------

# Use the labels endpoint to verify auth — it only needs issue:read scope
# (the /user endpoint requires read:user which we don't need for anything else)
AUTH_RESPONSE=$(curl -s -w "\n%{http_code}" -H "$AUTH" "${API}/labels")
HTTP_CODE=$(echo "$AUTH_RESPONSE" | tail -1)
AUTH_BODY=$(echo "$AUTH_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  pass "Authenticated and connected to ${REPO}"
else
  fail "Authentication failed (HTTP ${HTTP_CODE})" "Check GITEA_TOKEN, GITEA_URL, and GITEA_REPO are correct"
  echo ""
  echo "Cannot continue without authentication. Exiting."
  exit 1
fi

# -------------------------------------------------------
echo ""
echo "── 2. List Labels ──"
# -------------------------------------------------------

LABELS=$(curl -s -H "$AUTH" "${API}/labels")
LABEL_COUNT=$(echo "$LABELS" | jq 'length')

if [ "$LABEL_COUNT" -gt 0 ]; then
  pass "Found ${LABEL_COUNT} labels"
else
  fail "No labels found" "Run the bootstrap script or create labels manually"
fi

# Check for required label groups
for LABEL_NAME in "bug" "P1-high" "triage/new" "source/claude" "sit/found" "area/api"; do
  EXISTS=$(echo "$LABELS" | jq -r --arg n "$LABEL_NAME" '.[] | select(.name == $n) | .name')
  if [ -n "$EXISTS" ]; then
    pass "Label exists: ${LABEL_NAME}"
  else
    fail "Missing label: ${LABEL_NAME}" "Create it in Repository → Labels"
  fi
done

# Grab IDs we need for the test issue
BUG_ID=$(echo "$LABELS" | jq -r '.[] | select(.name == "bug") | .id')
TRIAGE_NEW_ID=$(echo "$LABELS" | jq -r '.[] | select(.name == "triage/new") | .id')
TRIAGE_CONFIRMED_ID=$(echo "$LABELS" | jq -r '.[] | select(.name == "triage/confirmed") | .id')
SOURCE_CLAUDE_ID=$(echo "$LABELS" | jq -r '.[] | select(.name == "source/claude") | .id')
P1_ID=$(echo "$LABELS" | jq -r '.[] | select(.name == "P1-high") | .id')

# -------------------------------------------------------
echo ""
echo "── 3. List Milestones ──"
# -------------------------------------------------------

MILESTONES=$(curl -s -H "$AUTH" "${API}/milestones?state=all")
MS_COUNT=$(echo "$MILESTONES" | jq 'length')

if [ "$MS_COUNT" -gt 0 ]; then
  pass "Found ${MS_COUNT} milestones"
  echo "$MILESTONES" | jq -r '.[] | "     → \(.title) [\(.state)] (id: \(.id))"'
else
  fail "No milestones found" "Create milestones for your sprints"
fi

# Find Backlog milestone for the test
BACKLOG_ID=$(echo "$MILESTONES" | jq -r '.[] | select(.title == "Backlog") | .id')
if [ -n "$BACKLOG_ID" ] && [ "$BACKLOG_ID" != "null" ]; then
  pass "Backlog milestone found (id: ${BACKLOG_ID})"
else
  fail "Backlog milestone not found" "Create a milestone titled exactly 'Backlog'"
  BACKLOG_ID=""
fi

# Find any open sprint milestone for the move test
SPRINT_MS_ID=$(echo "$MILESTONES" | jq -r '[.[] | select(.state == "open" and (.title | test("Sprint"))) ] | first | .id // empty')

# -------------------------------------------------------
echo ""
echo "── 4. Create Test Issue ──"
# -------------------------------------------------------

CREATE_BODY=$(cat <<EOF
{
  "title": "[SMOKE TEST] Delete me — API validation",
  "body": "## Description\nAutomated smoke test to validate Gitea API access.\nThis issue should be deleted after the test completes.\n\n## Context\n- **Branch:** n/a (smoke test)\n- **Sprint:** n/a\n- **Platform:** API",
  "labels": [${BUG_ID}, ${TRIAGE_NEW_ID}, ${SOURCE_CLAUDE_ID}]
}
EOF
)

# Add milestone if Backlog exists
if [ -n "$BACKLOG_ID" ] && [ "$BACKLOG_ID" != "null" ]; then
  CREATE_BODY=$(echo "$CREATE_BODY" | jq --argjson ms "$BACKLOG_ID" '. + {milestone: $ms}')
fi

CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST -H "$AUTH" -H "$CT" "${API}/issues" -d "$CREATE_BODY")
CREATE_CODE=$(echo "$CREATE_RESPONSE" | tail -1)
CREATE_RESULT=$(echo "$CREATE_RESPONSE" | sed '$d')

if [ "$CREATE_CODE" = "201" ]; then
  TEST_ISSUE_NUMBER=$(echo "$CREATE_RESULT" | jq -r '.number')
  pass "Created issue #${TEST_ISSUE_NUMBER}"
else
  fail "Failed to create issue (HTTP ${CREATE_CODE})" "$(echo "$CREATE_RESULT" | jq -r '.message // "Unknown error"')"
fi

# Only continue with issue-dependent tests if creation succeeded
if [ -n "$TEST_ISSUE_NUMBER" ]; then

  # -------------------------------------------------------
  echo ""
  echo "── 5. Read Issue Back ──"
  # -------------------------------------------------------

  READ_RESPONSE=$(curl -s -H "$AUTH" "${API}/issues/${TEST_ISSUE_NUMBER}")
  READ_TITLE=$(echo "$READ_RESPONSE" | jq -r '.title')
  READ_LABELS=$(echo "$READ_RESPONSE" | jq -r '[.labels[].name] | join(", ")')

  if echo "$READ_TITLE" | grep -q "SMOKE TEST"; then
    pass "Read issue back: #${TEST_ISSUE_NUMBER}"
    pass "Labels applied: ${READ_LABELS}"
  else
    fail "Could not read issue back" "Unexpected title: ${READ_TITLE}"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 6. Update Labels (triage/new → triage/confirmed) ──"
  # -------------------------------------------------------

  # This tests the REPLACE behaviour — must send full label array
  UPDATE_BODY=$(cat <<EOF
{
  "labels": [${BUG_ID}, ${TRIAGE_CONFIRMED_ID}, ${SOURCE_CLAUDE_ID}, ${P1_ID}]
}
EOF
)

  UPDATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH -H "$AUTH" -H "$CT" "${API}/issues/${TEST_ISSUE_NUMBER}" -d "$UPDATE_BODY")
  UPDATE_CODE=$(echo "$UPDATE_RESPONSE" | tail -1)

  if [ "$UPDATE_CODE" = "201" ]; then
    UPDATED_LABELS=$(echo "$UPDATE_RESPONSE" | sed '$d' | jq -r '[.labels[].name] | join(", ")')
    pass "Labels updated: ${UPDATED_LABELS}"
  else
    fail "Failed to update labels (HTTP ${UPDATE_CODE})" "Check issue:write scope"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 7. Add Comment ──"
  # -------------------------------------------------------

  COMMENT_BODY='{"body": "Smoke test comment — validating Claude Code can add comments to issues."}'

  COMMENT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST -H "$AUTH" -H "$CT" "${API}/issues/${TEST_ISSUE_NUMBER}/comments" -d "$COMMENT_BODY")
  COMMENT_CODE=$(echo "$COMMENT_RESPONSE" | tail -1)

  if [ "$COMMENT_CODE" = "201" ]; then
    COMMENT_ID=$(echo "$COMMENT_RESPONSE" | sed '$d' | jq -r '.id')
    pass "Comment added (id: ${COMMENT_ID})"
  else
    fail "Failed to add comment (HTTP ${COMMENT_CODE})" "Check issue:write scope"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 8. Search Issues ──"
  # -------------------------------------------------------

  SEARCH_RESPONSE=$(curl -s -H "$AUTH" "${API}/issues?q=SMOKE+TEST&type=issues")
  SEARCH_COUNT=$(echo "$SEARCH_RESPONSE" | jq 'length')

  if [ "$SEARCH_COUNT" -gt 0 ]; then
    pass "Search found ${SEARCH_COUNT} result(s) for 'SMOKE TEST'"
  else
    fail "Search returned no results" "Issue was created but search didn't find it"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 9. List Issue Attachments ──"
  # -------------------------------------------------------

  ASSETS_RESPONSE=$(curl -s -w "\n%{http_code}" -H "$AUTH" "${API}/issues/${TEST_ISSUE_NUMBER}/assets")
  ASSETS_CODE=$(echo "$ASSETS_RESPONSE" | tail -1)

  if [ "$ASSETS_CODE" = "200" ]; then
    ASSET_COUNT=$(echo "$ASSETS_RESPONSE" | sed '$d' | jq 'length')
    pass "Attachment endpoint accessible (${ASSET_COUNT} attachments on test issue)"
    echo "     Claude Code can view screenshots uploaded by testers"
  else
    fail "Failed to list attachments (HTTP ${ASSETS_CODE})" "Check write:issue scope covers asset access"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 10. Move Issue Between Milestones ──"
  # -------------------------------------------------------

  if [ -n "$SPRINT_MS_ID" ] && [ "$SPRINT_MS_ID" != "null" ]; then
    MOVE_BODY="{\"milestone\": ${SPRINT_MS_ID}}"
    MOVE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH -H "$AUTH" -H "$CT" "${API}/issues/${TEST_ISSUE_NUMBER}" -d "$MOVE_BODY")
    MOVE_CODE=$(echo "$MOVE_RESPONSE" | tail -1)

    if [ "$MOVE_CODE" = "201" ]; then
      NEW_MS=$(echo "$MOVE_RESPONSE" | sed '$d' | jq -r '.milestone.title')
      pass "Moved issue to milestone: ${NEW_MS}"

      # Move it back to Backlog
      if [ -n "$BACKLOG_ID" ] && [ "$BACKLOG_ID" != "null" ]; then
        curl -s -X PATCH -H "$AUTH" -H "$CT" "${API}/issues/${TEST_ISSUE_NUMBER}" \
          -d "{\"milestone\": ${BACKLOG_ID}}" > /dev/null
        pass "Moved issue back to Backlog"
      fi
    else
      fail "Failed to move issue (HTTP ${MOVE_CODE})" "Check issue:write scope covers milestone changes"
    fi
  else
    echo "  ⏭️  Skipped (no open sprint milestone to test with)"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 11. Create Milestone (dry run) ──"
  # -------------------------------------------------------

  # Create a test milestone and immediately delete it
  TEST_MS_BODY='{"title": "[SMOKE TEST] Delete me", "description": "Automated test — safe to delete."}'
  TEST_MS_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST -H "$AUTH" -H "$CT" "${API}/milestones" -d "$TEST_MS_BODY")
  TEST_MS_CODE=$(echo "$TEST_MS_RESPONSE" | tail -1)

  if [ "$TEST_MS_CODE" = "201" ]; then
    TEST_MS_ID=$(echo "$TEST_MS_RESPONSE" | sed '$d' | jq -r '.id')
    pass "Created test milestone (id: ${TEST_MS_ID})"

    # Clean up — delete the test milestone
    DEL_MS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "$AUTH" "${API}/milestones/${TEST_MS_ID}")
    if [ "$DEL_MS_CODE" = "204" ]; then
      pass "Deleted test milestone"
    else
      echo "  ⚠️  Could not delete test milestone (HTTP ${DEL_MS_CODE}) — delete manually"
    fi
  else
    fail "Failed to create milestone (HTTP ${TEST_MS_CODE})" "Check issue:write scope covers milestone creation"
  fi

  # -------------------------------------------------------
  echo ""
  echo "── 12. Clean Up Test Issue ──"
  # -------------------------------------------------------

  # Close the test issue (normally only humans do this, but we're cleaning up)
  CLOSE_BODY='{"state": "closed"}'
  CLOSE_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH -H "$AUTH" -H "$CT" "${API}/issues/${TEST_ISSUE_NUMBER}" -d "$CLOSE_BODY")

  if [ "$CLOSE_CODE" = "201" ]; then
    pass "Closed test issue #${TEST_ISSUE_NUMBER}"
  else
    echo "  ⚠️  Could not close test issue (HTTP ${CLOSE_CODE}) — close it manually in Gitea"
  fi

  echo ""
  echo "  Note: Test issue #${TEST_ISSUE_NUMBER} has been closed but not deleted"
  echo "  (Gitea doesn't support issue deletion via API)."
  echo "  You can delete it from the Gitea UI if you want a clean issue list,"
  echo "  or leave it — it's closed and won't affect anything."

fi

# -------------------------------------------------------
echo ""
echo "══════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "  🎉 All ${PASS} tests passed — Claude Code is ready to go."
else
  echo "  ⚠️  ${PASS} passed, ${FAIL} failed — fix the issues above before starting."
fi

echo ""
