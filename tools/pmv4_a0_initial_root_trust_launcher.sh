#!/usr/bin/env bash
# Exact Owner-approved PMv4 Stage A0 initial root-trust bootstrap only.
# Source-only wrapper; never runs root-owned code from the operator archive.
set -Eeuo pipefail
umask 077

ACTION="${1:-}"
SOURCE="/srv/jason/archive/pmv4-a0-root-trust-consumer-7b42ce983896711525de4c7955bf9fc43ac003d0.py"
OWNER="/srv/jason/archive/pmv4-stage-a0-initial-root-trust-owner-consent-7b42ce983896711525de4c7955bf9fc43ac003d0.py"
STAGE="/run/jason-pmv4-a0-root-trust-7b42ce983896"
STAGED="$STAGE/installer.py"
SOURCE_HASH="85551e2b08ae005a6a6ffb5609eab2943f1cd2bf828bdd56709eaa7ad98a4b59"
OWNER_HASH="d4e74c0c1c591bb146481eeea1735a0397993d7ddebb96e0888f4886d036ae78"
STAGE_CREATED=0

if [[ "$ACTION" != "--check-only" && "$ACTION" != "--execute" ]]; then
  echo "DENIED: use --check-only or --execute" >&2
  exit 2
fi
if [[ "$(id -u)" != 1000 ]]; then
  echo "DENIED: unprivileged al Owner shell required" >&2
  exit 2
fi
printf '%s  %s\n' "$SOURCE_HASH" "$SOURCE" | sha256sum -c - >/dev/null
printf '%s  %s\n' "$OWNER_HASH" "$OWNER" | sha256sum -c - >/dev/null

python3 -B "$OWNER" --check-only
python3 -B - "$SOURCE" <<'PY'
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec=spec_from_file_location("exact_root_consumer",sys.argv[1])
module=module_from_spec(spec)
spec.loader.exec_module(module)
plan,files=module.parse_exact_package()
module.preflight_production()
module.check_absent()
assert len(files)==6 and len(plan["new_root_directories"])==2
print("SIX_FILE_ROOT_PACKAGE_AND_LIVE_SAFE_GATES=PASS",flush=True)
PY

if [[ "$ACTION" == "--check-only" ]]; then
  echo "PREFLIGHT_PASS=TRUE; AUTHENTICATED_PROOF_NOT_YET_ISSUED; ROOT_INSTALL_NOT_RUN"
  exit 0
fi
if [[ ! -t 0 ]]; then
  echo "DENIED: interactive local Owner console required" >&2
  exit 2
fi
if [[ -e "$STAGE" || -L "$STAGE" ]]; then
  echo "DENIED: root-private staging namespace already exists" >&2
  exit 2
fi

# Owner executes the Entra device-code flow and types the exact-action phrase.
python3 -B "$OWNER" --authorize
python3 -B "$OWNER" --verify-proof

cleanup() {
  if [[ "$STAGE_CREATED" == 1 ]]; then
    sudo /usr/bin/rm -f -- "$STAGED"
    sudo /usr/bin/rmdir -- "$STAGE"
  fi
}
trap cleanup EXIT
sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
STAGE_CREATED=1
sudo /usr/bin/install -o root -g root -m 0400 "$SOURCE" "$STAGED"
printf '%s  %s\n' "$SOURCE_HASH" "$STAGED" | sudo /usr/bin/sha256sum -c -
sudo /usr/bin/python3 -I "$STAGED" --execute

echo "ROOT_TRUST_INITIAL_INSTALL_TRANSACTION=FINISHED; independent readback still required"
