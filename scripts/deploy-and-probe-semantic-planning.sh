#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNING DEPLOYMENT AND PROBE =========="

echo "========== SECTION 1: PRECONDITIONS =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
echo "HEAD: $(git rev-parse --short HEAD)"

if [[ "$BRANCH" != "feature/jason-runtime-service" ]]; then
  echo "ERROR: expected feature/jason-runtime-service."
  exit 20
fi

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before deployment."
  printf '%s\n' "$DIRTY"
  exit 21
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required."
  exit 22
fi

if ! docker inspect jason-runtime >/dev/null 2>&1; then
  echo "ERROR: running jason-runtime container is required to derive live deployment inputs."
  exit 23
fi

echo "========== SECTION 2: DERIVE LIVE DEPLOYMENT INPUTS =========="

container_env() {
  local name="$1"
  docker inspect jason-runtime | .venv/bin/python -c '
import json, sys
name = sys.argv[1]
data = json.load(sys.stdin)[0]
for item in data.get("Config", {}).get("Env", []) or []:
    key, sep, value = item.partition("=")
    if sep and key == name:
        print(value)
        break
' "$name"
}

mount_source() {
  local destination="$1"
  docker inspect jason-runtime | .venv/bin/python -c '
import json, sys
destination = sys.argv[1]
data = json.load(sys.stdin)[0]
for mount in data.get("Mounts", []) or []:
    if mount.get("Destination") == destination:
        print(mount.get("Source", ""))
        break
' "$destination"
}

export JASON_OLLAMA_MODEL="$(container_env JASON_OLLAMA_MODEL)"
export JASON_OPENBAO_ROLE_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/role_id)"
export JASON_OPENBAO_SECRET_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/secret_id)"
export JASON_SES_OPENBAO_ROLE_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/aws-ses/role_id)"
export JASON_SES_OPENBAO_SECRET_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/aws-ses/secret_id)"
export JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/microsoft-graph/role_id)"
export JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/microsoft-graph/secret_id)"

required_vars=(
  JASON_OLLAMA_MODEL
  JASON_OPENBAO_ROLE_ID_HOST_PATH
  JASON_OPENBAO_SECRET_ID_HOST_PATH
  JASON_SES_OPENBAO_ROLE_ID_HOST_PATH
  JASON_SES_OPENBAO_SECRET_ID_HOST_PATH
  JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH
  JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH
)

for name in "${required_vars[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: could not derive $name from running jason-runtime."
    exit 24
  fi
  echo "$name = SET"
done

echo "========== SECTION 3: VALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py

COMPOSE_DIR=/home/al/projects/jason/infrastructure/jason-runtime
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"
cd "$COMPOSE_DIR"
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo "========== SECTION 4: BUILD + DEPLOY =========="
docker compose -f "$COMPOSE_FILE" build jason-runtime
docker compose -f "$COMPOSE_FILE" up -d jason-runtime

echo "========== SECTION 5: HEALTH =========="
healthy=0
for attempt in $(seq 1 20); do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' jason-runtime 2>/dev/null || true)"
  echo "Health attempt $attempt: ${status:-unknown}"
  if [[ "$status" == "healthy" ]]; then
    healthy=1
    break
  fi
  sleep 2
done

if [[ "$healthy" -ne 1 ]]; then
  echo "ERROR: Jason runtime did not become healthy within bounded wait."
  docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
  exit 25
fi

echo "========== SECTION 6: LIVE PROBE =========="
cat <<'EOF'
Ask Jason in Teams, one at a time:

1. What is the Windows Display Version for AOT-50282?
2. What processor is on AOT-50282?
3. How much memory does AOT-50282 have?

Expected:
- Display Version must be an OS release value or fail closed; it must NOT return health/version text.
- Processor must remain the processor model.
- Memory may still be raw provider capacity at this stage; human-friendly unit rendering is a separate presentation improvement.
EOF

echo "========== RESULT =========="
echo "Semantic planning repair deployed and healthy."
echo "========== END SEMANTIC PLANNING DEPLOYMENT AND PROBE =========="
