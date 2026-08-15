#!/usr/bin/env bash
set -eu

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-openclaw-gateway-1}"
OPENCLAW_COMPOSE_FILE="${OPENCLAW_COMPOSE_FILE:-/opt/jason/services/openclaw/docker-compose.yml}"
AZURE_CLI_IMAGE="${AZURE_CLI_IMAGE:-mcr.microsoft.com/azure-cli:latest}"

if ! docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: OpenClaw container not found: $OPENCLAW_CONTAINER"
  exit 1
fi

APP_ID="$(docker exec "$OPENCLAW_CONTAINER" openclaw config get channels.msteams.appId 2>/dev/null | tr -d '\r' | tail -n 1)"
TENANT_ID="$(docker exec "$OPENCLAW_CONTAINER" openclaw config get channels.msteams.tenantId 2>/dev/null | tr -d '\r' | tail -n 1)"

run_az() {
  if command -v az >/dev/null 2>&1; then
    az "$@"
  else
    mkdir -p "$HOME/.azure"
    docker run --rm -i \
      -v "$HOME/.azure:/root/.azure" \
      "$AZURE_CLI_IMAGE" \
      az "$@"
  fi
}

echo "========== DIRECT TEAMS CUTOVER DISCOVERY =========="
echo "APP_ID=$APP_ID"
echo "TENANT_ID=$TENANT_ID"

echo
echo "========== AZURE SESSION =========="
if ! run_az account show --only-show-errors >/dev/null 2>&1; then
  echo "ERROR: Azure CLI session is not available. Re-run the credential bootstrap login first."
  exit 1
fi

echo "PASS: Azure CLI session available"

echo
echo "========== FIND AZURE BOT RESOURCE =========="
FOUND_FILE="$(mktemp)"
trap 'rm -f "$FOUND_FILE"' EXIT
: > "$FOUND_FILE"

SUBSCRIPTIONS="$(run_az account list --all --query "[?tenantId=='$TENANT_ID' && state=='Enabled'].id" -o tsv --only-show-errors)"

for SUB in $SUBSCRIPTIONS; do
  run_az resource list \
    --subscription "$SUB" \
    --resource-type Microsoft.BotService/botServices \
    --query "[?properties.msaAppId=='$APP_ID'].id" \
    -o tsv \
    --only-show-errors >> "$FOUND_FILE" || true
done

BOT_COUNT="$(grep -c '^/' "$FOUND_FILE" || true)"
if [ "$BOT_COUNT" -ne 1 ]; then
  echo "ERROR: expected exactly one Azure Bot resource for APP_ID=$APP_ID; found $BOT_COUNT"
  if [ "$BOT_COUNT" -gt 0 ]; then
    sed 's/^/BOT_RESOURCE=/' "$FOUND_FILE"
  fi
  exit 1
fi

BOT_ID="$(head -n 1 "$FOUND_FILE" | tr -d '\r')"
BOT_SUBSCRIPTION="$(printf '%s' "$BOT_ID" | cut -d/ -f3)"
BOT_RESOURCE_GROUP="$(printf '%s' "$BOT_ID" | cut -d/ -f5)"
BOT_NAME="$(printf '%s' "$BOT_ID" | cut -d/ -f9)"
BOT_ENDPOINT="$(run_az resource show --ids "$BOT_ID" --query properties.endpoint -o tsv --only-show-errors | tr -d '\r')"
BOT_APP_TYPE="$(run_az resource show --ids "$BOT_ID" --query properties.msaAppType -o tsv --only-show-errors | tr -d '\r')"

echo "BOT_NAME=$BOT_NAME"
echo "BOT_RESOURCE_GROUP=$BOT_RESOURCE_GROUP"
echo "BOT_SUBSCRIPTION=$BOT_SUBSCRIPTION"
echo "BOT_APP_TYPE=$BOT_APP_TYPE"
echo "BOT_ENDPOINT=$BOT_ENDPOINT"

echo
echo "========== LOCAL EDGE =========="
echo "OPENCLAW_3978_BINDING=$(docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | tr '\n' ' ' || true)"
echo "JASON_PILOT_3979_BINDING=$(docker port jason-teams-gateway-pilot 3979/tcp 2>/dev/null | tr '\n' ' ' || true)"

if [ -f "$OPENCLAW_COMPOSE_FILE" ]; then
  echo "OPENCLAW_COMPOSE_FILE=$OPENCLAW_COMPOSE_FILE"
  echo "--- compose lines mentioning 3978 ---"
  grep -n -C 3 '3978' "$OPENCLAW_COMPOSE_FILE" || true
else
  echo "OPENCLAW_COMPOSE_FILE_NOT_FOUND=$OPENCLAW_COMPOSE_FILE"
fi

echo
echo "DISCOVERY_STATUS=PASS"
echo "No Azure, Teams, Docker, OpenClaw, or Jason configuration was changed."
