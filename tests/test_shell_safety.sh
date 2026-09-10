#!/usr/bin/env bash
# Functional safety tests for the shell layer.
#
# Covers the failure modes that a Valheim major-version update can trigger:
#   guard_world()  #70 — must never overwrite a migrated world
#   backup()       #73 — must never silently archive nothing
#
# Run: bash tests/test_shell_safety.sh
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

setup(){
  T="$(mktemp -d)"; export SAVEDIR="$T/worlds"; export BACKUP_DIR="$T/backups"
  export WORLD_NAME="CrowsNest"; export LOG_DIR="$T/logs"; export LOGFILE="$T/logs/v.log"
  export PIDFILE="$T/v.pid"; export GUARD_WORLD="${GUARD_WORLD:-true}"; export PORT=2456
  mkdir -p "$SAVEDIR/worlds_local" "$BACKUP_DIR" "$LOG_DIR"
}
mkbackup(){ # a pre-1.0 flat backup containing OLD content
  mkdir -p "$T/stage/worlds_local"
  echo "OLD-WORLD-FROM-BACKUP" > "$T/stage/worlds_local/CrowsNest.db"
  echo "OLD-FWL"               > "$T/stage/worlds_local/CrowsNest.fwl"
  tar -czf "$BACKUP_DIR/world-CrowsNest-2026-06-13_00-00-00.tar.gz" -C "$T/stage" worlds_local
}
# CRITICAL: the manager runs with `set -eo pipefail`. The tests must too, or
# they miss the entire class of "pipeline fails under pipefail" bugs — which
# is exactly what happened: backup() verification passed here and failed on
# the real host.
run_guard(){ ( set -eo pipefail; set +e; source "$REPO/helpers.sh"; guard_world ) 2>&1; }

echo "TEST 1: chunked (1.0) world must NOT be touched"
setup; mkbackup
mkdir -p "$SAVEDIR/worlds_local/CrowsNest"
echo "NEW-1.0-CHUNK" > "$SAVEDIR/worlds_local/CrowsNest/chunk_0_0.dat"
OUT="$(run_guard)"
if grep -q "NEW-1.0-CHUNK" "$SAVEDIR/worlds_local/CrowsNest/chunk_0_0.dat" \
   && [[ ! -f "$SAVEDIR/worlds_local/CrowsNest.db" ]]; then
  ok "chunked world preserved, no stale restore"
else
  no "chunked world was clobbered!"; echo "$OUT"
fi
echo "$OUT" | grep -qi "chunked" && ok "detected chunked layout" || no "did not report chunked"
rm -rf "$T"

echo "TEST 2: healthy flat world must NOT be touched"
setup; mkbackup
echo "LIVE-WORLD" > "$SAVEDIR/worlds_local/CrowsNest.db"
echo "LIVE-FWL"   > "$SAVEDIR/worlds_local/CrowsNest.fwl"
run_guard >/dev/null
grep -q "LIVE-WORLD" "$SAVEDIR/worlds_local/CrowsNest.db" && ok "healthy flat world untouched" || no "healthy world overwritten!"
rm -rf "$T"

echo "TEST 3: damaged flat world SHOULD restore (regression guard)"
setup; mkbackup
: > "$SAVEDIR/worlds_local/CrowsNest.db"        # zero-byte = damaged
echo "LIVE-FWL" > "$SAVEDIR/worlds_local/CrowsNest.fwl"
run_guard >/dev/null
grep -q "OLD-WORLD-FROM-BACKUP" "$SAVEDIR/worlds_local/CrowsNest.db" 2>/dev/null \
  && ok "damaged world restored from backup" || no "damaged world NOT restored"
rm -rf "$T"

echo "TEST 4: unrecognised layout WITH data must refuse to restore"
setup; mkbackup
echo "MYSTERY-FORMAT" > "$SAVEDIR/worlds_local/CrowsNest.newfmt"
OUT="$(run_guard)"
grep -q "MYSTERY-FORMAT" "$SAVEDIR/worlds_local/CrowsNest.newfmt" \
  && [[ ! -f "$SAVEDIR/worlds_local/CrowsNest.db" ]] \
  && ok "refused to restore over unknown-but-present data" || { no "clobbered unknown layout!"; echo "$OUT"; }
rm -rf "$T"

echo "TEST 5: GUARD_WORLD=false disables it entirely"
setup; mkbackup
GUARD_WORLD=false
OUT="$(GUARD_WORLD=false run_guard)"
echo "$OUT" | grep -qi "disabled" && ok "GUARD_WORLD=false honoured" || no "flag ignored"
rm -rf "$T"

run_backup(){ ( set -eo pipefail; set +e; source "$REPO/config.conf" >/dev/null 2>&1; source "$REPO/helpers.sh"; \
                BACKUPS_KEEP=5; source /dev/stdin <<< "$(sed -n "/^backup() {/,/^}/p" "$REPO/valheim-server-manager.sh")"; \
                backup ) 2>&1; }

echo "TEST 6: backup() must FAIL loudly when there is no world"
setup
OUT="$(run_backup)"; RC=$?
if [[ $RC -ne 0 ]] && echo "$OUT" | grep -qi "error"; then
  ok "empty world -> hard error (not a silent warning)"
else
  no "empty world did not produce an error (rc=$RC)"; echo "$OUT"
fi
[[ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]] && ok "no empty archive left behind" || no "wrote an archive with no world"
rm -rf "$T"

