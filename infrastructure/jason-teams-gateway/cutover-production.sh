#!/usr/bin/env bash
set -eu

OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-openclaw-openclaw-gateway-1}"
RUNTIME_CONTAINER="${RUNTIME_CONTAINER:-jason-runtime}"
OPENCLAW_COMPOSE_FILE="${OPENCLAW_COMPOSE_FILE:-/opt/jason/services/openclaw/docker-compose.yml}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-jason-teams-gateway}"
PILOT_CONTAINER="${PILOT_CONTAINER:-jason-teams-gateway-pilot}"
IMAGE="${JASON_TEAMS_PRODUCTION_IMAGE:-jason-teams-gateway:production}"
PROMOTION_PERMIT="${JASON_PRODUCTION_PROMOTION_PERMIT:-}"
PROMOTION_PLAN_SHA256="${JASON_PRODUCTION_PLAN_SHA256:-}"
SERVICE_DIR="${JASON_TEAMS_SERVICE_DIR:-/opt/jason/services/jason-teams-gateway}"
HOST_PORT="${JASON_TEAMS_HOST_PORT:-3978}"
CONTAINER_PORT="${JASON_TEAMS_CONTAINER_PORT:-3979}"
RUN_UID="$(id -u)"
RUN_GID="$(id -g)"
STATE_FILE="$SERVICE_DIR/cutover-state.env"
PREFLIGHT_ONLY=false
if [ "${1:-}" = "--preflight" ]; then
  PREFLIGHT_ONLY=true
  shift
fi
if [ "$#" -ne 0 ]; then
  echo "CUTOVER_STATUS=FAIL"
  echo "ERROR: unsupported arguments"
  exit 2
fi

fail() {
  echo "CUTOVER_STATUS=FAIL"
  echo "ERROR: $*"
  exit 1
}

if [ ! -f infrastructure/jason-teams-gateway/Dockerfile ]; then
  fail "run this script from the Jason repository root"
fi
if [ ! -f "$OPENCLAW_COMPOSE_FILE" ]; then
  fail "OpenClaw compose file not found: $OPENCLAW_COMPOSE_FILE"
fi
if [ ! -s "$SERVICE_DIR/msteams.env" ]; then
  fail "dedicated Jason Teams credential file is missing"
fi
if [ ! -s "$SERVICE_DIR/secrets/ingress.pem" ]; then
  fail "Jason governed ingress signing key is missing"
fi
if ! docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1; then
  fail "OpenClaw container not found: $OPENCLAW_CONTAINER"
fi
if ! docker inspect "$RUNTIME_CONTAINER" >/dev/null 2>&1; then
  fail "Jason runtime container not found: $RUNTIME_CONTAINER"
fi

OPENCLAW_SERVICE="$(docker inspect "$OPENCLAW_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.service"}}' 2>/dev/null || true)"
OPENCLAW_PROJECT="$(docker inspect "$OPENCLAW_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
OPENCLAW_WORKDIR="$(docker inspect "$OPENCLAW_CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
NETWORK="$(docker inspect "$RUNTIME_CONTAINER" --format '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' | head -n 1 | tr -d '\r')"

[ -n "$OPENCLAW_SERVICE" ] || fail "could not resolve OpenClaw compose service"
[ -n "$OPENCLAW_PROJECT" ] || fail "could not resolve OpenClaw compose project"
[ -n "$OPENCLAW_WORKDIR" ] || fail "could not resolve OpenClaw compose working directory"
[ -n "$NETWORK" ] || fail "could not resolve Jason runtime Docker network"

if ! docker inspect "$PILOT_CONTAINER" >/dev/null 2>&1; then
  fail "healthy pilot container is not present"
fi
if [ "$(docker inspect "$PILOT_CONTAINER" --format '{{.State.Status}}')" != "running" ]; then
  fail "pilot container is not running"
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  fail "immutable candidate image is not present: $IMAGE"
fi
IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
IMAGE_SOURCE_SHA="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
if [ -z "$IMAGE_SOURCE_SHA" ]; then
  IMAGE_SOURCE_SHA="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || true)"
fi
case "$IMAGE_ID" in
  sha256:????????????????????????????????????????????????????????????????) ;;
  *) fail "candidate image ID is not an immutable sha256 digest" ;;
esac
case "$IMAGE_SOURCE_SHA" in
  ????????????????????????????????????????) ;;
  *) fail "candidate image source revision is not an exact git SHA" ;;
