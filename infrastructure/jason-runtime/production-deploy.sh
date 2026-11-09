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
if [ "$IMAGE" = "jason-runtime:rollback-current" ]; then
  # A rollback must not grant rights absent from the prior release.
  STAFF_NOTE_PROFILE=""
else
  STAFF_NOTE_PROFILE="$SOURCE_STAFF_NOTE_PROFILE"
  if [ "${JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE:-}" != "$STAFF_NOTE_PROFILE" ]; then
    echo "DENIED: staff-note activation differs from immutable source" >&2
    exit 2
  fi
fi

# Source-bound universal/open-world query activation. The candidate source is
# authoritative; there is no host-only enable override. Rollback always disables
# the capability because the prior production revision did not carry this profile.
SOURCE_UNIVERSAL_QUERY_PROFILE="$(python3 - "$REPO_ROOT/config/universal-query-activation.json" <<'PY_UNIVERSAL'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
if p.is_symlink() or not p.is_file():
    raise SystemExit("DENIED: immutable universal-query activation profile absent")
try:
    d=json.loads(p.read_text(encoding="utf-8"))
except (OSError,ValueError):
    raise SystemExit("DENIED: invalid universal-query activation profile")
if (not isinstance(d,dict) or set(d)!={"schema_version","profile"}
        or d.get("schema_version")!="1.0"
        or d.get("profile") not in ("off","aot-internal-read-v1")):
    raise SystemExit("DENIED: unreviewed universal-query activation profile declaration")
print(d["profile"])
PY_UNIVERSAL
)" || exit 2
if [ "$IMAGE" = "jason-runtime:rollback-current" ]; then
  UNIVERSAL_QUERY_ENABLED="false"
else
  case "$SOURCE_UNIVERSAL_QUERY_PROFILE" in
    off) UNIVERSAL_QUERY_ENABLED="false" ;;
    aot-internal-read-v1) UNIVERSAL_QUERY_ENABLED="true" ;;
    *) echo "DENIED: unsupported universal-query activation profile" >&2; exit 2 ;;
  esac
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

# Owner-reviewed release approval is source-bound. Preproduction can validate
# the exact candidate declaration but always runs the approval lane OFF.
SOURCE_RELEASE_APPROVAL_MODE="$(python3 - "$REPO_ROOT/config/mobile-release-approval-policy.json" <<'PY2'
import json, re, sys, uuid
from pathlib import Path
p=Path(sys.argv[1])
if p.is_symlink() or not p.is_file():
    raise SystemExit("DENIED: immutable mobile release approval policy absent")
d=json.loads(p.read_text(encoding="utf-8"))
version=d.get("schema_version")
if version == "2.0":
    mode = "owner_reviewed"
    risks = {"normal", "production_control_core"}
    expected = {"schema_version", "organization_id", "policy_mode",
                "owner_identity_ids", "allowed_risk_profiles", "ttl_seconds",
                "capability", "high_impact_review"}
elif version == "3.0":
    mode = "owner_reviewed"
    risks = {"normal", "production_control_core", "production_repair"}
    expected = {"schema_version", "organization_id", "policy_mode",
                "owner_identity_ids", "allowed_risk_profiles", "ttl_seconds",
                "capability", "high_impact_review"}
elif version == "4.0":
    mode = "admin_approver_separated"
    risks = {"normal", "production_control_core"}
    expected = {"schema_version", "organization_id", "policy_mode",
                "owner_identity_ids", "allowed_risk_profiles", "ttl_seconds",
                "capability", "high_impact_review", "admin_approver_binding",
                "regular_requester_binding"}
else:
    raise SystemExit("DENIED: source mobile release approval policy version unreviewed")
actual_risks=d.get("allowed_risk_profiles")
ttl=d.get("ttl_seconds")
if (set(d) != expected or d.get("organization_id") != "aot"
        or d.get("policy_mode") != mode
        or d.get("owner_identity_ids") != ["person-al"]
        or type(actual_risks) is not list
        or set(actual_risks) != risks or len(actual_risks) != len(risks)
        or type(ttl) is not int or not 300 <= ttl <= 900
        or d.get("capability") != "release.production.approve"
        or d.get("high_impact_review") != {
            "owner_exact_sha_required": True,
            "signed_teams_identity_required": True,
            "independent_ccc_required": True,
            "protected_release_gates_unchanged": True,
        }):
    raise SystemExit("DENIED: source mobile release approval policy is invalid")
