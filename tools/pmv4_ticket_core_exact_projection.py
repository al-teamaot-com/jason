"""Stage C reviewed, structural external worker projection. READ-ONLY.

This is NOT a new authority or approval plane. Root release verifier must bind
this source/manifest and actual Docker inspect to an exact signed Owner plan
before any production mount, credential, data migration or process change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

class ProjectionDenied(PermissionError):
    pass

TICKET = Path("/var/lib/jason/ticket-core")
AUTHORITY = Path("/var/lib/jason/authority")
SHARED = Path("/var/lib/jason/governed-ticket-shared")
LEGACY = Path("/var/lib/jason/openclaw")

STATE_MOUNTS = (
    str(TICKET), str(AUTHORITY), str(SHARED),
)

# Existing production source paths observed 2026-11-17; no provider password
# or token value, no directory-wide secret projection. Every file is RO.
# The separately governed root cutover must independently verify role scope,
# realpath/UID/mode, and the current signed production-readback identifiers.
CREDENTIAL_MOUNTS = (
    ("/run/jason-runtime-credentials/openbao/autotask/role_id",
     "/run/jason-secrets/openbao/autotask/role_id"),
    ("/run/jason-runtime-credentials/openbao/autotask/secret_id",
     "/run/jason-secrets/openbao/autotask/secret_id"),
    ("/var/lib/jason/runtime-secrets/openbao/autotask-write-approle/role-id",
     "/run/jason-secrets/openbao/autotask-write/role_id"),
    ("/var/lib/jason/runtime-secrets/openbao/autotask-write-approle/secret-id",
     "/run/jason-secrets/openbao/autotask-write/secret_id"),
    ("/var/lib/jason/runtime-secrets/openbao/aws-ses-sendmail-approle/role-id",
     "/run/jason-secrets/openbao/aws-ses/role_id"),
    ("/var/lib/jason/runtime-secrets/openbao/aws-ses-sendmail-approle/secret-id",
     "/run/jason-secrets/openbao/aws-ses/secret_id"),
    ("/var/lib/jason/runtime-secrets/openbao/backup-net-read-approle/role-id",
     "/run/jason-secrets/openbao/backup-net/role_id"),
    ("/var/lib/jason/runtime-secrets/openbao/backup-net-read-approle/secret-id",
     "/run/jason-secrets/openbao/backup-net/secret_id"),
    ("/var/lib/jason/runtime-secrets/openbao/backup-net-full-access-approle/role-id",
     "/run/jason-secrets/openbao/backup-net-full-access/role_id"),
    ("/var/lib/jason/runtime-secrets/openbao/backup-net-full-access-approle/secret-id",
     "/run/jason-secrets/openbao/backup-net-full-access/secret_id"),
    ("/opt/jason/bootstrap/secrets/openbao/datto-edr-read-approle/role-id",
     "/run/jason-secrets/openbao/datto-edr/role_id"),
    ("/opt/jason/bootstrap/secrets/openbao/datto-edr-read-approle/secret-id",
     "/run/jason-secrets/openbao/datto-edr/secret_id"),
    ("/opt/jason/bootstrap/secrets/openbao/datto-rmm-execution-approle/role-id",
     "/run/jason-secrets/openbao/datto-rmm-execution/role_id"),
    ("/opt/jason/bootstrap/secrets/openbao/datto-rmm-execution-approle/secret-id",
     "/run/jason-secrets/openbao/datto-rmm-execution/secret_id"),
    ("/var/lib/jason/runtime-secrets/openbao/datto-rmm-execution-approle/role-id",
     "/run/jason-secrets/openbao/datto-rmm-execution-v2/role_id"),
    ("/var/lib/jason/runtime-secrets/openbao/datto-rmm-execution-approle/secret-id",
     "/run/jason-secrets/openbao/datto-rmm-execution-v2/secret_id"),
    ("/opt/jason/bootstrap/secrets/openbao/microsoft-graph-directory-read-approle/role-id",
     "/run/jason-secrets/openbao/microsoft-graph/role_id"),
    ("/opt/jason/bootstrap/secrets/openbao/microsoft-graph-directory-read-approle/secret-id",
     "/run/jason-secrets/openbao/microsoft-graph/secret_id"),
    ("/opt/jason/bootstrap/secrets/openbao/openai-semantic-intent-approle/role-id",
     "/run/jason-secrets/openbao/openai/role_id"),
    ("/opt/jason/bootstrap/secrets/openbao/openai-semantic-intent-approle/secret-id",
     "/run/jason-secrets/openbao/openai/secret_id"),
)

# These are the exact preprod durable stores opened by the reviewed ticket
# component. They must be migrated or accessed canonically under one governed
# transaction. The worker must never inherit unrelated HTTP/PM state paths.
STATE_PATHS = {
    "autonomy_worker_db": TICKET/"autonomy-operational-work.sqlite3",
    "autonomy_promotion_db": TICKET/"playbook-autonomy.sqlite3",
    "autonomy_targeted_wake_db": TICKET/"autonomy-targeted-wakes.sqlite3",
    "authority_db": AUTHORITY/"authority.sqlite3",
    "bindings_db": SHARED/"teams-identity-bindings.sqlite3",
    "orchestration_events_db": SHARED/"orchestration-events.sqlite3",
    "governed_execution_db": SHARED/"governed-execution.sqlite3",
    "resolution_memory_db": SHARED/"resolution-memory.sqlite3",
    "reflection_db": SHARED/"reflection.sqlite3",
    "microsoft_boundary_db": AUTHORITY/"client-boundaries.sqlite3",
}

def expected_docker_mounts() -> tuple[dict[str,Any], ...]:
    state=tuple({
        "Type":"bind", "Source":p, "Destination":p, "RW":True
    } for p in STATE_MOUNTS)
    credentials=tuple({
        "Type":"bind", "Source":source, "Destination":dest, "RW":False
    } for source,dest in CREDENTIAL_MOUNTS)
    return state+credentials

def validate_exact_mounts(mounts:Sequence[Mapping[str,Any]]) -> dict[str,Any]:
    """Effective Docker inspect check; no arbitrary host state or credentials."""
    expected={
        (x["Source"],x["Destination"],x["RW"],x["Type"])
        for x in expected_docker_mounts()
    }
    if not isinstance(mounts,(list,tuple)) or len(mounts)!=len(expected):
        raise ProjectionDenied("CORE_EXACT_MOUNT_COUNT_MISMATCH")
    received=[]
    for mount in mounts:
        if not isinstance(mount,Mapping):
            raise ProjectionDenied("CORE_EXACT_MOUNT_NOT_OBJECT")
        raw=(mount.get("Source"),mount.get("Destination"),
             mount.get("RW"),mount.get("Type"))
        if (not isinstance(raw[0],str) or not isinstance(raw[1],str)
            or type(raw[2]) is not bool or raw[3] != "bind"
            or raw[0] != str(Path(raw[0])) or raw[1] != str(Path(raw[1]))
            or ".." in Path(raw[0]).parts or ".." in Path(raw[1]).parts):
            raise ProjectionDenied("CORE_EXACT_MOUNT_INVALID")
        if raw not in expected or raw in received:
            raise ProjectionDenied("CORE_EXACT_MOUNT_NOT_APPROVED")
        received.append(raw)
    if set(received)!=expected:
        raise ProjectionDenied("CORE_EXACT_MOUNT_SET_MISMATCH")
    return {
        "mount_shape":"reviewed_exact_v1",
        "state_mount_count":len(STATE_MOUNTS),
        "credential_mount_count":len(CREDENTIAL_MOUNTS),
        "provider_requests_executed":False,
        "root_owner_release_verified":False,
    }

def validate_exact_settings(settings:Any) -> dict[str,Any]:
    """Pure source-path gate. No file IO or service/provider mutations."""
    if (getattr(settings,"ticket_worker_hosting",None)!="external"
        or getattr(settings,"autonomy_worker_enabled",None) is not True):
        raise ProjectionDenied("CORE_EXACT_EXTERNAL_WORKER_MODE_REQUIRED")
    for key,expected in STATE_PATHS.items():
        actual=getattr(settings,key,None)
        if actual is None and key=="microsoft_boundary_db":
            actual=Path(getattr(settings,"authority_db","")).with_name(
                "client-boundaries.sqlite3")
        if actual is None and key=="reflection_db":
            actual=Path(getattr(settings,"orchestration_events_db","")).with_name(
                "reflection.sqlite3")
        if not isinstance(actual,Path) or actual!=expected:
            raise ProjectionDenied("CORE_EXACT_STATE_PATH_MISMATCH:"+key)
    return {
        "status":"source_paths_reviewed",
        "external_worker_ready":False,
        "owner_authorization_issued":False,
        "production_mutations":False,
    }
