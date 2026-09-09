#!/usr/bin/env bash
set -u

REPO="/home/al/projects/jason"
COMPOSE_DIR="$REPO/infrastructure/jason-runtime"
COMPOSE_FILE="$COMPOSE_DIR/compose.yaml"
SERVICE="jason-runtime"
PROJECT="jason-runtime"

cd "$REPO" || exit 1

echo "========== START JASON RUNTIME DEPLOYMENT =========="

echo "========== SECTION 1: SOURCE STATE =========="
git status --short
git log -1 --oneline --decorate
if ! git diff --check; then
  echo "ERROR: git diff --check failed"
  exit 1
fi

echo "========== SECTION 2: DERIVE LIVE DEPLOYMENT INPUTS =========="
mount_source() {
  docker inspect "$SERVICE" --format '{{range .Mounts}}{{println .Source "|" .Destination}}{{end}}' \
    | awk -F' \| ' -v dest="$1" '$2 == dest {print $1; exit}'
}

live_env() {
  docker inspect "$SERVICE" --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | sed -n "s/^$1=//p" | head -n 1
}

export JASON_OLLAMA_MODEL="$(live_env JASON_OLLAMA_MODEL)"
export JASON_OPENBAO_ROLE_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/role_id)"
export JASON_OPENBAO_SECRET_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/secret_id)"
export JASON_SES_OPENBAO_ROLE_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/aws-ses/role_id)"
export JASON_SES_OPENBAO_SECRET_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/aws-ses/secret_id)"
export JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/microsoft-graph/role_id)"
export JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH="$(mount_source /run/jason-secrets/openbao/microsoft-graph/secret_id)"

export JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH="$(
  mount_source /run/jason-secrets/openbao/openai/role_id
)"
export JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH="$(
  mount_source /run/jason-secrets/openbao/openai/secret_id
)"

if [ -z "$JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH" ]; then
  JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH="/opt/jason/bootstrap/secrets/openbao/openai-semantic-intent-approle/role-id"
fi

if [ -z "$JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH" ]; then
  JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH="/opt/jason/bootstrap/secrets/openbao/openai-semantic-intent-approle/secret-id"
fi

export JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH
export JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH

for name in \
  JASON_OLLAMA_MODEL \
  JASON_OPENBAO_ROLE_ID_HOST_PATH \
  JASON_OPENBAO_SECRET_ID_HOST_PATH \
  JASON_SES_OPENBAO_ROLE_ID_HOST_PATH \
  JASON_SES_OPENBAO_SECRET_ID_HOST_PATH \
  JASON_MICROSOFT_OPENBAO_ROLE_ID_HOST_PATH \
  JASON_MICROSOFT_OPENBAO_SECRET_ID_HOST_PATH \
  JASON_OPENAI_OPENBAO_ROLE_ID_HOST_PATH \
  JASON_OPENAI_OPENBAO_SECRET_ID_HOST_PATH; do
  value="${!name:-}"
  if [ -z "$value" ]; then
    echo "$name = MISSING"
    exit 1
  fi
  echo "$name = SET"
done

echo "========== SECTION 3: COMPOSE VALIDATION =========="
if ! docker compose -p "$PROJECT" --project-directory "$COMPOSE_DIR" -f "$COMPOSE_FILE" config --quiet; then
  echo "ERROR: compose validation failed"
  exit 1
fi

echo "========== SECTION 4: BUILD =========="
if ! docker compose -p "$PROJECT" --project-directory "$COMPOSE_DIR" -f "$COMPOSE_FILE" build "$SERVICE"; then
  echo "ERROR: build failed"
  exit 1
fi

echo "========== SECTION 5: DEPLOY =========="
if ! docker compose -p "$PROJECT" --project-directory "$COMPOSE_DIR" -f "$COMPOSE_FILE" up -d --no-deps "$SERVICE"; then
  echo "ERROR: deploy failed"
  exit 1
fi

echo "========== SECTION 6: HEALTH =========="
health_rc=1
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  echo "Health attempt $attempt"
  if docker exec "$SERVICE" python - <<'PY'
import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    health_rc=0
    echo "Health check: PASS"
    break
  fi
  sleep 2
done

if [ "$health_rc" -ne 0 ]; then
  echo "ERROR: health check failed"
  docker ps --filter "name=$SERVICE" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
  exit 1
fi

echo "========== FINAL STATUS =========="
docker ps --filter "name=$SERVICE" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
echo "PASS: Jason runtime deployment completed successfully."
echo "========== END JASON RUNTIME DEPLOYMENT =========="
