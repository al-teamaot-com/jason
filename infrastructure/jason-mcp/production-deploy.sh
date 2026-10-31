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

# Source-declared v13 and last-known-good v10 are both exact-SHA reviewed.
# PM v10's non-mutating preflight does not inject profile variables; enforce
# immutable source and verify the current container's known-good profile
# independently instead of weakening the actual release activation contract.
PROFILE_PAIR="$(
  python3 - "$REPO_ROOT/config/autotask-entity-read-profile.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if p.is_symlink() or not p.is_file():
    raise SystemExit("DENIED: immutable Autotask read/rollback profile absent")
o = json.loads(p.read_text(encoding="utf-8"))
allowed = {"itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10",
           "itglue-autotask-entra-comprehensive-entity-read-catalog-v11",
           "itglue-autotask-entra-dynamic-schema-read-catalog-v13"}
if (not isinstance(o, dict)
        or set(o) != {"schema_version", "read_profile", "rollback_read_profile"}
        or o.get("schema_version") != "1.0"
        or o.get("read_profile") not in allowed
        or o.get("rollback_read_profile") not in allowed):
    raise SystemExit("DENIED: unapproved Autotask candidate/rollback profile pair")
print(o["read_profile"] + "|" + o["rollback_read_profile"])
PY
)" || exit 2
IFS='|' read -r SOURCE_READ_PROFILE DECLARED_ROLLBACK_PROFILE <<< "$PROFILE_PAIR"
# Optional PM overrides never supersede the exact source contract.
if [ -n "${JASON_PROVIDER_READ_ACTIVATION_PROFILE:-}" ] &&
   [ "$JASON_PROVIDER_READ_ACTIVATION_PROFILE" != "$SOURCE_READ_PROFILE" ]; then
  echo "DENIED: invoking candidate provider-read profile differs from reviewed source" >&2
  exit 2
fi
if [ -n "${JASON_PROVIDER_READ_ROLLBACK_PROFILE:-}" ] &&
   [ "$JASON_PROVIDER_READ_ROLLBACK_PROFILE" != "$DECLARED_ROLLBACK_PROFILE" ]; then
  echo "DENIED: invoking rollback provider-read profile differs from reviewed source" >&2
  exit 2
fi
case "$IMAGE" in
  jason-mcp:rollback-current)
    # Original v10 code/image may have no source declaration of its own.
    # On exact native rollback use the current candidate's reviewed LKG pair.
    AUTOTASK_READ_PROFILE="$DECLARED_ROLLBACK_PROFILE"
    ;;
  *)
    # During runtime->MCP transition only verify this service's previous
    # profile; the other service may legitimately be on the new revision.
    LIVE_READ_PROFILE="$(docker inspect jason-mcp-pilot --format '{{range .Config.Env}}{{println .}}{{end}}' |
      sed -n 's/^JASON_PROVIDER_READ_ACTIVATION_PROFILE=//p')"
    # Permit an existing exact source-bound profile to be upgraded in place,
    # while preserving the separately declared known-good rollback profile.
    # Unknown or unrelated profiles remain denied before any deployment.
    if [ "$LIVE_READ_PROFILE" != "$DECLARED_ROLLBACK_PROFILE" ] &&
       [ "$LIVE_READ_PROFILE" != "$SOURCE_READ_PROFILE" ]; then
      echo "DENIED: current service profile is neither approved source nor LKG" >&2
      exit 2
    fi
    AUTOTASK_READ_PROFILE="$SOURCE_READ_PROFILE"
    ;;
esac

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

# Explicit human-only routine Autotask profile; no provider-wide RW policy.
case "${JASON_AOT_ROUTINE_RW_PROFILE:-}" in
  ""|autotask-ticket-v1) ;;
  *) echo "DENIED: unknown AOT routine Autotask ticket profile" >&2; exit 2 ;;
esac
AOT_ROUTINE_RW_PROFILE="${JASON_AOT_ROUTINE_RW_PROFILE:-}"
# Enforce the original OFF authority state during last-known-good rollback.
if [ "$IMAGE" = "jason-mcp:rollback-current" ]; then
  AOT_ROUTINE_RW_PROFILE=""
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
  --set-env "JASON_PROVIDER_READ_ACTIVATION_PROFILE=$AUTOTASK_READ_PROFILE" \
  --set-env "JASON_AOT_ROUTINE_RW_PROFILE=$AOT_ROUTINE_RW_PROFILE" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --set-env "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=${JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID:-}" \
  --add-readonly-bind "$QBO_DEV_ROLE_HOST:/run/jason-secrets/openbao/quickbooks-development/role_id" \
  --add-readonly-bind "$QBO_DEV_SECRET_HOST:/run/jason-secrets/openbao/quickbooks-development/secret_id" \
  "${QBO_PROD_ARGS[@]}" \
  --promote-image-tag jason-mcp:production \
  --rollback-image-tag jason-mcp:rollback-current \
  --health-url http://127.0.0.1:8000/healthz   "$@"

if [ "$PREFLIGHT" != "true" ]; then
  docker exec -i jason-mcp-pilot python -c 'import jason_mcp.server as s; x=s.jason_mcp_status(); assert x["status"]=="ok"; assert x["governed_execution"]=="central-orchestrator"; assert x["generic_execution_tool"] is True; assert x["direct_provider_access"] is False; print("MCP_GOVERNANCE_POSTCHECK=PASS")'
fi
