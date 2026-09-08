#!/usr/bin/env bash
# Pre-commit / CI guard: refuse to commit secret-shaped content.
#
# This repo is PUBLIC (mirrored to GitHub). A secret committed here is a secret
# published. History already contains an old hard-coded server password from
# before .env existed — see SECURITY.md. This guard stops the next one.
set -euo pipefail

FAIL=0
say(){ echo "[secret-check] $*" >&2; }

# Files that must never be tracked, regardless of .gitignore drift.
NEVER_TRACK='^\.env$|^\.env\..*|(^|/)secrets?\.(ya?ml|json|conf)$|\.pem$|(^|/)id_(rsa|ed25519)$|(^|/)\.api\.pid$'
if staged=$(git diff --cached --name-only 2>/dev/null) && [[ -n "${staged}" ]]; then
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if grep -qE "${NEVER_TRACK}" <<< "$f"; then
      say "REFUSING: $f must never be committed."
      FAIL=1
    fi
  done <<< "${staged}"
fi

# Assignments that look like a real credential rather than a placeholder.
# Deliberately narrow: long, high-entropy-ish values only, and placeholders are
# allowed so the docs and env.example keep working.
PATTERN='(PASSWORD|API_KEYS?|SECRET|TOKEN|PRIVATE_KEY)[[:space:]]*=[[:space:]]*"?[A-Za-z0-9/+_.-]{8,}"?'
ALLOW='example|placeholder|your-|changeme|CHANGE_ME|xxx|\$\{|<|serverpassword123|Password12|test-api-key|demo-key'

diffout="$(git diff --cached -U0 2>/dev/null || true)"
if [[ -n "${diffout}" ]]; then
  hits="$(grep -E '^\+' <<< "${diffout}" | grep -EI "${PATTERN}" | grep -vEi "${ALLOW}" || true)"
  if [[ -n "${hits}" ]]; then
    say "REFUSING: a staged line looks like a real credential."
    say "If it is a placeholder, add it to the ALLOW list in this script."
    # Print the KEY only, never the value.
    sed -E 's/=.*/=<redacted>/' <<< "${hits}" >&2
    FAIL=1
  fi
fi

if [[ "${FAIL}" -ne 0 ]]; then
  say "Commit blocked. Secrets belong in .env (gitignored) or Infisical."
  exit 1
fi
say "OK — no secret-shaped content staged."
