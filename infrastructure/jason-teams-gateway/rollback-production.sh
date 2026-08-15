#!/usr/bin/env bash
set -eu

SERVICE_DIR="${JASON_TEAMS_SERVICE_DIR:-/opt/jason/services/jason-teams-gateway}"
STATE_FILE="$SERVICE_DIR/cutover-state.env"
OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-openclaw-gateway-1}"

if [ ! -f "$STATE_FILE" ]; then
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: cutover state file not found: $STATE_FILE"
  exit 1
fi

# shellcheck disable=SC1090
. "$STATE_FILE"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: compose backup not found: $BACKUP_FILE"
  exit 1
fi

echo "========== DIRECT TEAMS ROLLBACK =========="
echo "BACKUP_FILE=$BACKUP_FILE"
echo "OPENCLAW_SERVICE=$OPENCLAW_SERVICE"
echo "OPENCLAW_PROJECT=$OPENCLAW_PROJECT"

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
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: OpenClaw container not found after rollback"
  exit 1
fi

OPENCLAW_STATE="$(docker inspect "$OPENCLAW_CONTAINER" --format '{{.State.Status}}')"
OPENCLAW_3978="$(docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | tr '\n' ' ' || true)"

echo "OPENCLAW_STATE=$OPENCLAW_STATE"
echo "OPENCLAW_3978=$OPENCLAW_3978"

if [ "$OPENCLAW_STATE" != "running" ]; then
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: OpenClaw is not running"
  exit 1
fi
if [ -z "$OPENCLAW_3978" ]; then
  echo "ROLLBACK_STATUS=FAIL"
  echo "ERROR: OpenClaw did not regain host port 3978"
  exit 1
fi

echo "ROLLBACK_STATUS=PASS"
echo "OpenClaw again owns the original Teams ingress port."
