#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_RUNTIME_PRODUCTION_IMAGE:-jason-runtime:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"
COMPLETION_TEAMS_PROFILE="${JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE:-person-al-v1}"
if [ "${JASON_QUICKBOOKS_READ_PROFILE+x}" = "x" ]; then
  QUICKBOOKS_READ_PROFILE="$JASON_QUICKBOOKS_READ_PROFILE"
else
  QUICKBOOKS_READ_PROFILE="$(
    docker inspect jason-runtime --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
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
ROLLBACK="jason-runtime-rollback-$STAMP"

if [ "$QUICKBOOKS_READ_PROFILE" = "quickbooks-production-read-v1" ]; then
  QBO_ROLE_HOST="${JASON_QUICKBOOKS_PRODUCTION_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/role-id}"
  QBO_SECRET_HOST="${JASON_QUICKBOOKS_PRODUCTION_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-production-oauth-client-approle/secret-id}"
  QBO_DB="/var/lib/jason/openclaw/quickbooks-production/oauth.sqlite3"
  QBO_MOUNT_BASE="/run/jason-secrets/openbao/quickbooks-production"
  if [ ! -f "$QBO_ROLE_HOST" ] || [ ! -f "$QBO_SECRET_HOST" ]; then
    echo "DENIED: QuickBooks production profile requires the production OpenBao AppRole projection." >&2
    exit 2
  fi
else
  QBO_ROLE_HOST="${JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_ROLE_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/role-id}"
  QBO_SECRET_HOST="${JASON_QUICKBOOKS_DEVELOPMENT_OPENBAO_SECRET_ID_HOST_PATH:-/var/lib/jason/runtime-secrets/openbao/quickbooks-development-oauth-client-approle/secret-id}"
  QBO_DB="/var/lib/jason/openclaw/quickbooks/oauth.sqlite3"
  QBO_MOUNT_BASE="/run/jason-secrets/openbao/quickbooks"
fi

# Resolve only an immutable, source-committed, expiring NONEXECUTING test
# campaign. The existing Release Manager invokes this canonical script only
# after exact-SHA owner authority, preproduction, CCC and rollback gates.
# Preflight always forces the test OFF; it cannot issue a Teams card.
UAT_PREFLIGHT=()
for argument in "$@"; do
  if [ "$argument" = "--preflight" ]; then
    UAT_PREFLIGHT=(--preflight)
  fi
done
# The previously verified LKG predates the UAT manifest. The existing
# production Release Manager rolls back through this candidate script with
# IMAGE=rollback-current and REVISION=the LKG hash. The rollback image itself
# must attest to exactly that revision; never import candidate UAT flags into
# an old runtime and never require a manifest absent from that old source.
if [ "$IMAGE" = "jason-runtime:rollback-current" ]; then
  IMAGE_REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
  if [[ ! "$REVISION" =~ ^[0-9a-f]{40}$ ]] || [ "$IMAGE_REVISION" != "$REVISION" ]; then
    echo "DENIED: rollback image/source revision mismatch" >&2
    exit 2
  fi
  UAT_RESULT="off|false|none"
else
  # Ordinary production activation stays byte-for-byte tied to its approved Git
  # commit and the strict test-only campaign parser.
  UAT_RESULT="$(python3 "$REPO_ROOT/tools/owner_uat_activation.py" \
    --manifest "$REPO_ROOT/config/owner-uat-campaign.json" \
    --source-revision "$REVISION" "${UAT_PREFLIGHT[@]}")"
fi
IFS='|' read -r OWNER_UAT_MODE OWNER_UAT_WORKER OWNER_UAT_SESSION <<< "$UAT_RESULT"
if [ "$OWNER_UAT_SESSION" = "none" ]; then
  OWNER_UAT_SESSION=""
fi
case "$OWNER_UAT_MODE:$OWNER_UAT_WORKER" in
  off:false|nonexecuting_test_only:true) ;;
  *) echo "DENIED: UAT manifest activation returned unsupported mode" >&2; exit 2 ;;
esac

exec python3 "$REPO_ROOT/tools/deploy_live_container.py"   --live jason-runtime   --image "$IMAGE"   --rollback "$ROLLBACK"   --source-revision "$REVISION"   --harden \
  --set-env "JASON_OWNER_UAT_MODE=$OWNER_UAT_MODE" \
  --set-env "JASON_OWNER_UAT_WORKER_ENABLED=$OWNER_UAT_WORKER" \
  --set-env "JASON_OWNER_UAT_SESSION_ID=$OWNER_UAT_SESSION" \
  --set-env "JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE=$COMPLETION_TEAMS_PROFILE" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH=$QBO_MOUNT_BASE/role_id" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH=$QBO_MOUNT_BASE/secret_id" \
  --set-env "JASON_QUICKBOOKS_OAUTH_DB=$QBO_DB" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --set-env "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=${JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID:-}" \
  --add-readonly-bind "$QBO_ROLE_HOST:$QBO_MOUNT_BASE/role_id" \
  --add-readonly-bind "$QBO_SECRET_HOST:$QBO_MOUNT_BASE/secret_id" \
  --promote-image-tag jason-runtime:production \
  --promote-image-tag jason-runtime:local \
  --rollback-image-tag jason-runtime:rollback-current \
  --health-url http://127.0.0.1:8080/healthz   "$@"