if version == "4.0":
    def exact_binding(field):
        binding=d.get(field)
        if not isinstance(binding, dict) or set(binding) != {
            "microsoft_tenant_id", "microsoft_object_id"
        }:
            raise SystemExit("DENIED: missing exact separated Entra binding")
        tenant=binding["microsoft_tenant_id"]
        oid=binding["microsoft_object_id"]
        for value in (tenant, oid):
            if (not isinstance(value, str)
                    or re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", value) is None
                    or str(uuid.UUID(value)) != value):
                raise SystemExit("DENIED: separated Entra binding is invalid")
        return tenant,oid
    admin=exact_binding("admin_approver_binding")
    regular=exact_binding("regular_requester_binding")
    if admin[0] != regular[0] or admin[1] == regular[1]:
        raise SystemExit("DENIED: approver cannot be normal requester")
print(mode)
PY2
)" || exit 2
if [ ${#UAT_PREFLIGHT[@]} -gt 0 ]; then
  RELEASE_APPROVAL_MODE="off"
elif [ "$IMAGE" = "jason-runtime:rollback-current" ]; then
  RELEASE_APPROVAL_MODE="${JASON_RELEASE_MOBILE_APPROVAL_ROLLBACK_MODE:-off}"
  case "$RELEASE_APPROVAL_MODE" in owner_only_pilot|owner_reviewed|admin_approver_separated|off) ;; *) echo "DENIED: invalid rollback release approval mode" >&2; exit 2;; esac
else
  if [ "${JASON_RELEASE_MOBILE_APPROVAL_MODE:-}" != "$SOURCE_RELEASE_APPROVAL_MODE" ]; then
    echo "DENIED: invoking release approval mode differs from reviewed source" >&2
    exit 2
  fi
  RELEASE_APPROVAL_MODE="$SOURCE_RELEASE_APPROVAL_MODE"
fi

exec python3 "$REPO_ROOT/tools/deploy_live_container.py"   --live jason-runtime   --image "$IMAGE"   --rollback "$ROLLBACK"   --source-revision "$REVISION"   --harden \
  --set-env "JASON_OWNER_UAT_MODE=$OWNER_UAT_MODE" \
  --set-env "JASON_OWNER_UAT_WORKER_ENABLED=$OWNER_UAT_WORKER" \
  --set-env "JASON_OWNER_UAT_SESSION_ID=$OWNER_UAT_SESSION" \
  --set-env "JASON_RELEASE_MOBILE_APPROVAL_MODE=$RELEASE_APPROVAL_MODE" \
  --set-env "JASON_AUTONOMY_COMPLETION_TEAMS_PROFILE=$COMPLETION_TEAMS_PROFILE"   --set-env "JASON_PM_V2_CONTROL_PROFILE=$PM_V2_CONTROL_PROFILE"   --set-env "JASON_PM_V2_SHARED_ROOT=$PM_V2_SHARED_ROOT" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_ROLE_ID_PATH=$QBO_MOUNT_BASE/role_id" \
  --set-env "JASON_QUICKBOOKS_OPENBAO_SECRET_ID_PATH=$QBO_MOUNT_BASE/secret_id" \
  --set-env "JASON_QUICKBOOKS_OAUTH_DB=$QBO_DB" \
  --set-env "JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE=$STAFF_NOTE_PROFILE" \
  --set-env "JASON_UNIVERSAL_QUERY_ENABLED=$UNIVERSAL_QUERY_ENABLED" \
  --set-env "JASON_PROVIDER_READ_ACTIVATION_PROFILE=$AUTOTASK_READ_PROFILE" \
  --set-env "JASON_QUICKBOOKS_READ_PROFILE=$QUICKBOOKS_READ_PROFILE" \
  --set-env "JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=${JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID:-}" \
  --add-readonly-bind "$QBO_ROLE_HOST:$QBO_MOUNT_BASE/role_id" \
  --add-readonly-bind "$QBO_SECRET_HOST:$QBO_MOUNT_BASE/secret_id" \
  --promote-image-tag jason-runtime:production \
  --promote-image-tag jason-runtime:local \
  --rollback-image-tag jason-runtime:rollback-current \
  --health-url http://127.0.0.1:8080/healthz   "$@"
