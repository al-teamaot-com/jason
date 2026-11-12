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

# Source-bound staff note authority: source-only activation, no host fallback.
SOURCE_STAFF_NOTE_PROFILE="$(python3 - "$REPO_ROOT/config/aot-staff-internal-note-profile.json" <<'PY_STAFF'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
if p.is_symlink():
    raise SystemExit("DENIED: staff-note profile is a symlink")
if not p.exists():
    print("")  # Historical releases are default-off.
    raise SystemExit(0)
try:
    d=json.loads(p.read_text(encoding="utf-8"))
except (OSError,ValueError):
    raise SystemExit("DENIED: invalid staff-note profile declaration")
if (not isinstance(d,dict) or set(d)!={"schema_version","profile"}
        or d.get("schema_version")!="1.0"
        or d.get("profile") not in ("off","internal-note-v1")):
    raise SystemExit("DENIED: unreviewed staff-note profile declaration")
print("" if d["profile"]=="off" else "internal-note-v1")
PY_STAFF
)" || exit 2
if [ "$IMAGE" = "jason-mcp:rollback-current" ]; then
  # A rollback must not grant rights absent from the prior release.
  STAFF_NOTE_PROFILE=""
else
  STAFF_NOTE_PROFILE="$SOURCE_STAFF_NOTE_PROFILE"
  if [ "${JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE:-}" != "$STAFF_NOTE_PROFILE" ]; then
    echo "DENIED: staff-note activation differs from immutable source" >&2
    exit 2
  fi
fi


# Shared source-controlled activation for qualified, authenticated AOT human
# technicians using approved client-notification templates only. This is a new
# organization grant requiring its own release review; never enable by an SSH
# environment override or carry it through an older-image rollback.
SOURCE_CLIENT_NOTIFICATION_TECH_PROFILE="$(python3 - "$REPO_ROOT/config/aot-client-notification-technician-profile.json" <<'PY_NOTIFICATION_TECH'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
if path.is_symlink():
    raise SystemExit("DENIED: notification technician policy symlink")
if not path.exists():
    print("")  # Historical source has no client-notification technician grant.
    raise SystemExit(0)
try:
    doc = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit("DENIED: unreadable notification technician policy")
if (not isinstance(doc, dict)
        or set(doc) != {"schema_version", "profile"}
        or doc.get("schema_version") != "1.0"
        or doc.get("profile") not in ("off", "approved-workflow-technician-v1")):
    raise SystemExit("DENIED: unreviewed notification technician policy")
print("" if doc["profile"] == "off" else doc["profile"])
PY_NOTIFICATION_TECH
)" || exit 2
if [ "$IMAGE" = "jason-mcp:rollback-current" ]; then
  CLIENT_NOTIFICATION_TECH_PROFILE=""
else
  CLIENT_NOTIFICATION_TECH_PROFILE="$SOURCE_CLIENT_NOTIFICATION_TECH_PROFILE"
  if [ "${JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE:-}" != "$CLIENT_NOTIFICATION_TECH_PROFILE" ]; then
    echo "DENIED: client-notification technician authority differs from immutable source" >&2
    exit 2
  fi
fi

if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "com.teamaot.jason.source_revision"}}' 2>/dev/null || true)"
fi
if [ -z "$REVISION" ]; then
  REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
fi

# The privileged-grant administrator is separately authenticated. This
# activation is bound to the reviewed source V4 release policy and is OFF for
# legacy candidates. An SSH/environment override cannot enable it.
SOURCE_ADMIN_APPROVER_PROFILE="$(python3 - "$REPO_ROOT" <<'PY_ADMIN_ROLE'
import sys
from pathlib import Path
repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
from release_manager_host_runner import _validated_mobile_release_policy
policy = _validated_mobile_release_policy(
    repo / "config" / "mobile-release-approval-policy.json",
    source_v2_required=True,
)
print("admin-separated-v1" if policy["mode"] == "admin_approver_separated" else "")
PY_ADMIN_ROLE
)" || exit 2
if [ "$IMAGE" = "jason-mcp:rollback-current" ]; then
  ADMIN_APPROVER_PROFILE=""
else
  ADMIN_APPROVER_PROFILE="$SOURCE_ADMIN_APPROVER_PROFILE"
  if [ "${JASON_AOT_ADMIN_APPROVER_PROFILE:-}" != "$ADMIN_APPROVER_PROFILE" ]; then
    echo "DENIED: admin approval profile differs from reviewed exact source" >&2
    exit 2
  fi
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

