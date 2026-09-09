#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EQUIVALENT VALUE DEPLOYMENT AND PROBE =========="
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
INSPECT_JSON="$(mktemp)"
trap 'rm -f "$INSPECT_JSON"' EXIT
docker inspect jason-runtime > "$INSPECT_JSON"

container_env() {
  local name="$1"
  .venv/bin/python - "$INSPECT_JSON" "$name" <<'PY'
import json, sys
path, name = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as handle:
    data = json.load(handle)[0]
for item in data.get('Config', {}).get('Env', []) or []:
    key, sep, value = item.partition('=')
    if sep and key == name:
        print(value)
        break
PY
}

mount_source() {
  local destination="$1"
  .venv/bin/python - "$INSPECT_JSON" "$destination" <<'PY'
import json, sys
path, destination = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as handle:
    data = json.load(handle)[0]
for mount in data.get('Mounts', []) or []:
    if mount.get('Destination') == destination:
        print(mount.get('Source', ''))
        break
PY
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
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py

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

1. What processor is on AOT-50282?
2. What is the Windows Display Version for AOT-50282?

Expected:
- Processor should resolve to the processor model when repeated Datto aliases carry the same value.
- Conflicting provider values must still fail closed.
- Windows Display Version must be an actual Windows release value or fail closed; never unrelated health/version text.
EOF

echo "========== RESULT =========="
echo "Datto semantic equivalent-value repair deployed and healthy."
echo "========== END DATTO SEMANTIC EQUIVALENT VALUE DEPLOYMENT AND PROBE =========="
