#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE="${JASON_RUNTIME_PRODUCTION_IMAGE:-jason-runtime:production}"
REVISION="${JASON_SOURCE_REVISION_OVERRIDE:-}"
COMPLETION_TEAMS_PROFILE="${JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE:-person-al-v1}"
if [ "${JASON_PM_V2_CONTROL_PROFILE+x}" = "x" ]; then
  PM_V2_CONTROL_PROFILE="$JASON_PM_V2_CONTROL_PROFILE"
else
  PM_V2_CONTROL_PROFILE="$(
    docker inspect jason-runtime --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
      sed -n 's/^JASON_PM_V2_CONTROL_PROFILE=//p' |
      tail -n 1
  )"
fi
PM_V2_SHARED_ROOT="${JASON_PM_V2_SHARED_ROOT:-/var/lib/jason/openclaw/pm-v2}"
if [ "${JASON_QUICKBOOKS_READ_PROFILE+x}" = "x" ]; then
  QUICKBOOKS_READ_PROFILE="$JASON_QUICKBOOKS_READ_PROFILE"
else
  QUICKBOOKS_READ_PROFILE="$(
    docker inspect jason-runtime --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
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
  jason-runtime:rollback-current)
    # Original v10 code/image may have no source declaration of its own.
    # On exact native rollback use the current candidate's reviewed LKG pair.
    AUTOTASK_READ_PROFILE="$DECLARED_ROLLBACK_PROFILE"
    ;;
  *)
    # During runtime->MCP transition only verify this service's previous
    # profile; the other service may legitimately be on the new revision.
    LIVE_READ_PROFILE="$(docker inspect jason-runtime --format '{{range .Config.Env}}{{println .}}{{end}}' |
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
  --set-env "JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE=$COMPLETION_TEAMS_PROFILE"   --set-env "JASON_PM_V2_CONTROL_PROFILE=$PM_V2_CONTROL_PROFILE"   --set-env "JASON_PM_V2_SHARED_ROOT=$PM_V2_SHARED_ROOT" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH=$QBO_MOUNT_BASE/role_id" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH=$QBO_MOUNT_BASE/secret_id" \
  --set-env "JASON_QUICKBOOKS_OAUTH_DB=$QBO_DB" \
  --set-env "JASON_PROVIDER_READ_ACTIVATION_PROFILE=$AUTOTASK_READ_PROFILE" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --set-env "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=${JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID:-}" \
  --add-readonly-bind "$QBO_ROLE_HOST:$QBO_MOUNT_BASE/role_id" \
  --add-readonly-bind "$QBO_SECRET_HOST:$QBO_MOUNT_BASE/secret_id" \
  --promote-image-tag jason-runtime:production \
  --promote-image-tag jason-runtime:local \
  --rollback-image-tag jason-runtime:rollback-current \
  --health-url http://127.0.0.1:8080/healthz   "$@"
