#!/usr/bin/env bash
# Separate one-use Owner-local release for the pre-reviewed V2 integrity
# recovery. Never alters MCP, ticket runtime, promotion hold or release freeze.
# Existing exact Stage A0 issuer ON requires a root-signed prior receipt.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
if [[ "$MODE" != "--check-only" && "$MODE" != "--execute" ]]; then
  echo "DENIED: use --check-only or --execute" >&2; exit 2
fi
if [[ "$(id -u)" != 1000 ]]; then
  echo "DENIED: exact existing operator UID1000 required" >&2; exit 2
fi

ROOT=/srv/jason/archive
OWNER_UPGRADE="$ROOT/owner-v2-issuer-attested-v2-update-owner-7b42.py"
ROOT_UPGRADE="$ROOT/owner-v2-issuer-attested-v2-root-updater-7b42.py"
FULL_OWNER="$ROOT/owner-v2-issuer-attested-v2-full-health-owner-7b42.py"
FULL_ROOT=/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py
V2_OLD=ff0b81a0cb60c6a76a21b3f45301f7750d4c7d95f044626c35e8ac5b9aaeb9a4
V2_NEW=a328adcf67fc258713bfaac8971490d2f3b5fdb5d409bf1b873813abd82711dc
OWNER_UPGRADE_SHA=4f087109f7aeef53849dae5e34437272d50cccda7d4f4d4557c7cfd82eef5e19
ROOT_UPGRADE_SHA=470f2dafa050ecbc81c6b1c8121da643678ffbd4d280c7bf8ec64de347461b9a
FULL_OWNER_SHA=deda7b16467148136c3206e5d041eca1b200a9da24e32e203ff234b0a14d66a3
POLICY_HASH=0c592b24a96be57754ff96973e58e7309da6ed502bb7021d303fa839c3cf7ecd
STAGED=/run/jason-owner-v2-issuer-v2-root-updater-7b42ce983896.py
CREATED=0

for record in "$OWNER_UPGRADE_SHA|$OWNER_UPGRADE" "$ROOT_UPGRADE_SHA|$ROOT_UPGRADE" "$FULL_OWNER_SHA|$FULL_OWNER"; do
  digest="${record%%|*}"; name="${record#*|}"
  printf '%s  %s\n' "$digest" "$name" | sha256sum -c - >/dev/null
done
current="$(sha256sum "$FULL_ROOT" | cut -d' ' -f1)"
if [[ "$current" != "$V2_OLD" && "$current" != "$V2_NEW" ]]; then
  echo "DENIED: full-integrity root helper not either reviewed revision" >&2; exit 2
fi
/usr/bin/python3 -B "$OWNER_UPGRADE" --check-only
echo "EXACT_V2_ISSUER_AWARE_PACKET_AND_OWNER_PREFLIGHT=PASS"
echo "CURRENT_FULL_INTEGRITY_ROOT_HELPER_SHA=$current"
echo "NO_ROOT_INSTALL_OR_FULL_SCAN_IN_CHECK_MODE=true"

if [[ "$MODE" == "--check-only" ]]; then exit 0; fi
if [[ ! -t 0 || ! -t 1 ]]; then
  echo "DENIED: real local interactive Owner SSH terminal required" >&2; exit 2
fi

if [[ "$current" == "$V2_OLD" ]]; then
  echo "PHASE_1: obtain exact Entra Owner consent for ONLY the V2 health two-file root-code/policy upgrade."
  /usr/bin/python3 -B "$OWNER_UPGRADE" --authorize
  if [[ -e "$STAGED" || -L "$STAGED" ]]; then
    echo "DENIED: fixed root staging path already occupied" >&2; exit 2
  fi
  cleanup() {
    if [[ "$CREATED" == 1 ]]; then sudo /usr/bin/rm -f -- "$STAGED"; fi
  }
  trap cleanup EXIT
  sudo /usr/bin/install -o root -g root -m 0400 -- "$ROOT_UPGRADE" "$STAGED"
  CREATED=1
  printf '%s  %s\n' "$ROOT_UPGRADE_SHA" "$STAGED" | sudo /usr/bin/sha256sum -c -
  sudo /usr/bin/python3 -I "$STAGED" --execute
  printf '%s  %s\n' "$V2_NEW" "$FULL_ROOT" | sha256sum -c -
  echo "EXACT_V2_ISSUER_AWARE_ROOT_CODE_POLICY=INSTALLED_VERIFIED"
else
  echo "PHASE_1: exact V2 issuer-aware root helper already present; do not replay."
fi

echo "PHASE_2: independent READ-ONLY full-integrity root preflight (must pass)."
sudo /usr/bin/python3 -I "$FULL_ROOT" --check-only

echo "PHASE_3: authenticate a DIFFERENT exact Entra Owner approval for real full four-database integrity + backup/restore."
/usr/bin/python3 -B "$FULL_OWNER" --authorize

echo "PHASE_4: run native bounded full four-database integrity/restore and verified release-breaker recovery. No shortcuts."
sudo /usr/bin/python3 -I "$FULL_ROOT" --execute

/usr/bin/python3 - <<'PY'
import json,datetime,pathlib,subprocess
root=pathlib.Path('/var/lib/jason/openclaw/release-manager/protected-readback')
control=json.loads((root/'production-control-state.json').read_bytes())
drift=json.loads((root/'production-drift.json').read_bytes())
st=datetime.datetime.fromisoformat(drift['observed_at'].replace('Z','+00:00'))
age=(datetime.datetime.now(datetime.timezone.utc)-st).total_seconds()
if (control.get('circuit_breaker',{}).get('state')!='closed'
    or drift.get('status')!='pass' or drift.get('problems')!=[]
    or st.tzinfo is None or not -10<=age<=180):
    raise SystemExit('DENIED: native breaker and fresh root drift not verified')
for unit in ('jason-openclaw-authority-full-integrity.service',
             'jason-openclaw-authority-health.service'):
    result=subprocess.check_output(['systemctl','show',unit,
                                    '-p','Result','-p','ExecMainStatus'],text=True)
    record=dict(x.split('=',1) for x in result.splitlines() if '=' in x)
    if record.get('Result')!='success' or record.get('ExecMainStatus')!='0':
        raise SystemExit('DENIED: required full/fast health service not successful')
print('GENUINE_FULL_SQLITE_AND_NATIVE_BREAKER_RECOVERY=VERIFIED')
PY
echo "NEXT=SEPARATELY_GOVERNED_STAGE_A0_ROOT_CLOSURE"