echo "TEST 7: backup() archives a CHUNKED world (1.0 layout)"
setup
mkdir -p "$SAVEDIR/worlds_local/CrowsNest"
echo "CHUNKDATA" > "$SAVEDIR/worlds_local/CrowsNest/chunk_0_0.dat"
echo "admin1" > "$SAVEDIR/adminlist.txt"
OUT="$(run_backup)"
ARC="$(ls "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -1)"
if [[ -n "$ARC" ]] && tar -tzf "$ARC" | grep -q "CrowsNest/chunk_0_0.dat"; then
  ok "chunked world archived"
else
  no "chunked world NOT archived"; echo "$OUT"
fi
[[ -n "$ARC" ]] && tar -tzf "$ARC" | grep -q "adminlist.txt" && ok "adminlist.txt included" || no "adminlist.txt missing"
rm -rf "$T"

echo "TEST 8: backup() archives a FLAT world and verifies integrity"
setup
echo "FLATDATA" > "$SAVEDIR/worlds_local/CrowsNest.db"
echo "FLATFWL"  > "$SAVEDIR/worlds_local/CrowsNest.fwl"
OUT="$(run_backup)"
ARC="$(ls "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -1)"
if [[ -n "$ARC" ]] && gzip -t "$ARC" 2>/dev/null && tar -tzf "$ARC" | grep -q "CrowsNest.db"; then
  ok "flat world archived and integrity-verified"
else
  no "flat world backup failed"; echo "$OUT"
fi
rm -rf "$T"

# ─────────────────────────────────────────────────────────────────────────────
# config.conf must survive `set -u`
#
# Three scripts source config.conf and TWO of them run `set -euo pipefail`.
# STEAMCLIENT_SO is not in .env, so config.conf:83 aborted them at source time:
# backup-automation.sh died on every invocation and systemd restarted it 5,884
# times without one backup ever running. Nothing caught it because nothing ever
# sourced config.conf the way those scripts do.
# ─────────────────────────────────────────────────────────────────────────────
echo
echo "TEST 12: config.conf sources cleanly under set -euo pipefail"
CFG_OUT="$( env -u STEAMCLIENT_SO -u LD_LIBRARY_PATH -u STEAMCMD_BIN -u SERVER_DIR \
            bash -c 'set -euo pipefail; source "'"$REPO"'/config.conf" >/dev/null 2>&1; echo SOURCED_OK' 2>&1 )"
if [[ "$CFG_OUT" == *SOURCED_OK* ]]; then
  ok "config.conf survives set -u with every optional var unset"
else
  no "config.conf aborts under set -u — this is what killed backup-automation.sh"
  echo "      $CFG_OUT"
fi

echo
echo "TEST 13: no read-before-assign left unguarded in config.conf"
# Only two shapes actually abort under set -u, and a use AFTER assignment is
# fine — so match the shapes, not every mention:
#   1. an emptiness guard on a var that may never have been set:  [[ -z "${VAR}" ]]
#   2. a self-referencing append:                        VAR="${VAR}:more"
UNGUARDED="$(grep -nE '\[\[ +(! +)?-[znx] +"\$\{[A-Z_]+\}"' "$REPO/config.conf" | grep -v ':-' || true)"
UNGUARDED="$UNGUARDED$(grep -nE '^\s*(export +)?([A-Z_]+)=.*\$\{\2\}' "$REPO/config.conf" | grep -v ':-' || true)"
if [[ -z "$UNGUARDED" ]]; then
  ok "every optional var is :- guarded where it is tested"
else
  no "unguarded reads remain — they will abort a set -u caller"
  echo "$UNGUARDED" | sed 's/^/      /'
fi

# ─────────────────────────────────────────────────────────────────────────────
# restart on a STOPPED server must actually start it
#
# stop() used `exit 0` rather than `return 0` on the not-running path. Since
# restart() is `stop; sleep 2; start`, the exit killed the whole script and
# start() never ran — while the API happily answered 202 "Restart accepted".
# ─────────────────────────────────────────────────────────────────────────────
echo
echo "TEST 14: stop()/start() no-op paths return, they do not exit"
BAD="$(grep -nE 'echo "(Server is not running|Already running)[^"]*"[^;]*; *exit ' "$REPO/valheim-server-manager.sh" || true)"
if [[ -z "$BAD" ]]; then
  ok "no-op paths use return — restart() can reach start()"
else
  no "an exit on a no-op path will truncate any caller (restart, update)"
  echo "$BAD" | sed 's/^/      /'
fi

echo
echo "TEST 15: the REAL stop() lets restart() reach start()"
setup
# Eval the shipped function bodies — a stubbed stop() would prove nothing about
# the file we actually deploy. The manager dispatches on "$1" at the bottom, so
# it cannot simply be sourced.
STOP_BODY="$(sed -n '/^stop() {/,/^}/p' "$REPO/valheim-server-manager.sh")"
RESTART_OUT="$( ( set -eo pipefail; set +e
  SCRIPT_DIR="$REPO"
  is_running(){ return 1; }
  start(){ echo "START_WAS_REACHED"; return 0; }
  eval "$STOP_BODY"
  restart(){ stop; start; }
  restart ) 2>&1 )"
if [[ "$RESTART_OUT" == *START_WAS_REACHED* ]]; then
  ok "the shipped stop() returns, so restart reaches start"
else
  no "the shipped stop() truncated restart before start"; echo "      $RESTART_OUT"
fi

echo; echo "  ── $PASS passed, $FAIL failed ──"
[[ $FAIL -eq 0 ]]
