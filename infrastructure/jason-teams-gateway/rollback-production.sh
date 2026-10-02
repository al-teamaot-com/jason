#!/usr/bin/env bash
set -eu

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_DIR="${JASON_TEAMS_SERVICE_DIR:-/opt/jason/services/jason-teams-gateway}"
STATE_FILE="$SERVICE_DIR/cutover-state.env"
OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-openclaw-gateway-1}"
PROMOTION_PERMIT="${JASON_PRODUCTION_ROLLBACK_PERMIT:-${JASON_PRODUCTION_PROMOTION_PERMIT:-}}"
REQUESTED_PLAN_SHA256="${JASON_PRODUCTION_PLAN_SHA256:-}"
PREFLIGHT_ONLY=false
if [ "${1:-}" = "--preflight" ]; then
  PREFLIGHT_ONLY=true
  shift
fi
if [ "$#" -ne 0 ]; then
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: unsupported arguments"
  exit 2
fi

fail() {
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: $*"
  exit 1
}

if [ ! -f "$STATE_FILE" ]; then
  fail "cutover state file not found: $STATE_FILE"
fi

# shellcheck disable=SC1090
. "$STATE_FILE"

[ -f "$BACKUP_FILE" ] || fail "compose backup not found: $BACKUP_FILE"
[ -n "${GATEWAY_SOURCE_SHA:-}" ] || fail "cutover state is missing GATEWAY_SOURCE_SHA"
[ -n "${BACKUP_SHA256:-}" ] || fail "cutover state is missing BACKUP_SHA256"

ACTUAL_BACKUP_SHA256="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
if [ "$ACTUAL_BACKUP_SHA256" != "$BACKUP_SHA256" ]; then
  fail "compose backup digest does not match cutover state"
fi
ROLLBACK_ARTIFACT_DIGEST="sha256:$ACTUAL_BACKUP_SHA256"

echo "========== DIRECT TEAMS ROLLBACK PREFLIGHT =========="
echo "BACKUP_FILE=$BACKUP_FILE"
echo "BACKUP_SHA256=$ACTUAL_BACKUP_SHA256"
echo "GATEWAY_SOURCE_SHA=$GATEWAY_SOURCE_SHA"
echo "OPENCLAW_SERVICE=$OPENCLAW_SERVICE"
echo "OPENCLAW_PROJECT=$OPENCLAW_PROJECT"

if [ "$PREFLIGHT_ONLY" = "true" ]; then
  echo "ROLLBACK_STATUS=PREFLIGHT_ONLY"
  exit 0
fi

[ -n "$PROMOTION_PERMIT" ] || fail "Production rollback requires a signed rollback permit"
[ -n "$REQUESTED_PLAN_SHA256" ] || fail "Production rollback requires JASON_PRODUCTION_PLAN_SHA256"
CUTOVER_PLAN_SHA256="${PROMOTION_PLAN_SHA256:-}"
[ -n "$CUTOVER_PLAN_SHA256" ] || fail "cutover state is missing PROMOTION_PLAN_SHA256"
if [ "$REQUESTED_PLAN_SHA256" != "$CUTOVER_PLAN_SHA256" ]; then
  fail "rollback plan digest does not match cutover state"
fi

python3 "$REPO_ROOT/tools/claim_production_promotion_permit.py" \
  --permit "$PROMOTION_PERMIT" \
  --component jason-teams-gateway \
  --operation rollback \
  --source-sha "$GATEWAY_SOURCE_SHA" \
  --artifact-digest "$ROLLBACK_ARTIFACT_DIGEST" \
  --plan-sha256 "$REQUESTED_PLAN_SHA256" \
  || fail "Production rollback permit verification/claim failed"

echo "PRODUCTION_PROMOTION_ROLLBACK_GATE=PASS"

echo
echo "========== STOP DIRECT JASON TEAMS GATEWAY =========="
docker rm -f "$GATEWAY_CONTAINER" >/dev/null 2>&1 || true

echo
echo "========== RESTORE OPENCLAW COMPOSE =========="
sudo cp "$BACKUP_FILE" "$OPENCLAW_COMPOSE_FILE"

(
  cd "$OPENCLAW_WORKDIR"
  docker compose -p "$OPENCLAW_PROJECT" -f "$OPENCLAW_COMPOSE_FILE" up -d "$OPENCLAW_SERVICE"
)

sleep 6

echo
echo "========== VERIFY ROLLBACK =========="
if ! docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1; then
  fail "OpenClaw container not found after rollback"
fi

OPENCLAW_STATE="$(docker inspect "$OPENCLAW_CONTAINER" --format '{{.State.Status}}')"
OPENCLAW_3978="$(docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | tr '\n' ' ' || true)"

echo "OPENCLAW_STATE=$OPENCLAW_STATE"
echo "OPENCLAW_3978=$OPENCLAW_3978"

if [ "$OPENCLAW_STATE" != "running" ]; then
  fail "OpenClaw is not running"
fi
if [ -z "$OPENCLAW_3978" ]; then
  fail "OpenClaw did not regain host port 3978"
fi

echo "ROLLBACK_STATUS=PASS"
echo "OpenClaw again owns the original Teams ingress port."