esac

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
LOCAL_NEXT_COMPOSE="$TMP_DIR/docker-compose.next.yml"
PORT_BINDINGS_JSON="$TMP_DIR/port-bindings.json"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NEXT_COMPOSE="${OPENCLAW_COMPOSE_FILE}.jason-next-${TIMESTAMP}"
BACKUP_FILE="${OPENCLAW_COMPOSE_FILE}.pre-jason-teams-${TIMESTAMP}"

rollback_now() {
  echo
  echo "========== AUTOMATIC ROLLBACK =========="
  docker rm -f "$GATEWAY_CONTAINER" >/dev/null 2>&1 || true
  if [ -f "$BACKUP_FILE" ]; then
    sudo cp "$BACKUP_FILE" "$OPENCLAW_COMPOSE_FILE"
    (
      cd "$OPENCLAW_WORKDIR"
      docker compose -p "$OPENCLAW_PROJECT" -f "$OPENCLAW_COMPOSE_FILE" up -d "$OPENCLAW_SERVICE"
    ) >/dev/null 2>&1 || true
  fi
  sudo rm -f "$NEXT_COMPOSE" >/dev/null 2>&1 || true
  echo "ROLLBACK_ATTEMPTED=1"
}

rewrite_ports_from_runtime() {
  docker inspect "$OPENCLAW_CONTAINER" \
    --format '{{json .HostConfig.PortBindings}}' \
    > "$PORT_BINDINGS_JSON"

  python3 - \
    "$OPENCLAW_COMPOSE_FILE" \
    "$OPENCLAW_SERVICE" \
    "$LOCAL_NEXT_COMPOSE" \
    "$PORT_BINDINGS_JSON" \
    "$HOST_PORT" <<'PY'
import json
import re
import sys

src, service_name, dst, bindings_path, release_host_port = sys.argv[1:6]
lines = open(src, encoding="utf-8").read().splitlines(True)
with open(bindings_path, encoding="utf-8") as handle:
    bindings = json.load(handle) or {}

kept = []
removed = []
for target_key, host_bindings in bindings.items():
    if "/" in target_key:
        target, protocol = target_key.rsplit("/", 1)
    else:
        target, protocol = target_key, "tcp"
    for binding in host_bindings or []:
        host_port = str(binding.get("HostPort") or "").strip()
        host_ip = str(binding.get("HostIp") or "").strip()
        if not host_port:
            continue
        item = {
            "target": target,
            "published": host_port,
            "protocol": protocol or "tcp",
            "host_ip": host_ip,
        }
        if host_port == release_host_port:
            removed.append(item)
        else:
            kept.append(item)

if not removed:
    raise SystemExit(
        f"runtime inspection found no OpenClaw binding on host port {release_host_port}"
    )

# Deduplicate equivalent runtime bindings while preserving order.
def dedupe(items):
    out = []
    seen = set()
    for item in items:
        key = (
            item["target"],
            item["published"],
            item["protocol"],
            item["host_ip"],
        )
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out

kept = dedupe(kept)
removed = dedupe(removed)

services_idx = None
services_indent = None
for i, line in enumerate(lines):
    if re.match(r"^\s*services\s*:\s*(?:#.*)?$", line):
        services_idx = i
        services_indent = len(line) - len(line.lstrip())
        break
if services_idx is None:
    raise SystemExit("compose services section not found")

service_idx = None
service_indent = None
service_re = re.compile(r"^(\s*)" + re.escape(service_name) + r"\s*:\s*(?:#.*)?$")
for i in range(services_idx + 1, len(lines)):
    line = lines[i]
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    indent = len(line) - len(line.lstrip())
    if indent <= services_indent:
        break
    match = service_re.match(line)
    if match:
        service_idx = i
        service_indent = len(match.group(1))
        break
if service_idx is None:
    raise SystemExit(f"compose service not found: {service_name}")

service_end = len(lines)
for i in range(service_idx + 1, len(lines)):
    line = lines[i]
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    indent = len(line) - len(line.lstrip())
    if indent <= service_indent:
        service_end = i
        break

ports_idx = None
ports_indent = None
for i in range(service_idx + 1, service_end):
    match = re.match(r"^(\s*)ports\s*:\s*(?:#.*)?$", lines[i])
    if match:
        ports_idx = i
        ports_indent = len(match.group(1))
        break
if ports_idx is None:
    raise SystemExit("ports section not found in OpenClaw service")

ports_end = service_end
for i in range(ports_idx + 1, service_end):
    line = lines[i]
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    indent = len(line) - len(line.lstrip())
    if indent <= ports_indent:
        ports_end = i
        break

prefix = " " * ports_indent
item_prefix = " " * (ports_indent + 2)
field_prefix = " " * (ports_indent + 4)

if not kept:
    replacement = [f"{prefix}ports: []\n"]
else:
    replacement = [f"{prefix}ports:\n"]
    for item in kept:
        target = item["target"]
        target_yaml = target if target.isdigit() else json.dumps(target)
        replacement.append(f"{item_prefix}- target: {target_yaml}\n")
        replacement.append(
            f"{field_prefix}published: {json.dumps(item['published'])}\n"
        )
        replacement.append(
            f"{field_prefix}protocol: {json.dumps(item['protocol'])}\n"
        )
        if item["host_ip"]:
            replacement.append(
                f"{field_prefix}host_ip: {json.dumps(item['host_ip'])}\n"
            )

out = lines[:ports_idx] + replacement + lines[ports_end:]
open(dst, "w", encoding="utf-8").writelines(out)

for item in removed:
    print(
        "REMOVED_RUNTIME_BINDING="
        f"{item['host_ip'] or '*'}:{item['published']}->{item['target']}/{item['protocol']}"
    )
for item in kept:
    print(
        "PRESERVED_RUNTIME_BINDING="
        f"{item['host_ip'] or '*'}:{item['published']}->{item['target']}/{item['protocol']}"
    )
PY
}

