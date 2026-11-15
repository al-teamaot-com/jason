#!/usr/bin/env bash
# One local, interactive Owner workflow for EXACT PMv4 A0 closure bootstrap,
# then distinct one-file native repair authorization. No standing root access.
set -Eeuo pipefail
umask 077

MODE="${1:-}"
WORKTREE="/srv/jason/archive/engineering-worktrees/pmv4-a0-one-file-root-closure-20261115"
ROOT_SOURCE="$WORKTREE/tools/pmv4_a0_closure_bootstrap_root.py"
OWNER_SOURCE="$WORKTREE/tools/pmv4_a0_closure_bootstrap_owner.py"
PLAN="/srv/jason/archive/pmv4-a0-closure-bootstrap-plan-7b42.json"
ROOT_SHA256="3790bf79d4a302fe572055c3936ba28b8935ea9e1dc1a833b6b8acc9ed62878b"
OWNER_SHA256="b35f34d110d8f6ddc7ec664f670958a435069e47c66fcb9a11afbaf4a7e2f5ad"
PLAN_SHA256="25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564"
STAGE="/run/jason-pmv4-a0-closure-bootstrap-7b42"
STAGED="$STAGE/installer.py"
TRUSTED_HELPER="/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py"
TRUSTED_POLICY="/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json"
TARGET="/opt/jason/releases/7b42ce983896711525de4c7955bf9fc43ac003d0/tools/pmv4_host_install_contract.py"
TARGET_SHA256="ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db"
HELPER_SHA256="1006edb6613f3ff976fadf64c25d8e6096dfef6b2296e4583ba51ee81ee4c4f6"
POLICY_SHA256="7cd1ef65c9bcf8c6442a191348ac187c05c421ed8576998b61b7427d08a5da32"
CREATED=0

if [[ "$MODE" != "--check-only" && "$MODE" != "--execute" ]]; then
  echo "DENIED: choose --check-only or --execute" >&2; exit 2
fi
if [[ "$(id -u)" != 1000 ]]; then
  echo "DENIED: existing local al UID1000 session required" >&2; exit 2
fi
printf '%s  %s\n' "$ROOT_SHA256" "$ROOT_SOURCE" | sha256sum -c - >/dev/null
printf '%s  %s\n' "$OWNER_SHA256" "$OWNER_SOURCE" | sha256sum -c - >/dev/null
printf '%s  %s\n' "$PLAN_SHA256" "$PLAN" | sha256sum -c - >/dev/null
python3 -B "$OWNER_SOURCE" --check-only
echo "EXACT_BOOTSTRAP_PACKAGE_AND_LIVE_OWNER_PREFLIGHT=VERIFIED"

if [[ "$MODE" == "--check-only" ]]; then
  echo "PRODUCTION_ROOT_WRITES=false; OWNER_APPROVAL_ISSUED=false"
  exit 0
fi
if [[ ! -t 0 || ! -t 1 ]]; then
  echo "DENIED: real interactive Owner-local terminal is required" >&2; exit 2
fi
if [[ -e "$STAGE" || -L "$STAGE" ]]; then
  echo "DENIED: private root bootstrap stage already exists" >&2; exit 2
fi

echo "STEP 1/2: authenticate exact Entra Owner consent for the two-file root bootstrap."
python3 -B "$OWNER_SOURCE" --authorize
python3 -B "$OWNER_SOURCE" --verify-proof

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
printf '%s  %s\n' "$ROOT_SHA256" "$STAGED" | sudo /usr/bin/sha256sum -c -
sudo /usr/bin/python3 -I "$STAGED" --execute

echo "BOOTSTRAP_ROOT_INSTALL=VERIFIED; exact installed byte readback follows."
printf '%s  %s\n' "$HELPER_SHA256" "$TRUSTED_HELPER" | sudo /usr/bin/sha256sum -c -
printf '%s  %s\n' "$POLICY_SHA256" "$TRUSTED_POLICY" | sudo /usr/bin/sha256sum -c -

echo "STEP 2/2: authenticate a NEW exact Entra Owner decision for ONLY the missing root-source file."
sudo /usr/bin/python3 -I "$TRUSTED_HELPER" --execute
printf '%s  %s\n' "$TARGET_SHA256" "$TARGET" | sudo /usr/bin/sha256sum -c -

echo "PMV4_A0_ROOT_SOURCE_REPAIRED=VERIFIED; STAGE_A0_INSTALL_REMAINS_SEPARATE"
echo "CURRENT_LKG_PRODUCTION_POINTER:"
readlink -f /opt/jason/current
echo "CURRENT_FREEZE_HOLD:"
sha256sum /var/lib/jason/openclaw/release-manager/production-deployment-freeze \
          /var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold
