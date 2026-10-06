#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_MCP_PRODUCTION_IMAGE:-jason-mcp:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"
if [ "${JASON_QUICKBOOKS_READ_PROFILE+x}" = "x" ]; then
  QUICKBOOKS_READ_PROFILE="$JASON_QUICKBOOKS_READ_PROFILE"
else
  QUICKBOOKS_READ_PROFILE="$(
    docker inspect jason-mcp-pilot --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
      sed -n 's/^JASON_QUICKBOOKS_READ_PROFILE=//p' |
      tail -n 1
  )"
fi

if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK="jason-mcp-pilot-rollback-$STAMP"
QBO_DEV_ROLE_HOST="${JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/role-id}"
QBO_DEV_SECRET_HOST="${JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/secret-id}"
QBO_PROD_ROLE_HOST="${JASON_QUICKBOOKS_PRODUCTION_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/role-id}"
QBO_PROD_SECRET_HOST="${JASON_QUICKBOOKS_PRODUCTION_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/secret-id}"
QBO_DEV_DB="/var/lib/jason/openclaw/quickbooks/oauth.sqlite3"
QBO_PROD_DB="/var/lib/jason/openclaw/quickbooks-production/oauth.sqlite3"

if [ "$QUICKBOOKS_READ_PROFILE" = "quickbooks-production-read-v1" ]; then
  if [ ! -f "$QBO_PROD_ROLE_HOST" ] || [ ! -f "$QBO_PROD_SECRET_HOST" ]; then
    echo "DENIED: QuickBooks production profile requires the production OpenBao AppRole projection." >&2
    exit 2
  fi
  QBO_ACTIVE_ROLE_CONTAINER="/run/jason-secrets/openbao/quickbooks-production/role_id"
  QBO_ACTIVE_SECRET_CONTAINER="/run/jason-secrets/openbao/quickbooks-production/secret_id"
  QBO_ACTIVE_DB="$QBO_PROD_DB"
else
  QBO_ACTIVE_ROLE_CONTAINER="/run/jason-secrets/openbao/quickbooks-development/role_id"
  QBO_ACTIVE_SECRET_CONTAINER="/run/jason-secrets/openbao/quickbooks-development/secret_id"
  QBO_ACTIVE_DB="$QBO_DEV_DB"
fi

QBO_PROD_ARGS=()
if [ -f "$QBO_PROD_ROLE_HOST" ] && [ -f "$QBO_PROD_SECRET_HOST" ]; then
  QBO_PROD_ARGS=(
    --set-env JASON_QUICKBOOKS_PRODUCTION_OPENBAO_ROLE_ID_PATH=/run/jason-secrets/openbao/quickbooks-production/role_id
    --set-env JASON_QUICKBOOKS_PRODUCTION_OPENBAO_SECRET_ID_PATH=/run/jason-secrets/openbao/quickbooks-production/secret_id
    --set-env JASON_QUICKBOOKS_PRODUCTION_OAUTH_DB="$QBO_PROD_DB"
    --add-readonly-bind "$QBO_PROD_ROLE_HOST:/run/jason-secrets/openbao/quickbooks-production/role_id"
    --add-readonly-bind "$QBO_PROD_SECRET_HOST:/run/jason-secrets/openbao/quickbooks-production/secret_id"
  )
fi

PREFLIGHT=false
for arg in "$@"; do
  if [ "$arg" = "--preflight" ]; then
    PREFLIGHT=true
  fi
done

python3 "$REPO_ROOT/tools/deploy_live_container.py"   --live jason-mcp-pilot   --image "$IMAGE"   --rollback "$ROLLBACK"   --source-revision "$REVISION"   --harden \
  --set-env JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_ROLE_ID_PATH=/run/jason-secrets/openbao/quickbooks-development/role_id \
  --set-env JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_SECRET_ID_PATH=/run/jason-secrets/openbao/quickbooks-development/secret_id \
  --set-env JASON_QUICKBOOKS_DEVELOPMENT_OAUTH_DB="$QBO_DEV_DB" \
  --set-env JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH="$QBO_ACTIVE_ROLE_CONTAINER" \
  --set-env JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH="$QBO_ACTIVE_SECRET_CONTAINER" \
  --set-env JASON_QUICKBOOKS_OAUTH_DB="$QBO_ACTIVE_DB" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --add-readonly-bind "$QBO_DEV_ROLE_HOST:/run/jason-secrets/openbao/quickbooks-development/role_id" \
  --add-readonly-bind "$QBO_DEV_SECRET_HOST:/run/jason-secrets/openbao/quickbooks-development/secret_id" \
  "${QBO_PROD_ARGS[@]}" \
  --promote-image-tag jason-mcp:production \
  --rollback-image-tag jason-mcp:rollback-current \
  --health-url http://127.0.0.1:8000/healthz   "$@"

if [ "$PREFLIGHT" != "true" ]; then
  docker exec -i jason-mcp-pilot python -c 'import jason_mcp.server as s; x=s.jason_mcp_status(); assert x["status"]=="ok"; assert x["governed_execution"]=="central-orchestrator"; assert x["generic_execution_tool"] is True; assert x["direct_provider_access"] is False; print("MCP_GOVERNANCE_POSTCHECK=PASS")'
fi
