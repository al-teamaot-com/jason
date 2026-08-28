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

bot_field() {
  local bot_id="$1"
  local field="$2"
  local value=""
  local subscription=""
  local resource_group=""
  local bot_name=""

  value="$(run_az resource show \
    --ids "$bot_id" \
    --query "properties.${field}" \
    -o tsv \
    --only-show-errors 2>/dev/null | tr -d '\r' || true)"
  if [ -n "$value" ] && [ "$value" != "None" ]; then
    printf '%s' "$value"
    return 0
  fi

  subscription="$(printf '%s' "$bot_id" | cut -d/ -f3)"
  resource_group="$(printf '%s' "$bot_id" | cut -d/ -f5)"
  bot_name="$(printf '%s' "$bot_id" | cut -d/ -f9)"
  value="$(run_az bot show \
    --subscription "$subscription" \
    --resource-group "$resource_group" \
    --name "$bot_name" \
    --query "$field" \
    -o tsv \
    --only-show-errors 2>/dev/null | tr -d '\r' || true)"
  if [ "$value" = "None" ]; then
    value=""
  fi
  printf '%s' "$value"
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
if [ -z "$SUBSCRIPTIONS" ]; then
  echo "ERROR: no enabled Azure subscriptions are visible for tenant $TENANT_ID"
  exit 1
fi

# Generic 'az resource list' output is not guaranteed to include provider properties.
# Enumerate Bot Service resource IDs first, then read each resource individually.
for SUB in $SUBSCRIPTIONS; do
  BOT_IDS="$(run_az resource list \
    --subscription "$SUB" \
    --resource-type Microsoft.BotService/botServices \
    --query '[].id' \
    -o tsv \
    --only-show-errors 2>/dev/null || true)"

  for BOT_ID in $BOT_IDS; do
    CANDIDATE_APP_ID="$(bot_field "$BOT_ID" msaAppId)"
    if [ "$CANDIDATE_APP_ID" = "$APP_ID" ]; then
      printf '%s\n' "$BOT_ID" >> "$FOUND_FILE"
    fi
  done
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
BOT_ENDPOINT="$(bot_field "$BOT_ID" endpoint)"
BOT_APP_TYPE="$(bot_field "$BOT_ID" msaAppType)"

if [ -z "$BOT_ENDPOINT" ]; then
  echo "ERROR: Azure Bot resource has no readable messaging endpoint"
  exit 1
fi

echo "BOT_NAME=$BOT_NAME"
echo "BOT_RESOURCE_GROUP=$BOT_RESOURCE_GROUP"
echo "BOT_SUBSCRIPTION=$BOT_SUBSCRIPTION"
echo "BOT_APP_TYPE=$BOT_APP_TYPE"
echo "BOT_ENDPOINT=$BOT_ENDPOINT"

echo
echo "========== LOCAL EDGE =========="
echo "OPENCLAW_3978_BINDING=$(docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | tr '\n' ' ' || true)"
echo "JASON_PILOT_3979_BINDING=$(docker port jason-teams-gateway-pilot 3979/tcp 2>/dev/null | tr '\n' ' ' || true)"
echo "OPENCLAW_COMPOSE_PROJECT=$(docker inspect -f '{{ index .Config.Labels \"com.docker.compose.project\" }}' "$OPENCLAW_CONTAINER" 2>/dev/null || true)"
echo "OPENCLAW_COMPOSE_SERVICE=$(docker inspect -f '{{ index .Config.Labels \"com.docker.compose.service\" }}' "$OPENCLAW_CONTAINER" 2>/dev/null || true)"
echo "OPENCLAW_COMPOSE_WORKDIR=$(docker inspect -f '{{ index .Config.Labels \"com.docker.compose.project.working_dir\" }}' "$OPENCLAW_CONTAINER" 2>/dev/null || true)"
echo "OPENCLAW_COMPOSE_CONFIG_FILES=$(docker inspect -f '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' "$OPENCLAW_CONTAINER" 2>/dev/null || true)"

echo
echo "========== RELEVANT HOST LISTENERS =========="
if command -v ss >/dev/null 2>&1; then
  ss -ltn 2>/dev/null | awk 'NR == 1 || $4 ~ /:(80|443|3978|3979)$/' || true
else
  echo "INFO: ss is unavailable"
fi

echo
echo "========== RELEVANT DOCKER PORTS =========="
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null \
  | awk 'BEGIN {print "NAME\tIMAGE\tPORTS"} /(^|[,:])80->|(^|[,:])443->|3978->|3979->|:80-|:443-/ {print}' || true

if [ -f "$OPENCLAW_COMPOSE_FILE" ]; then
  echo
echo "OPENCLAW_COMPOSE_FILE=$OPENCLAW_COMPOSE_FILE"
  echo "--- compose lines mentioning 3978 ---"
  grep -n -C 4 '3978' "$OPENCLAW_COMPOSE_FILE" || true
else
  echo "OPENCLAW_COMPOSE_FILE_NOT_FOUND=$OPENCLAW_COMPOSE_FILE"
fi

echo
echo "DISCOVERY_STATUS=PASS"
echo "No Azure, Teams, Docker, OpenClaw, or Jason configuration was changed."
