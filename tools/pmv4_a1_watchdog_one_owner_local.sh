#!/usr/bin/env bash
# One separate, governed Entra Owner release: exact one-container root watchdog.
# NOT the A1 gateway activation. The root policy remains protected throughout.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] ||
  { echo "A1_POLICY_LOCAL=DENIED INVALID_MODE" >&2; exit 2; }
[[ "$(id -u)" == 1000 ]] ||
  { echo "A1_POLICY_LOCAL=DENIED OWNER_LOCAL_UID_REQUIRED" >&2; exit 2; }

TREE="/srv/jason/archive/engineering-worktrees/pmv4-a1-watchdog-allowlist-20261116"
ROOT="$TREE/tools/pmv4_a1_watchdog_policy_root.py"
ISSUER="$TREE/tools/pmv4_a1_watchdog_one_owner.py"
ARTIFACT="/srv/jason/archive/engineering-artifacts/pmv4-a1-watchdog-860dc8"
PLAN="$ARTIFACT/exact-policy-plan.json"
PROOF="$ARTIFACT/exact-one-owner-proof.json"
STAGE="/run/jason-pmv4-a1-policy-860dc8"
STAGED="$STAGE/installer.py"
ROOT_SHA="b6786157e4cbd41ec1435f5022affdb1b23bcce8ac0317cb5ae97b4ce8e1503f"
ISSUER_SHA="d48bbf80393dd4958a3102bc3c7e4398a03455b444c711e15b7dc82acd4591c3"
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
hash_check "$ISSUER_SHA" "$ISSUER"
hash_check "$FREEZE_SHA" "$FREEZE"
hash_check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_POLICY_LOCAL=DENIED PROTECTED_LKG_CHANGED" >&2; exit 2; }
[[ "$(gh api repos/al-teamaot-com/jason/branches/main --jq .commit.sha)" == "$SOURCE" ]] ||
  { echo "A1_POLICY_LOCAL=DENIED PROTECTED_SOURCE_CHANGED" >&2; exit 2; }
[[ ! -e "$PROOF" && ! -L "$PROOF" ]] ||
  { echo "A1_POLICY_LOCAL=DENIED EXACT_OWNER_PROOF_ALREADY_EXISTS" >&2; exit 2; }
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] ||
  { echo "A1_POLICY_LOCAL=DENIED UNREVIEWED_ROOT_STAGE" >&2; exit 2; }

cd "$TREE"
PYTHONPATH=implementation:tools:. /usr/bin/python3 -B "$ISSUER" --check-only
echo "A1_POLICY_EXACT_ONE_OWNER_SOURCE_PREFLIGHT=PASS"
echo "OWNER_APPROVAL_USED=false; ROOT_POLICY_CHANGES=false"
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi

[[ -t 0 && -t 1 ]] ||
  { echo "A1_POLICY_LOCAL=DENIED INTERACTIVE_OWNER_TTY_REQUIRED" >&2; exit 2; }

STAGED_TEMP=0
OWNER_PROOF_CREATED=0
cleanup() {
  if [[ "$STAGED_TEMP" == 1 && "$OWNER_PROOF_CREATED" == 0 ]]; then
    sudo /usr/bin/rm -f -- "$STAGED"
    sudo /usr/bin/rmdir -- "$STAGE"
  fi
}
trap cleanup EXIT

# No root policy mutation or release entitlement is created in preflight.
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
STAGED_TEMP=1
sudo /usr/bin/install -o root -g root -m 0400 "$ROOT" "$STAGED"
printf '%s  %s\n' "$ROOT_SHA" "$STAGED" |
  sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$STAGED" --preflight
echo "A1_POLICY_INDEPENDENT_ROOT_PREFLIGHT=PASS"
echo "OWNER_APPROVAL_NOT_ISSUED=true; POLICY_UNMODIFIED=true"

PYTHONPATH=implementation:tools:. /usr/bin/python3 -B "$ISSUER" --authorize
OWNER_PROOF_CREATED=1
sudo /usr/bin/python3 -I -B "$STAGED" --execute
sudo /usr/bin/python3 -I -B "$STAGED" --postflight
hash_check "$FREEZE_SHA" "$FREEZE"
hash_check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "A1_POLICY_LOCAL=DENIED CORE_LKG_CHANGED_POSTFLIGHT" >&2; exit 2; }
echo "ONE_OWNER_EXACT_A1_ROOT_WATCHDOG_POLICY=VERIFIED_POSTFLIGHT"
echo "SHADOW_GATEWAY_NOT_AUTHORIZED_BY_THIS_POLICY_RELEASE"
