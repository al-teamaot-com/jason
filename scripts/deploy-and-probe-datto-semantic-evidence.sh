#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EVIDENCE DEPLOYMENT AND PROBE =========="

echo "========== SECTION 1: PRECONDITIONS =========="
BRANCH="$(git branch --show-current)"
HEAD="$(git rev-parse --short HEAD)"
echo "Branch: $BRANCH"
echo "HEAD: $HEAD"

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
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' jason-runtime \
    | awk -F= -v key="$name" '$1 == key {sub(/^[^=]*=/, ""); print; exit}'
}

mount_source() {
  local destination="$1"
  docker inspect --format '{{range .Mounts}}{{println .Destination "|" .Source}}{{end}}' jason-runtime \
    | awk -F'|' -v dest="$destination" '$1 == dest {print $2; exit}'
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
    echo "ERROR: could not derive $name from the running production container."
    exit 24
  fi
  echo "$name = SET"
done

echo "========== SECTION 3: STATIC + COMPOSE VALIDATION =========="
git diff --check

COMPOSE_DIR=/home/al/projects/jason/infrastructure/jason-runtime
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: authoritative compose file missing: $COMPOSE_FILE"
  exit 25
fi

cd "$COMPOSE_DIR"
docker compose -f "$COMPOSE_FILE" config >/dev/null

echo "========== SECTION 4: BUILD =========="
docker compose -f "$COMPOSE_FILE" build jason-runtime

echo "========== SECTION 5: DEPLOY =========="
docker compose -f "$COMPOSE_FILE" up -d jason-runtime

echo "========== SECTION 6: HEALTH =========="
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
  echo "ERROR: Jason runtime did not become healthy within the bounded wait."
  docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
  exit 26
fi

echo "========== SECTION 7: DEPLOYMENT STATUS =========="
docker ps --filter name=jason-runtime --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'

echo "========== SECTION 8: LIVE PROBE INSTRUCTIONS =========="
cat <<'EOF'
Run these five questions through the normal Jason Teams interface, one at a time:

1. What is the Windows Display Version for AOT-50282?
2. What processor is on AOT-50282?
3. What CPU does AOT-50282 have?
4. How much RAM is in AOT-50282?
5. How much memory does AOT-50282 have?

Expected semantic behavior:
- Windows Display Version must come only from operating-system/windows-release evidence.
- Processor/CPU must resolve to processor model, not logical processor count.
- RAM/memory must resolve to total memory.
- If Datto does not expose a uniquely mapped provider value, Jason should fail closed rather than return an unrelated field.
EOF

echo "========== RESULT =========="
echo "Deployment completed and health passed. Live semantic evidence questions are ready for Teams validation."
echo "NO SOURCE CHANGES PERFORMED."
echo "========== END DATTO SEMANTIC EVIDENCE DEPLOYMENT AND PROBE =========="