echo "========== PRE-CUTOVER =========="
echo "OPENCLAW_SERVICE=$OPENCLAW_SERVICE"
echo "OPENCLAW_PROJECT=$OPENCLAW_PROJECT"
echo "OPENCLAW_WORKDIR=$OPENCLAW_WORKDIR"
echo "RUNTIME_NETWORK=$NETWORK"
echo "CURRENT_OPENCLAW_3978=$(docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | tr '\n' ' ' || true)"

echo
echo "========== IMMUTABLE CANDIDATE =========="
echo "CANDIDATE_IMAGE=$IMAGE"
echo "CANDIDATE_IMAGE_ID=$IMAGE_ID"
echo "CANDIDATE_SOURCE_SHA=$IMAGE_SOURCE_SHA"
echo "PASS: immutable candidate image is present"

echo
echo "========== PREPARE OPENCLAW PORT RELEASE =========="
rewrite_ports_from_runtime

if ! docker compose \
  --project-directory "$OPENCLAW_WORKDIR" \
  -p "$OPENCLAW_PROJECT" \
  -f "$LOCAL_NEXT_COMPOSE" \
  config >/dev/null
then
  fail "modified OpenClaw compose did not validate"
fi
echo "PASS: modified compose validates"

if [ "$PREFLIGHT_ONLY" = "true" ]; then
  echo "PRODUCTION_PROMOTION_PREFLIGHT=PASS"
  echo "CUTOVER_STATUS=PREFLIGHT_ONLY"
  exit 0
fi

[ -n "$PROMOTION_PERMIT" ] || fail "Production cutover requires JASON_PRODUCTION_PROMOTION_PERMIT"
[ -n "$PROMOTION_PLAN_SHA256" ] || fail "Production cutover requires JASON_PRODUCTION_PLAN_SHA256"

python3 tools/claim_production_promotion_permit.py \
  --permit "$PROMOTION_PERMIT" \
  --component jason-teams-gateway \
  --operation deploy \
  --source-sha "$IMAGE_SOURCE_SHA" \
  --artifact-digest "$IMAGE_ID" \
  --plan-sha256 "$PROMOTION_PLAN_SHA256" \
  || fail "Production promotion permit verification/claim failed"

echo "PRODUCTION_PROMOTION_GATE=PASS"

sudo install -m 0644 "$LOCAL_NEXT_COMPOSE" "$NEXT_COMPOSE"
sudo cp "$OPENCLAW_COMPOSE_FILE" "$BACKUP_FILE"
BACKUP_SHA256="$(sha256sum "$BACKUP_FILE" | awk '{print $1}')"
sudo cp "$NEXT_COMPOSE" "$OPENCLAW_COMPOSE_FILE"
sudo rm -f "$NEXT_COMPOSE"
echo "BACKUP_FILE=$BACKUP_FILE"

echo
echo "========== RELEASE HOST PORT 3978 FROM OPENCLAW =========="
if ! (
  cd "$OPENCLAW_WORKDIR"
  docker compose -p "$OPENCLAW_PROJECT" -f "$OPENCLAW_COMPOSE_FILE" up -d "$OPENCLAW_SERVICE"
); then
  rollback_now
  fail "OpenClaw recreation failed"
