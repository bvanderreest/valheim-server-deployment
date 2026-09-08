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
run_guard(){ ( set +e; source "$REPO/helpers.sh"; guard_world ) 2>&1; }

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

run_backup(){ ( set +e; source "$REPO/config.conf" >/dev/null 2>&1; source "$REPO/helpers.sh"; \
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

echo; echo "  ── $PASS passed, $FAIL failed ──"
[[ $FAIL -eq 0 ]]
