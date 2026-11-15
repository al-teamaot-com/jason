#!/usr/bin/env bash
# One Owner-local command; each protected subaction remains independently signed.
# Native integrity recovery (when genuinely needed) precedes Stage A0 root
# source repair. This does NOT issue the final Stage A0 native install approval.
set -Eeuo pipefail
umask 077
MODE="${1:-}"
if [[ "$MODE" != "--check-only" && "$MODE" != "--execute" ]]; then
  echo "DENIED: choose --check-only or --execute" >&2; exit 2
fi
if [[ "$(id -u)" != 1000 ]]; then
  echo "DENIED: original Owner-local al UID1000 required" >&2; exit 2
fi

ROOT=/srv/jason/archive
HEALTH="$ROOT/owner-v2-issuer-aware-v2-local-7b42.sh"
CLOSURE="$ROOT/pmv4-a0-closure-owner-local-7b42.sh"
HEALTH_SHA="de4519df425d796d1f7cc3e8270c4a427b05ff9621c1955bc6b7d367c43e65eb"
CLOSURE_SHA="3ba8b330c0d5efd79e2f9a92f2348e703eef42f9b2837b18237522854b7fc49f"
SOURCE="7b42ce983896711525de4c7955bf9fc43ac003d0"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
MCP="sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
RUNTIME="sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
FREEZE="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
for item in "$HEALTH_SHA|$HEALTH" "$CLOSURE_SHA|$CLOSURE"; do
  expected="${item%%|*}"; file="${item#*|}"
  printf '%s  %s\n' "$expected" "$file" | sha256sum -c - >/dev/null
done
if [[ "$(git -C /home/al/.local/lib/jason/engineering-source-repo rev-parse origin/main)" != "$SOURCE" ]]; then
  echo "DENIED: protected main changed" >&2; exit 2
fi
if [[ "$(readlink -f /opt/jason/current)" != "/opt/jason/releases/$LKG" ]]; then
  echo "DENIED: production current pointer changed" >&2; exit 2
fi
if [[ "$(sha256sum /var/lib/jason/openclaw/release-manager/production-deployment-freeze | cut -d' ' -f1)" != "$FREEZE" ]]; then
  echo "DENIED: freeze changed" >&2; exit 2
fi
if [[ "$(sha256sum /var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold | cut -d' ' -f1)" != "$HOLD" ]]; then
  echo "DENIED: promotion hold changed" >&2; exit 2
fi
IMAGES="$(docker inspect jason-runtime jason-mcp-pilot --format '{{.Name}} {{.Image}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}')"
if [[ "$IMAGES" != *"/jason-runtime $RUNTIME running healthy"* || "$IMAGES" != *"/jason-mcp-pilot $MCP running"* ]]; then
  echo "DENIED: protected MCP or ticket runtime changed" >&2; exit 2
fi
if [[ "$(docker inspect jason-mcp-pilot --format '{{json .Config.Env}}')" != *'"JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true"'* ]]; then
  echo "DENIED: previously approved exact same-image issuer not enabled" >&2; exit 2
fi

# Read-only exact source+Owner attestations before asking for any new consent.
bash "$HEALTH" --check-only
bash "$CLOSURE" --check-only
STATE="$(/usr/bin/python3 - <<'PY'
import json,pathlib
root=pathlib.Path('/var/lib/jason/openclaw/release-manager/protected-readback')
c=json.loads((root/'production-control-state.json').read_bytes())
d=json.loads((root/'production-drift.json').read_bytes())
state=c.get('circuit_breaker',{}).get('state')
problems=d.get('problems')
if state=='closed' and d.get('status')=='pass' and problems==[]:
 print('HEALTHY')
elif (state=='open' and c.get('circuit_breaker',{}).get('reason')=='continuous_production_drift_detected'
      and d.get('status')=='drift_detected'
      and problems==[{'kind':'failed_system_unit','state':'failed',
                      'unit':'jason-openclaw-authority-health.service'}]):
 print('RECOVERABLE_V2_FULL_PROOF')
else:
 raise SystemExit('DENIED: other drift or root breaker issue')
PY
)"
echo "EXACT_OWNER_CHAIN_PREFLIGHT=PASS"
echo "PRODUCTION_HEALTH_STATE=$STATE"
echo "NO_PRODUCTION_ACTION_OR_OWNER_SIGNATURE_FROM_PREFLIGHT=true"
if [[ "$MODE" == "--check-only" ]]; then exit 0; fi
if [[ ! -t 0 || ! -t 1 ]]; then
  echo "DENIED: real interactive local Owner terminal required" >&2; exit 2
fi

if [[ "$STATE" == "RECOVERABLE_V2_FULL_PROOF" ]]; then
  echo "STEP 1/2: new exact Owner attestations for the V2 root health updater and genuine full integrity recovery."
  bash "$HEALTH" --execute
else
  echo "STEP 1/2: native breaker and drift already PASS; no redundant health repair."
fi

/usr/bin/python3 - <<'PY'
import datetime,json,pathlib
root=pathlib.Path('/var/lib/jason/openclaw/release-manager/protected-readback')
c=json.loads((root/'production-control-state.json').read_bytes())
d=json.loads((root/'production-drift.json').read_bytes())
stamp=datetime.datetime.fromisoformat(d['observed_at'].replace('Z','+00:00'))
age=(datetime.datetime.now(datetime.timezone.utc)-stamp).total_seconds()
if (c.get('circuit_breaker',{}).get('state')!='closed'
    or d.get('status')!='pass' or d.get('problems')!=[]
    or stamp.tzinfo is None or not -10<=age<=180):
 raise SystemExit('DENIED: full-health verified breaker/drift not ready for Stage A0')
print('BREAKERMODE=VERIFIED_CLOSED_AND_FRESH_DRIFT_PASS')
PY

echo "STEP 2/2: new exact Owner attestations for root source helper bootstrap and ONE missing immutable file."
bash "$CLOSURE" --execute
echo "PROTECTED_STAGE_A0_SOURCE_CLOSURE=VERIFIED"
echo "NEXT=SEPARATE_AUTHENTICATED_STAGE_A0_NATIVE_INSTALL_VIA_JASON_MCP"
