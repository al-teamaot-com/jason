"""Exact initial activation contract, without side effects or approval issuance."""
from copy import deepcopy
from hashlib import sha256
import json

ACTION = "INSTALL-EXACT-OWNER-OBJECTIVE-COMPLETION"
BASE_POLICY = "9110f982e7294fa789c8cd976223aa223143e924fd8bcec368f72b83a8d785b1"
UNITS = ("jason-owner-objective-executor.service", "jason-owner-objective-executor.path")
CONTAINER = "jason-owner-objective"
ROOT_TARGETS = (
    "/usr/local/lib/jason/owner-objective",
    "/etc/jason-owner-release/owner-objective.json",
    "/var/lib/jason-owner-release/objectives",
    "/var/lib/jason/owner-objective-inbox",
    "/var/lib/jason/openclaw/owner-objective",
    "/var/lib/jason/openclaw/universal-approvals.sqlite3",
    "/var/lib/jason/authority/authority.sqlite3",
    "/etc/jason/release-readback-recovery/production-desired-state.json",
    "/etc/systemd/system/jason-owner-objective-executor.service",
    "/etc/systemd/system/jason-owner-objective-executor.path",
    "/etc/systemd/system/jason-documentation-reconciliation.service.d",
)
CAPABILITIES = ("release.documentation.publisher.restore",
                "release.documentation.publisher.verify", "interaction.owner.acceptance.record")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def desired_policy(before):
    after = deepcopy(before)
    if before.get("schema_version") != "1.0":
        raise PermissionError("OBJECTIVE_BASELINE_POLICY_SCHEMA")
    if CONTAINER in before["allowed_running_containers"] or any(
            unit in before["allowed_system_units"] for unit in UNITS):
        raise PermissionError("OBJECTIVE_ALREADY_DECLARED_OR_PARTIAL_INSTALL")
    after["allowed_running_containers"] = sorted(before["allowed_running_containers"] + [CONTAINER])
    after["allowed_system_units"] = sorted(before["allowed_system_units"] + list(UNITS))
    count = before["max_stopped_rollback_containers"]
    if type(count) is not int or not 0 <= count <= 100:
        raise PermissionError("OBJECTIVE_ROLLBACK_INVENTORY_INVALID")
    after["max_stopped_rollback_containers"] = count + 1
    validate_policy_delta(before, after)
    return after


def validate_policy_delta(before, after):
    permitted = {"allowed_running_containers", "allowed_system_units", "max_stopped_rollback_containers"}
    if set(before) != set(after) or any(before[k] != after[k] for k in set(before)-permitted):
        raise PermissionError("OBJECTIVE_UNRELATED_POLICY_CHANGE")
    if (set(after["allowed_running_containers"]) != set(before["allowed_running_containers"]) | {CONTAINER}
            or set(after["allowed_system_units"]) != set(before["allowed_system_units"]) | set(UNITS)
            or after["max_stopped_rollback_containers"] != before["max_stopped_rollback_containers"] + 1):
        raise PermissionError("OBJECTIVE_POLICY_DELTA_EXCEEDS_SCOPE")
    if (len(after["allowed_running_containers"]) != len(set(after["allowed_running_containers"]))
            or len(after["allowed_system_units"]) != len(set(after["allowed_system_units"]))):
        raise PermissionError("OBJECTIVE_POLICY_DUPLICATE")


def grants(owner_identity, service_identity):
    if (not owner_identity or not service_identity or owner_identity == service_identity
            or service_identity != "jason-autonomy-worker"):
        raise PermissionError("OBJECTIVE_EXACT_REGISTERED_IDENTITIES")
    return tuple({
        "grant_id": "owner-objective-v1-" + sha256((subject+"|"+cap).encode()).hexdigest()[:32],
        "subject_id": subject, "capability": cap, "organization_id": "aot", "client_id": None,
        "permission": "execute", "approval_required": subject == service_identity,
        "effective_from": None, "effective_until": None, "status": "active",
    } for subject in (owner_identity, service_identity) for cap in CAPABILITIES)
