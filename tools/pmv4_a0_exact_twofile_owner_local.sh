#!/usr/bin/env bash
# Exact one-use root-trust migration. Local authenticated Owner TTY only.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
[[ "$#" == 1 && ( "$MODE" == "--check-only" || "$MODE" == "--execute" ) ]] ||
  { echo "DENIED: exact mode required" >&2; exit 2; }
[[ "$(id -u)" == "1000" ]] || { echo "DENIED: local Owner UID1000" >&2; exit 2; }
R="/srv/jason/archive/engineering-worktrees/pmv4-a0-rebind-20261115"
CODE="$R/tools/pmv4_a0_exact_twofile_root_trust_migrator.py"
OWNER="$R/tools/pmv4_a0_exact_twofile_owner_issuer.py"
SOURCE="8c2064193d74cc41b52369681febbc0a74fa96f7"
MANIFEST="/srv/jason/archive/pmv4-a0-root-trust-twofile-migration-$SOURCE-SIGNED-REVIEW.json"
PACKAGE="/srv/jason/archive/pmv4-a0-root-trust-twofile-migration-$SOURCE.tar"
STAGE="/run/jason-pmv4-a0-trust-twofile-8c20"
ROOT="$STAGE/installer.py"
PROOF="/srv/jason/archive/pmv4-a0-root-trust-twofile-OWNER-PROOF-$SOURCE.json"
ROOT_SHA="0660aa5ab58c9b8e4ed69bb8628f031b20162862338c52c0386b5fbb9820f903"
OWNER_SHA="30c63bc2c8ae21ed2291ad25f480c399b7923b4d77b9fc0e552ec776306eae2d"
REVIEW_SHA="5c9ddd10825c7a2e13a134dd5458d16d2eadfd9bea3bd991cb6427e658071138"
PACKAGE_SHA="be49db761f381b8d570773c50d9bcdd5e3248135684094461dc2596aacdab402"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE="/var/lib/jason/openclaw/release-manager/production-deployment-freeze"
HOLD="/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
check() { printf '%s  %s\n' "$1" "$2" | /usr/bin/sha256sum --check --status; }
check "$ROOT_SHA" "$CODE"
check "$OWNER_SHA" "$OWNER"
check "$REVIEW_SHA" "$MANIFEST"
check "$PACKAGE_SHA" "$PACKAGE"
check "$FREEZE_SHA" "$FREEZE"
check "$HOLD_SHA" "$HOLD"
[[ "$(readlink -f /opt/jason/current)" == "/opt/jason/releases/$LKG" ]] ||
  { echo "DENIED: production LKG changed" >&2; exit 2; }
[[ ! -e "$STAGE" && ! -L "$STAGE" && ! -e "$PROOF" && ! -L "$PROOF" ]] ||
  { echo "DENIED: review existing stage/proof before retry" >&2; exit 2; }
cd "$R"
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --check-only
echo "A0_TWOFILE_UNPRIVILEGED_PREFLIGHT=PASS"
echo "OWNER_APPROVAL_CONSUMED=false; ROOT_WRITES=false"
[[ "$MODE" == "--check-only" ]] && exit 0
[[ -t 0 && -t 1 ]] || { echo "DENIED: real Owner local TTY required" >&2; exit 2; }
CREATED=0
SIGNED=0
cleanup() {
  if [[ "$CREATED" == 1 && "$SIGNED" == 0 ]]; then
    sudo /usr/bin/rm -f -- "$ROOT"
    sudo /usr/bin/rmdir -- "$STAGE"
  fi
}
trap cleanup EXIT
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
CREATED=1
sudo /usr/bin/install -o root -g root -m 0400 "$CODE" "$ROOT"
printf '%s  %s\n' "$ROOT_SHA" "$ROOT" | sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$ROOT" --preflight
echo "INDEPENDENT_ROOT_ONLY_PREFLIGHT=PASS; APPROVAL_UNUSED=true"
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --authorize
SIGNED=1
PYTHONPATH=implementation:. /usr/bin/python3 -B "$OWNER" --verify-proof
if ! sudo /usr/bin/python3 -I -B "$ROOT" --execute; then
  echo "EXACT TWOFILE ROOT MIGRATION FAILED; RECOVERY REQUIRED" >&2
  sudo /usr/bin/python3 -I -B "$ROOT" --recover || echo "MANUAL ROOT REVIEW REQUIRED" >&2
  exit 2
fi
if ! sudo /usr/bin/python3 -I -B "$ROOT" --postflight; then
  echo "A0_TWOFILE_POSTFLIGHT_FAILED; ORIGINAL-PROOF ROLLBACK REQUIRED" >&2
  sudo /usr/bin/python3 -I -B "$ROOT" --recover ||
    echo "A0_TWOFILE_ROLLBACK_REQUIRES_PRIVILEGED_REVIEW" >&2
  exit 2
fi
check "$FREEZE_SHA" "$FREEZE"
check "$HOLD_SHA" "$HOLD"
echo "ONE_OWNER_EXACT_TWOFILE_ROOT_TRUST=VERIFIED_POSTFLIGHT"
