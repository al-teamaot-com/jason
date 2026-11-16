#!/usr/bin/env bash
# Reconcile ONLY the previously signed, already consumed A1 release rollback.
# This is not another Owner approval or a retry/promotion. Uses sudo only to
# read the original root-audit/receipt and settle the exact original rollback.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--recover" ) ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED MODE_NOT_ALLOWED" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED ORIGINAL_OWNER_UID_REQUIRED" >&2; exit 2; }

WORKTREE="/srv/jason/archive/engineering-worktrees/pmv4-a1-pending-recovery-20261116"
SOURCE="$WORKTREE/tools/pmv4_a1_pending_exact_recovery.py"
SOURCE_SHA="21419fbe7825cc38eb5faa33591b05956722f4926ef7f773544f8c5106e8e0e4"
STAGE="/run/jason-pmv4-a1-reconcile-8c20"
STAGED="$STAGE/recovery.py"
PROOF="/srv/jason/archive/engineering-artifacts/pmv4-a1-8c2064193d74cc41b52369681febbc0a74fa96f7/root-oneowner-proof.json"
OLD_EXEC="/run/jason-pmv4-a1-oneowner-8c20/installer.py"
RECEIPT="/var/lib/jason/pmv4-shadow/receipts/owner-owner-mcp-319c697027a146beac98818e5305a971.json"
ROOT_POINTER="/var/lib/jason/pmv4-shadow/current"
SHADOW="jason-pmv4-shadow-gateway"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE="/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
HOLD="/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"

hash_check() { printf '%s  %s\n' "$1" "$2" | /usr/bin/sha256sum --check --status; }
hash_check "$SOURCE_SHA" "$SOURCE"
hash_check "$FREEZE_SHA" "$FREEZE"
hash_check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED ORIGINAL_PRODUCTION_LKG_CHANGED" >&2; exit 2; }
[[ "$(readlink "$ROOT_POINTER")" == "releases/0000000000000000000000000000000000000000" ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED ORIGINAL_SHADOW_POINTER_NOT_EMPTY" >&2; exit 2; }
[[ -f "$PROOF" && -f "$RECEIPT" && ! -L "$PROOF" && ! -L "$RECEIPT" ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED ORIGINAL_SIGNED_PROOF_OR_NATIVE_RECEIPT_MISSING" >&2; exit 2; }
[[ -d "$(dirname "$OLD_EXEC")" && ! -L "$(dirname "$OLD_EXEC")" ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED ORIGINAL_ROOT_EXECUTOR_STAGE_MISSING" >&2; exit 2; }
# The original root-only stage has mode 0700. A non-root caller cannot
# stat its interior. The privileged preflight independently checks the exact
# executor file inode, root ownership and source SHA256 before any recovery.
if /usr/bin/docker ps -a --format '{{.Names}}' | grep -qx "$SHADOW"; then
  echo "A1_RECOVERY_LOCAL=DENIED SHADOW_STILL_PRESENT" >&2; exit 2
fi
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED RECOVERY_ROOT_STAGE_ALREADY_EXISTS" >&2; exit 2; }
cd "$WORKTREE"
PYTHONPATH=implementation:. /usr/bin/python3 -B -m pytest -q \
  tests/test_pmv4_a1_pending_exact_recovery.py
echo "A1_ORIGINAL_SIGNED_ROLLBACK_SOURCE_PREFLIGHT=PASS"
echo "NEW_OWNER_APPROVALS_REQUIRED=false; ROOT_MUTATIONS=false"
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi

[[ -t 0 && -t 1 ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED INTERACTIVE_SUDO_TTY_REQUIRED" >&2; exit 2; }
# A root-owned transient copy is required to access the original root-only
# journal, which remains protected. No Entra flow or new scope is introduced.
STAGED_TEMP=0
cleanup() {
  # The copy is not a standing recovery endpoint; remove on any exit.
  if [[ "$STAGED_TEMP" == 1 ]]; then
    sudo /usr/bin/rm -f -- "$STAGED"
    sudo /usr/bin/rmdir -- "$STAGE"
  fi
}
trap cleanup EXIT
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
STAGED_TEMP=1
sudo /usr/bin/install -o root -g root -m 0400 "$SOURCE" "$STAGED"
printf '%s  %s\n' "$SOURCE_SHA" "$STAGED" |
  sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$STAGED" --preflight
echo "A1_ORIGINAL_OWNER_PENDING_JOURNAL_AND_ROLLBACK_PREFLIGHT=PASS"
sudo /usr/bin/python3 -I -B "$STAGED" --recover
hash_check "$FREEZE_SHA" "$FREEZE"
hash_check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_RECOVERY_LOCAL=DENIED PRODUCTION_LKG_POSTFLIGHT_CHANGED" >&2; exit 2; }
echo "A1_SIGNED_FAILED_RELEASE_ROLLBACK=VERIFIED_POSTFLIGHT"
echo "NO_NEW_OWNER_AUTHENTICATION_WAS_REQUESTED"
