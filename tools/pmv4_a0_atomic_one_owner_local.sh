#!/usr/bin/env bash
# ONE existing Entra Owner exact-release signature for the whole 3-action A0.
# The root-owned exact stage is a narrowly scoped trusted native executor:
# source-only checkout remains NONEXECUTABLE as root.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] ||
  { echo "DENIED: --check-only or --execute required" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
  { echo "DENIED: authenticated local Jason al UID1000 required" >&2; exit 2; }

R="/srv/jason/archive/engineering-worktrees/pmv4-a0-rebind-20261115"
ROOT="$R/tools/pmv4_a0_exact_v1_root_release.py"
BOOT="$R/tools/pmv4_a0_closure_bootstrap_root.py"
OWNER="$R/tools/pmv4_a0_atomic_v1_owner_issuer.py"
POLICY="$R/config/pmv4-stage-a0/atomic-v1-root-policy-review.json"
STAGE="/run/jason-pmv4-a0-atomic-v1-8c20"
STAGED="$STAGE/installer.py"
STAGED_BOOT="$STAGE/bootstrap.py"
STAGED_POLICY="$STAGE/policy.json"
ROOT_SHA="cb24795359ec1c220a4d84cc735fe5bedeab4f93c150802c4a27ea89c79ca065"
BOOT_SHA="44cac21301f371f0f9ff16e18e57be8734aae8b5ab1e75cfee9d1bcf6c6e3474"
OWNER_SHA="5f65ed5858d5f8a18db6604dbbe23e51ffe4ee94e889752be4a889cad46277b2"
POLICY_SHA="9452b2215f4085d1b9cef1aabeb13df15e8113dda649b648b996106a164ea62a"
SOURCE="8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE="/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
HOLD="/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"

check_hash() {
  printf '%s  %s\n' "$1" "$2" | /usr/bin/sha256sum --check --status
}
check_hash "$ROOT_SHA" "$ROOT"
check_hash "$BOOT_SHA" "$BOOT"
check_hash "$OWNER_SHA" "$OWNER"
check_hash "$POLICY_SHA" "$POLICY"
check_hash "$FREEZE_SHA" "$FREEZE"
check_hash "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "DENIED: existing production LKG drift" >&2; exit 2; }
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] ||
  { echo "DENIED: preexisting private root release stage requires review" >&2; exit 2; }
[[ ! -e "/srv/jason/archive/pmv4-a0-atomic-v1-OWNER-PROOF-8c20.json" ]] ||
  { echo "DENIED: original one-use Owner grant has already been published" >&2; exit 2; }

cd "$R"
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --check-only
echo "ONE_EXACT_A0_WHOLE_RELEASE_UNPRIVILEGED_PREFLIGHT=PASS"
echo "ONE_AUTHENTICATED_OWNER_APPROVAL_TOTAL=1"
echo "OWNER_APPROVAL_CONSUMED=false; PRODUCTION_MUTATIONS=false"
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi

[[ -t 0 && -t 1 ]] ||
  { echo "DENIED: real interactive local Owner TTY and sudo required" >&2; exit 2; }

CREATED=0
APPROVAL_CREATED=0
COMPLETED=0
cleanup() {
  # Once the ONE signed whole-release Owner proof exists, retain the exact
  # root-owned 0400 /run recovery executable/policy (even after success).
  # It has no service/standing authority; one-use root journal denies replay,
  # but rollback-only and independent postflight must remain available.
  # Only pre-approval staging may be removed automatically.
  if [[ "$CREATED" == 1 && "$APPROVAL_CREATED" == 0 ]]; then
    sudo /usr/bin/rm -f -- "$STAGED" "$STAGED_BOOT" "$STAGED_POLICY"
    sudo /usr/bin/rmdir -- "$STAGE"
  fi
}
trap cleanup EXIT

# Root-only empty-baseline/readback happens BEFORE Entra login, so an
# undiscovered root-only target does NOT waste the Owner's last approval.
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
CREATED=1
sudo /usr/bin/install -o root -g root -m 0400 "$ROOT" "$STAGED"
sudo /usr/bin/install -o root -g root -m 0400 "$BOOT" "$STAGED_BOOT"
sudo /usr/bin/install -o root -g root -m 0400 "$POLICY" "$STAGED_POLICY"
printf '%s  %s\n' "$ROOT_SHA" "$STAGED" | sudo /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$BOOT_SHA" "$STAGED_BOOT" | sudo /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$POLICY_SHA" "$STAGED_POLICY" | sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$STAGED" --preflight
echo "INDEPENDENT_ROOT_ONLY_EMPTY_BASELINE=VERIFIED_NO_OWNER_APPROVAL_USED"

# Exactly one Owner credential ceremony and one signed v1 full manifest.
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --authorize
APPROVAL_CREATED=1
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --verify-proof

if ! sudo /usr/bin/python3 -I -B "$STAGED" --execute; then
  echo "A0_ATOMIC_NATIVE_EXECUTION_FAILED; attempting original-proof rollback" >&2
  sudo /usr/bin/python3 -I -B "$STAGED" --recover ||
    echo "A0_ATOMIC_RECOVERY_REQUIRES_PRIVILEGED_REVIEW; stage retained" >&2
  exit 2
fi
if ! sudo /usr/bin/python3 -I -B "$STAGED" --postflight; then
  echo "A0_POSTCOMMIT_POSTFLIGHT_FAILED; original Owner rollback only" >&2
  sudo /usr/bin/python3 -I -B "$STAGED" --recover ||
    echo "A0_ROLLBACK_REQUIRES_REVIEW; root stage retained" >&2
  exit 2
fi
check_hash "$FREEZE_SHA" "$FREEZE"
check_hash "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "DENIED: LKG changed postflight" >&2; exit 2; }
COMPLETED=1
echo "ONE_OWNER_EXACT_A0_WHOLE_RELEASE=VERIFIED_POSTFLIGHT"
echo "GLOBAL_PRODUCTION_FREEZE_AND_HOLD_UNCHANGED=true"
echo "SEPARATE_STAGE_OWNER_APPROVALS_REQUESTED=0"