fi

sleep 5
if docker port "$OPENCLAW_CONTAINER" 3978/tcp 2>/dev/null | grep -q .; then
  rollback_now
  fail "OpenClaw still publishes host port 3978"
fi

OPENCLAW_STATE="$(docker inspect "$OPENCLAW_CONTAINER" --format '{{.State.Status}}' 2>/dev/null || true)"
if [ "$OPENCLAW_STATE" != "running" ]; then
  rollback_now
  fail "OpenClaw is not running after port release"
fi

echo "PASS: OpenClaw remains running without host port 3978"

echo
echo "========== START DIRECT JASON TEAMS PRODUCTION GATEWAY =========="
docker rm -f "$GATEWAY_CONTAINER" >/dev/null 2>&1 || true

if ! docker run -d \
  --name "$GATEWAY_CONTAINER" \
  --restart unless-stopped \
  --user "$RUN_UID:$RUN_GID" \
  --network "$NETWORK" \
  --env-file "$SERVICE_DIR/msteams.env" \
  -e PORT="$CONTAINER_PORT" \
  -e JASON_RUNTIME_URL=http://jason-runtime:8080/v1/openclaw/teams/conversation \
  -e JASON_INGRESS_KEY_ID=openclaw-gateway-2 \
  -e JASON_INGRESS_PRIVATE_KEY_PATH=/run/jason/ingress.pem \
  -p "0.0.0.0:${HOST_PORT}:${CONTAINER_PORT}" \
  -v "$SERVICE_DIR/secrets/ingress.pem:/run/jason/ingress.pem:ro" \
  "$IMAGE" >/dev/null
then
  rollback_now
  fail "direct Jason Teams gateway failed to start"
fi

sleep 5
if ! docker exec "$GATEWAY_CONTAINER" node -e \
  "fetch('http://127.0.0.1:${CONTAINER_PORT}/healthz').then(async r=>{if(!r.ok) process.exit(1); console.log(await r.text())}).catch(()=>process.exit(1))"
then
  docker logs --tail 40 "$GATEWAY_CONTAINER" 2>&1 || true
  rollback_now
  fail "direct Jason Teams gateway health check failed"
fi

if ! docker port "$GATEWAY_CONTAINER" "${CONTAINER_PORT}/tcp" 2>/dev/null | grep -q ":${HOST_PORT}$"; then
  rollback_now
  fail "direct Jason Teams gateway does not own host port ${HOST_PORT}"
fi

echo "PASS: direct Jason Teams gateway owns host port ${HOST_PORT}"

sudo mkdir -p "$SERVICE_DIR"
{
  printf 'BACKUP_FILE=%q\n' "$BACKUP_FILE"
  printf 'OPENCLAW_COMPOSE_FILE=%q\n' "$OPENCLAW_COMPOSE_FILE"
  printf 'OPENCLAW_PROJECT=%q\n' "$OPENCLAW_PROJECT"
  printf 'OPENCLAW_SERVICE=%q\n' "$OPENCLAW_SERVICE"
  printf 'OPENCLAW_WORKDIR=%q\n' "$OPENCLAW_WORKDIR"
  printf 'GATEWAY_CONTAINER=%q\n' "$GATEWAY_CONTAINER"
  printf 'GATEWAY_SOURCE_SHA=%q\n' "$IMAGE_SOURCE_SHA"
  printf 'BACKUP_SHA256=%q\n' "$BACKUP_SHA256"
  printf 'PROMOTION_PLAN_SHA256=%q\n' "$PROMOTION_PLAN_SHA256"
  printf 'CUTOVER_TIMESTAMP=%q\n' "$TIMESTAMP"
} > "$TMP_DIR/cutover-state.env"
sudo install -m 0640 -o "$RUN_UID" -g "$RUN_GID" "$TMP_DIR/cutover-state.env" "$STATE_FILE"

docker rm -f "$PILOT_CONTAINER" >/dev/null 2>&1 || true

echo
echo "========== FINAL SERVICE STATE =========="
docker ps \
  --filter "name=$GATEWAY_CONTAINER" \
  --filter "name=$RUNTIME_CONTAINER" \
  --filter "name=$OPENCLAW_CONTAINER" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo
echo "CUTOVER_STATUS=PASS"
echo "STATE_FILE=$STATE_FILE"
echo "ROLLBACK_COMMAND=bash infrastructure/jason-teams-gateway/rollback-production.sh"
echo "READY_FOR_TEAMS_LIVE_TEST=1"
