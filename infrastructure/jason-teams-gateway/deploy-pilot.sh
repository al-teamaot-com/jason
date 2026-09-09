#!/usr/bin/env bash
set -eu

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-openclaw-gateway-1}"
RUNTIME_CONTAINER="${RUNTIME_CONTAINER:-jason-runtime}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-jason-teams-gateway-pilot}"
IMAGE="${IMAGE:-jason-teams-gateway:pilot}"
HOST_BIND="${JASON_TEAMS_HOST_BIND:-127.0.0.1}"
HOST_PORT="${JASON_TEAMS_HOST_PORT:-3979}"
SERVICE_DIR="${JASON_TEAMS_SERVICE_DIR:-/opt/jason/services/jason-teams-gateway}"
OPENCLAW_CONFIG_HOST="${OPENCLAW_CONFIG_HOST:-/opt/jason/services/openclaw/data/config/openclaw.json}"
OPENCLAW_KEY_CONTAINER="${OPENCLAW_KEY_CONTAINER:-/home/node/.config/openclaw/jason-ingress/openclaw-jason-ed25519-v2.pem}"
RUN_UID="$(id -u)"
RUN_GID="$(id -g)"

if [ ! -f infrastructure/jason-teams-gateway/Dockerfile ]; then
  echo "ERROR: run this script from the Jason repository root"
  exit 1
fi
if [ ! -f "$OPENCLAW_CONFIG_HOST" ]; then
  echo "ERROR: OpenClaw config not found at $OPENCLAW_CONFIG_HOST"
  exit 1
fi
if ! docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: OpenClaw container not found: $OPENCLAW_CONTAINER"
  exit 1
fi
if ! docker inspect "$RUNTIME_CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: Jason runtime container not found: $RUNTIME_CONTAINER"
  exit 1
fi

NETWORK="$(docker inspect "$RUNTIME_CONTAINER" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' | head -n 1 | tr -d '\r')"
if [ -z "$NETWORK" ]; then
  echo "ERROR: could not resolve Jason runtime Docker network"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/secrets"

has_complete_teams_env() {
  file="$1"
  [ -f "$file" ] &&
    grep -q '^MSTEAMS_APP_ID=.' "$file" &&
    grep -q '^MSTEAMS_TENANT_ID=.' "$file" &&
    grep -q '^MSTEAMS_APP_PASSWORD=.' "$file"
}

echo "========== BUILD DIRECT TEAMS GATEWAY =========="
docker build \
  -f infrastructure/jason-teams-gateway/Dockerfile \
  -t "$IMAGE" \
  .

echo
echo "========== COPY EXISTING GOVERNED INGRESS IDENTITY =========="
docker cp \
  "$OPENCLAW_CONTAINER:$OPENCLAW_KEY_CONTAINER" \
  "$TMP_DIR/secrets/ingress.pem"

# Reuse env-backed OpenClaw credentials only when all required values are
# actually present. Otherwise preserve the dedicated Jason credential file
# created by bootstrap-azure-credential.sh. Never print secret values.
docker inspect "$OPENCLAW_CONTAINER" \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^MSTEAMS_(APP_ID|APP_PASSWORD|TENANT_ID)=' \
  > "$TMP_DIR/openclaw-msteams.env" || true

sudo mkdir -p "$SERVICE_DIR/secrets"
sudo install -m 0600 -o "$RUN_UID" -g "$RUN_GID" \
  "$TMP_DIR/secrets/ingress.pem" \
  "$SERVICE_DIR/secrets/ingress.pem"

if has_complete_teams_env "$TMP_DIR/openclaw-msteams.env"; then
  sudo install -m 0600 -o "$RUN_UID" -g "$RUN_GID" \
    "$TMP_DIR/openclaw-msteams.env" \
    "$SERVICE_DIR/msteams.env"
  echo "PASS: complete env-backed Teams credentials copied from OpenClaw"
elif has_complete_teams_env "$SERVICE_DIR/msteams.env"; then
  echo "PASS: using existing dedicated Jason Teams credential"
else
  echo "CREDENTIAL_BOOTSTRAP_REQUIRED=1"
  echo "ERROR: OpenClaw does not expose complete Teams credentials through its container environment."
  echo "Run infrastructure/jason-teams-gateway/bootstrap-azure-credential.sh once, then rerun this pilot."
  exit 3
fi

echo "PASS: governed signing identity staged without printing secret material"

echo
echo "========== START ISOLATED PILOT =========="
docker rm -f "$GATEWAY_CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$GATEWAY_CONTAINER" \
  --restart unless-stopped \
  --user "$RUN_UID:$RUN_GID" \
  --network "$NETWORK" \
  --env-file "$SERVICE_DIR/msteams.env" \
  -e PORT=3979 \
  -e OPENCLAW_CONFIG_PATH=/run/openclaw/openclaw.json \
  -e JASON_RUNTIME_URL=http://jason-runtime:8080/v1/openclaw/teams/conversation \
  -e JASON_INGRESS_KEY_ID=openclaw-gateway-2 \
  -e JASON_INGRESS_PRIVATE_KEY_PATH=/run/jason/ingress.pem \
  -p "$HOST_BIND:$HOST_PORT:3979" \
  -v "$OPENCLAW_CONFIG_HOST:/run/openclaw/openclaw.json:ro" \
  -v "$SERVICE_DIR/secrets/ingress.pem:/run/jason/ingress.pem:ro" \
  "$IMAGE" >/dev/null

sleep 4

echo
echo "========== PILOT HEALTH =========="
if ! docker exec "$GATEWAY_CONTAINER" node -e \
  "fetch('http://127.0.0.1:3979/healthz').then(async r=>{console.log(await r.text()); if(!r.ok) process.exit(1)}).catch(e=>{console.error(e);process.exit(1)})"
then
  echo "PILOT_STATUS=FAIL"
  docker logs --tail 50 "$GATEWAY_CONTAINER" 2>&1 || true
  exit 1
fi

printf '\n========== CURRENT TEAMS EDGE FACTS ==========\n'
printf 'DIRECT_GATEWAY_LOCAL=http://%s:%s/api/messages\n' "$HOST_BIND" "$HOST_PORT"
printf 'OPENCLAW_3978_BINDING=%s\n' "$(docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | tr '\n' ' ' || true)"
printf 'OPENCLAW_COMPOSE_WORKDIR=%s\n' "$(docker inspect "$OPENCLAW_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
printf 'OPENCLAW_COMPOSE_FILES=%s\n' "$(docker inspect "$OPENCLAW_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)"

echo
echo "========== SERVICES =========="
docker ps \
  --filter "name=$GATEWAY_CONTAINER" \
  --filter "name=$RUNTIME_CONTAINER" \
  --filter "name=$OPENCLAW_CONTAINER" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo
echo "PILOT_STATUS=PASS"
echo "No OpenClaw code, hooks, packages, or Azure Bot settings were modified."