# The independently approved Owner signing secret is provisioned OUTSIDE
# Git and Docker builds. A missing or unsafe signer denies activation.
OWNER_SIGNER_HOST="/var/lib/jason/runtime-secrets/owner-release/private_key"
OWNER_SIGNER_CONTAINER="/run/jason-secrets/owner-release/private_key"
OWNER_SIGNER_ARGS=()
if [ "$IMAGE" = "jason-mcp:rollback-current" ]; then
  # A V2 rollback must not retain the new signing secret or live auth path.
  OWNER_SIGNER_ARGS=(
    --set-env "JASON_OWNER_RELEASE_ED25519_KEY_PATH="
    --omit-owner-release-signer-bind-on-rollback
  )
else
  if [ -L "$OWNER_SIGNER_HOST" ] || [ ! -f "$OWNER_SIGNER_HOST" ]; then
    echo "DENIED: Owner release signing key has not been provisioned" >&2
    exit 2
  fi
  OWNER_SIGNER_OWNER_MODE="$(stat -c '%u:%g:%a' "$OWNER_SIGNER_HOST")"
  if [ "$OWNER_SIGNER_OWNER_MODE" != "1000:1000:400" ] ||
     [ "$(stat -c '%s' "$OWNER_SIGNER_HOST")" != "32" ]; then
    echo "DENIED: Owner signing key mode, UID or exact Ed25519 length invalid" >&2
    exit 2
  fi
  # Source-key must match the separately root-owned policy's pinned
  # public key. This is a non-mutating proof before Docker replacement,
  # including during --preflight. Never print private bytes.
  OWNER_SIGNER_PUBLIC_POLICY="/etc/jason-owner-release/verified-owner-public-key.json"
  PYTHONPATH="$REPO_ROOT/implementation" python3 - "$OWNER_SIGNER_HOST" "$OWNER_SIGNER_PUBLIC_POLICY" <<'PY_OWNER_SIGNER'
import sys
from pathlib import Path
from kernel.signed_owner_release import (
    read_pinned_root_owner_public_key, read_service_owner_signing_key,
    public_key_sha256,
)
private = read_service_owner_signing_key(Path(sys.argv[1]))
trusted = read_pinned_root_owner_public_key(Path(sys.argv[2]))
if public_key_sha256(private.public_key()) != public_key_sha256(trusted):
    raise SystemExit("DENIED: Owner signer differs from root-approved public key")
print("MCP_OWNER_SIGNER_ROOT_TRUST_PRECHECK=PASS")
PY_OWNER_SIGNER
  OWNER_SIGNER_ARGS=(
    --set-env "JASON_OWNER_RELEASE_ED25519_KEY_PATH=$OWNER_SIGNER_CONTAINER"
    --add-readonly-bind "$OWNER_SIGNER_HOST:$OWNER_SIGNER_CONTAINER"
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
  --set-env "JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE=$STAFF_NOTE_PROFILE" \
  --set-env "JASON_AOT_CLIENT_NOTIFICATION_TECH_PROFILE=$CLIENT_NOTIFICATION_TECH_PROFILE" \
  --set-env "JASON_AOT_ADMIN_APPROVER_PROFILE=$ADMIN_APPROVER_PROFILE" \
  --set-env "JASON_PROVIDER_READ_ACTIVATION_PROFILE=$AUTOTASK_READ_PROFILE" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --set-env "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=${JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID:-}" \
  --add-readonly-bind "$QBO_DEV_ROLE_HOST:/run/jason-secrets/openbao/quickbooks-development/role_id" \
  --add-readonly-bind "$QBO_DEV_SECRET_HOST:/run/jason-secrets/openbao/quickbooks-development/secret_id" \
  "${QBO_PROD_ARGS[@]}" \
  "${OWNER_SIGNER_ARGS[@]}" \
  --promote-image-tag jason-mcp:production \
  --rollback-image-tag jason-mcp:rollback-current \
  --health-url http://127.0.0.1:8000/healthz   "$@"

if [ "$PREFLIGHT" != "true" ]; then
  docker exec -i jason-mcp-pilot python -c 'import jason_mcp.server as s; x=s.jason_mcp_status(); assert x["status"]=="ok"; assert x["governed_execution"]=="central-orchestrator"; assert x["generic_execution_tool"] is True; assert x["direct_provider_access"] is False; print("MCP_GOVERNANCE_POSTCHECK=PASS")'
  if [ "$IMAGE" != "jason-mcp:rollback-current" ]; then
    # Verify the 0400 mount in the unprivileged MCP process without logging bytes.
    docker exec -i jason-mcp-pilot python -c 'import os,stat;from pathlib import Path;from kernel.signed_owner_release import read_service_owner_signing_key;p=Path(os.environ["JASON_OWNER_RELEASE_ED25519_KEY_PATH"]);s=p.lstat();assert not p.is_symlink() and stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o400 and s.st_uid==os.geteuid()==1000;read_service_owner_signing_key(p);print("MCP_OWNER_RELEASE_SIGNER_MOUNT=PASS")'
  fi
fi
