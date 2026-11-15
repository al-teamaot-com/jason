#!/usr/bin/env bash
# EXACT first root-only bootstrap transition. ONE authenticated Owner approval.
# Do not invoke the second root source repair or Stage A0 native installation.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" -eq 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] ||
    { echo "DENIED: only --check-only or --execute" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
    { echo "DENIED: existing al UID1000 required" >&2; exit 2; }

BASE="/srv/jason/archive"
WORKTREE="$BASE/engineering-worktrees/pmv4-a0-one-file-root-closure-20261115"
ROOT_SOURCE="$WORKTREE/tools/pmv4_a0_closure_bootstrap_root.py"
OWNER_SOURCE="$WORKTREE/tools/pmv4_a0_closure_bootstrap_owner.py"
PLAN="$BASE/pmv4-a0-closure-bootstrap-plan-7b42.json"
ROOT_SHA="3790bf79d4a302fe572055c3936ba28b8935ea9e1dc1a833b6b8acc9ed62878b"
OWNER_SHA="b35f34d110d8f6ddc7ec664f670958a435069e47c66fcb9a11afbaf4a7e2f5ad"
PLAN_SHA="25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564"
SOURCE_SHA="7b42ce983896711525de4c7955bf9fc43ac003d0"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
STAGE="/run/jason-pmv4-a0-closure-bootstrap-7b42"
STAGED="$STAGE/installer.py"
HELPER="/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py"
HELPER_SHA="1006edb6613f3ff976fadf64c25d8e6096dfef6b2296e4583ba51ee81ee4c4f6"
POLICY="/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json"
POLICY_SHA="7cd1ef65c9bcf8c6442a191348ac187c05c421ed8576998b61b7427d08a5da32"
FREEZE="/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
HOLD="/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"

printf '%s  %s\n' "$ROOT_SHA" "$ROOT_SOURCE" |
    /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$OWNER_SHA" "$OWNER_SOURCE" |
    /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$PLAN_SHA" "$PLAN" |
    /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$FREEZE_SHA" "$FREEZE" |
    /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$HOLD_SHA" "$HOLD" |
    /usr/bin/sha256sum --check --status
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
    { echo "DENIED: production LKG changed" >&2; exit 2; }

# The pinned Owner preflight checks the source metadata, existing root
# policy/ledger absence, production identity and exact immutable review.
python3 -B "$OWNER_SOURCE" --check-only
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] ||
    { echo "DENIED: private root stage already exists" >&2; exit 2; }
echo "ONE_EXACT_ROOT_BOOTSTRAP_TRANSITION_PREFLIGHT=VERIFIED"
echo "PRODUCTION_ROOT_WRITES=false; OWNER_APPROVAL_ISSUED=false"
if [[ "$MODE" == "--check-only" ]]; then
    exit 0
fi
[[ -t 0 && -t 1 ]] ||
    { echo "DENIED: real interactive local Owner terminal required" >&2; exit 2; }

echo "EXACT_ACTION=pmv4-stage-a0-root-source-closure-bootstrap-v1"
echo "ONE_HELPER_ONE_POLICY_ONE_EMPTY_AUDIT_DIRECTORY_ONLY=true"
echo "SOURCE_SHA=$SOURCE_SHA; PRODUCTION_LKG=$LKG"
echo "NEXT_STAGE_APPROVAL_INCLUDED=false"
python3 -B "$OWNER_SOURCE" --authorize
python3 -B "$OWNER_SOURCE" --verify-proof

CREATED=0
cleanup() {
    if [[ "$CREATED" == 1 ]]; then
        sudo /usr/bin/rm -f -- "$STAGED"
        sudo /usr/bin/rmdir -- "$STAGE"
    fi
}
trap cleanup EXIT
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
CREATED=1
sudo /usr/bin/install -o root -g root -m 0400 "$ROOT_SOURCE" "$STAGED"
printf '%s  %s\n' "$ROOT_SHA" "$STAGED" | sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I "$STAGED" --execute
printf '%s  %s\n' "$HELPER_SHA" "$HELPER" |
    sudo /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$POLICY_SHA" "$POLICY" |
    sudo /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$FREEZE_SHA" "$FREEZE" |
    /usr/bin/sha256sum --check --status
printf '%s  %s\n' "$HOLD_SHA" "$HOLD" |
    /usr/bin/sha256sum --check --status
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
    { echo "DENIED: production LKG changed after exact bootstrap" >&2; exit 2; }
echo "EXACT_BOOTSTRAP_ONE_OWNER_APPROVAL=VERIFIED_INSTALLED"
echo "STAGE_A0_SOURCE_REPAIR_AND_NATIVE_INSTALL=NOT_AUTHORIZED_NOT_EXECUTED"
