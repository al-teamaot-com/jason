#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_RUNTIME_PRODUCTION_IMAGE:-jason-runtime:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"
COMPLETION_TEAMS_PROFILE="${JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE:-person-al-v1}"
QUICKBOOKS_READ_PROFILE="${JASON_QUICKBOOKS_READ_PROFILE:-}"

if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK="jason-runtime-rollback-$STAMP"

if [ "$QUICKBOOKS_READ_PROFILE" = "quickbooks-production-read-v1" ]; then
  QBO_ROLE_HOST="${JASON_QUICKBOOKS_PRODUCTION_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/role-id}"
  QBO_SECRET_HOST="${JASON_QUICKBOOKS_PRODUCTION_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/secret-id}"
  QBO_DB="/var/lib/jason/openclaw/quickbooks-production/oauth.sqlite3"
  if [ ! -f "$QBO_ROLE_HOST" ] || [ ! -f "$QBO_SECRET_HOST" ]; then
    echo "DENIED: QuickBooks production profile requires the production OpenBao AppRole projection." >&2
    exit 2
  fi
else
  QBO_ROLE_HOST="${JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/role-id}"
  QBO_SECRET_HOST="${JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/secret-id}"
  QBO_DB="/var/lib/jason/openclaw/quickbooks/oauth.sqlite3"
fi

exec python3 "$REPO_ROOT/tools/deploy_live_container.py"   --live jason-runtime   --image "$IMAGE"   --rollback "$ROLLBACK"   --source-revision "$REVISION"   --harden \
  --set-env "JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE=$COMPLETION_TEAMS_PROFILE" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH=/run/jason-secrets/openbao/quickbooks/role_id" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH=/run/jason-secrets/openbao/quickbooks/secret_id" \
  --set-env "JASON_QUICKBOOKS_OAUTH_DB=$QBO_DB" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --add-readonly-bind "$QBO_ROLE_HOST:/run/jason-secrets/openbao/quickbooks/role_id" \
  --add-readonly-bind "$QBO_SECRET_HOST:/run/jason-secrets/openbao/quickbooks/secret_id" \
  --promote-image-tag jason-runtime:production \
  --promote-image-tag jason-runtime:local \
  --rollback-image-tag jason-runtime:rollback-current \
  --health-url http://127.0.0.1:8080/healthz   "$@"
