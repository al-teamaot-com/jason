#!/usr/bin/env bash
# PMv4 A1 only: one Entra Owner consent for one exact isolated shadow release.
# Source-only until reviewed. No preexisting A0 approval is reused.
set -Eeuo pipefail
umask 077

MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] ||
  { echo "A1_LOCAL=DENIED INVALID_MODE" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
  { echo "A1_LOCAL=DENIED OWNER_LOCAL_UID_REQUIRED" >&2; exit 2; }

TREE="/srv/jason/archive/engineering-worktrees/pmv4-a1-shadow-package-20261116"
ROOT="$TREE/tools/pmv4_a1_atomic_shadow_root.py"
OWNER="$TREE/tools/pmv4_a1_atomic_one_owner.py"
ARTIFACT="/srv/jason/archive/engineering-artifacts/pmv4-a1-8c2064193d74cc41b52369681febbc0a74fa96f7"
PLAN="$ARTIFACT/root-release-plan.json"
PROOF="$ARTIFACT/root-oneowner-proof.json"
STAGE="/run/jason-pmv4-a1-oneowner-8c20"
STAGED="$STAGE/installer.py"
ROOT_SHA="db66f73f0d5a98329a665c33cd9bf4a7712d5e27ffeb5d4dec89f0fac933f42f"
OWNER_SHA="9eb50beaf292a8114f8f74e1ece055058d8d58bf4253a4faaa3c09ecda7239a8"
SOURCE="8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE="/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
HOLD="/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"

hash_check() {
  printf '%s  %s\n' "$1" "$2" | /usr/bin/sha256sum --check --status
}
hash_check "$ROOT_SHA" "$ROOT"
hash_check "$OWNER_SHA" "$OWNER"
hash_check "$FREEZE_SHA" "$FREEZE"
hash_check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_LOCAL=DENIED PRODUCTION_LKG_CHANGED" >&2; exit 2; }
[[ ! -e "$PROOF" && ! -L "$PROOF" ]] ||
  { echo "A1_LOCAL=DENIED A1_OWNER_PROOF_ALREADY_EXISTS" >&2; exit 2; }
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] ||
  { echo "A1_LOCAL=DENIED ROOT_STAGE_ALREADY_EXISTS" >&2; exit 2; }
[[ -f "$PLAN" && ! -L "$PLAN" ]] ||
  { echo "A1_LOCAL=DENIED PLAN_NOT_REVIEWED" >&2; exit 2; }
cd "$TREE"
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --check-only
echo "A1_ONE_OWNER_EXACT_SOURCE_PREFLIGHT=PASS"
echo "NO_PRODUCTION_OR_ROOT_CHANGES=true"
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi

# The transient /run executable is root-owned 0400 for root-only readback.
# No candidate manifest, token, or production state is staged before consent.
[[ -t 0 && -t 1 ]] ||
  { echo "A1_LOCAL=DENIED INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }
STAGED_TEMP=0
OWNER_APPROVAL_CREATED=0
cleanup() {
  # Before consent the disposable trusted /run copy may be removed.
  # After consent retain the exact privileged artifact for recovery inspection
  # even on a failed or interrupted release; never alter the A0 namespace.
  if [[ "$STAGED_TEMP" == 1 && "$OWNER_APPROVAL_CREATED" == 0 ]]; then
    sudo /usr/bin/rm -f -- "$STAGED"
    sudo /usr/bin/rmdir -- "$STAGE"
  fi
}
trap cleanup EXIT

sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
STAGED_TEMP=1
sudo /usr/bin/install -o root -g root -m 0400 "$ROOT" "$STAGED"
printf '%s  %s\n' "$ROOT_SHA" "$STAGED" |
  sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$STAGED" --preflight
echo "A1_ROOT_INDEPENDENT_PREFLIGHT=PASS"
echo "OWNER_APPROVAL_NOT_YET_USED=true; PRODUCTION_MUTATIONS=false"

# ONE verified Entra Owner and ONE exact confirmation, issuing the pair of
# independently bound root + shadow proofs under the same immutable approval.
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --authorize
OWNER_APPROVAL_CREATED=1
sudo /usr/bin/python3 -I -B "$STAGED" --execute
sudo /usr/bin/python3 -I -B "$STAGED" --postflight
hash_check "$FREEZE_SHA" "$FREEZE"
hash_check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_LOCAL=DENIED ORIGINAL_PRODUCTION_LKG_CHANGED" >&2; exit 2; }
echo "A1_ONE_OWNER_FULL_SHADOW_RELEASE=VERIFIED_POSTFLIGHT"
echo "PMV4_LATER_PHASES_ARE_NOT_AUTHORIZED"
