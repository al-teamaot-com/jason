#!/usr/bin/env bash
# A1 v3: reconcile ONLY the existing Owner-signed failed shadow release.
set -Eeuo pipefail
umask 077
MODE="$1"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--recover" ) ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED INVALID_MODE" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED LOCAL_OWNER_UID_REQUIRED" >&2; exit 2; }

W="/srv/jason/archive/engineering-worktrees/pmv4-a1-v3-recovery-20261117"
S="$W/tools/pmv4_a1_v3_recover_consumed_owner.py"
ORIGINAL="/run/jason-pmv4-a1-v3-c999216a3df9/installer.py"
STAGE="/run/jason-pmv4-a1-v3-consumed-rollback-c999216a"
ROOT_SCRIPT="$STAGE/recovery.py"
SOURCE_SHA="bf4b7758e4bea6d648804c3092b1b061ff2d676c5a78928c4951e025b6316228"
REVIEWED_HEAD="$(git -C "$W" rev-parse refs/remotes/origin/fix/pmv4-a1-v3-consumed-rollback-20261117)"
ORIGINAL_SHA="bb8e88189c6a8cef3e9dec19bd4d637de2779e3c7f4c3f506c3185462dfbe83d"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE="/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
HOLD="/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold"

hash_check() {
  printf '%s  %s\n' "$1" "$2" | /usr/bin/sha256sum --check --status
}

hash_check "$SOURCE_SHA" "$S"
hash_check "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f" "$FREEZE"
hash_check "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED PRODUCTION_BASELINE_CHANGED" >&2; exit 2; }
[[ "$(git -C "$W" rev-parse HEAD)" == "$REVIEWED_HEAD" ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED REVIEWED_SOURCE_CHANGED" >&2; exit 2; }
[[ -z "$(git -C "$W" status --porcelain --untracked-files=all)" ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED REVIEWED_SOURCE_DIRTY" >&2; exit 2; }

if [[ "$MODE" == "--check-only" ]]; then
  (cd "$W" && PYTHONPATH=implementation:. /usr/bin/python3 -B -m pytest -q \
    tests/test_pmv4_a1_v3_recover_consumed_owner.py \
    tests/test_pmv4_shadow_release.py tests/test_pmv4_a1_atomic_shadow_root.py \
    tests/test_pmv4_host_release_guard.py)
  echo "A1_V3_PREVIOUS_OWNER_RECOVERY_SOURCE_PREFLIGHT=PASS"
  echo "NEW_OWNER_AUTHENTICATION=false; PRODUCTION_MUTATIONS=false"
  exit 0
fi

[[ -t 0 && -t 1 ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }

STAGED=0
RECOVERY_STARTED=0
cleanup() {
  if [[ "$STAGED" == 1 && "$RECOVERY_STARTED" == 0 ]]; then
    sudo /usr/bin/rm -f -- "$ROOT_SCRIPT" || true
    sudo /usr/bin/rmdir -- "$STAGE" || true
  fi
}
trap cleanup EXIT

sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
STAGED=1
sudo /usr/bin/install -o root -g root -m 0400 "$S" "$ROOT_SCRIPT"
printf '%s  %s\n' "$SOURCE_SHA" "$ROOT_SCRIPT" |
  sudo /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$ORIGINAL_SHA" "$ORIGINAL" |
  sudo /usr/bin/sha256sum --check --status

sudo /usr/bin/python3 -I -B "$ROOT_SCRIPT" --preflight
echo "A1_V3_HISTORICAL_OWNER_ROOT_PREFLIGHT=PASS"
echo "PRODUCTION_MUTATIONS=false; NO_NEW_OWNER_CONSENT=true"

RECOVERY_STARTED=1
sudo /usr/bin/python3 -I -B "$ROOT_SCRIPT" --recover
sudo /usr/bin/python3 -I -B "$ROOT_SCRIPT" --postflight
hash_check "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f" "$FREEZE"
hash_check "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_V3_RECOVERY_LOCAL=DENIED PRODUCTION_POINTER_CHANGED" >&2; exit 2; }
echo "A1_V3_PREVIOUS_OWNER_EXACT_ROLLBACK=VERIFIED_POSTFLIGHT"
