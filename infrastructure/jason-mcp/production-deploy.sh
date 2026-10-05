#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_MCP_PRODUCTION_IMAGE:-jason-mcp:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"
QUICKBOOKS_READ_PROFILE="${JASON_QUICKBOOKS_READ_PROFILE:-}"

if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK="jason-mcp-pilot-rollback-$STAMP"
PREFLIGHT=false
for arg in "$@"; do
  if [ "$arg" = "--preflight" ]; then
    PREFLIGHT=true
  fi
done

python3 "$REPO_ROOT/tools/deploy_live_container.py"   --live jason-mcp-pilot   --image "$IMAGE"   --rollback "$ROLLBACK"   --source-revision "$REVISION"   --harden \
  --set-env JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH=/run/jason-secrets/openbao/quickbooks/role_id \
  --set-env JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH=/run/jason-secrets/openbao/quickbooks/secret_id \
  --set-env JASON_QUICKBOOKS_OAUTH_DB=/var/lib/jason/openclaw/quickbooks/oauth.sqlite3 \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --add-readonly-bind "${JASON_QUICKBOOKS_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/role-id}:/run/jason-secrets/openbao/quickbooks/role_id" \
  --add-readonly-bind "${JASON_QUICKBOOKS_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/secret-id}:/run/jason-secrets/openbao/quickbooks/secret_id" \
  --promote-image-tag jason-mcp:production \
  --rollback-image-tag jason-mcp:rollback-current \
  --health-url http://127.0.0.1:8000/healthz   "$@"

if [ "$PREFLIGHT" != "true" ]; then
  docker exec -i jason-mcp-pilot python -c 'import jason_mcp.server as s; x=s.jason_mcp_status(); assert x["status"]=="ok"; assert x["governed_execution"]=="central-orchestrator"; assert x["generic_execution_tool"] is True; assert x["direct_provider_access"] is False; print("MCP_GOVERNANCE_POSTCHECK=PASS")'
fi
