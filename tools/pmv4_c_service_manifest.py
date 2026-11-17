"""PMv4 Stage C exact external Ticket Core service contract.

Pure source-only manifest builder and effective Docker-inspect verifier.
It never creates a container, authenticates an Owner, reads secret contents,
or mutates production.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from tools.pmv4_ticket_core_exact_projection import expected_docker_mounts

CONTAINER_NAME = "jason-pmv4-ticket-core"
NETWORK = "jason-core"
USER = "1000:1000"
COMMAND = ("python", "-m", "jason_runtime.ticket_worker_service")
MEMORY_BYTES = 2 * 1024 * 1024 * 1024
NANO_CPUS = 1_000_000_000
PIDS_LIMIT = 256
TMPFS = {"/tmp": "rw,nosuid,nodev,noexec,size=33554432"}

class ServiceManifestDenied(RuntimeError):
    pass

def _need(ok: bool, reason: str) -> None:
    if not ok:
        raise ServiceManifestDenied(reason)

def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()

def _exact_sha(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{40}", value or "") is not None

def _exact_digest(value: str) -> bool:
    return re.fullmatch(r"sha256:[0-9a-f]{64}", value or "") is not None

# These direct-environment activation paths are unrelated to Ticket Core
# processing. The external worker never inherits them from the HTTP runtime.
FORCED_ENV = {
    "JASON_TICKET_WORKER_HOSTING": "external",
    "JASON_AUTONOMY_WORKER_ENABLED": "true",
    "JASON_AUTONOMY_WORKER_DB":
        "/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3",
    "JASON_AUTONOMY_PROMOTION_DB":
        "/var/lib/jason/ticket-core/playbook-autonomy.sqlite3",
    "JASON_AUTONOMY_TARGETED_WAKE_DB":
        "/var/lib/jason/ticket-core/autonomy-targeted-wakes.sqlite3",
    "JASON_AUTHORITY_DB": "/var/lib/jason/authority/authority.sqlite3",
    "JASON_MICROSOFT_BOUNDARY_DB":
        "/var/lib/jason/authority/client-boundaries.sqlite3",
    "JASON_TEAMS_IDENTITY_BINDINGS_DB":
        "/var/lib/jason/governed-ticket-shared/teams-identity-bindings.sqlite3",
    "JASON_ORCHESTRATION_EVENTS_DB":
        "/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3",
    "JASON_GOVERNED_EXECUTION_DB":
        "/var/lib/jason/governed-ticket-shared/governed-execution.sqlite3",
    "JASON_RESOLUTION_MEMORY_DB":
        "/var/lib/jason/governed-ticket-shared/resolution-memory.sqlite3",
    "JASON_REFLECTION_DB":
        "/var/lib/jason/governed-ticket-shared/reflection.sqlite3",
    "JASON_MODEL_USAGE_DB":
        "/var/lib/jason/governed-ticket-shared/model-usage.sqlite3",
    "JASON_DNSFILTER_MCP_OAUTH_DB":
        "/var/lib/jason/openclaw/dnsfilter-mcp/oauth.sqlite3",
    "JASON_QUICKBOOKS_OAUTH_DB":
        "/var/lib/jason/openclaw/quickbooks-production/oauth.sqlite3",
    "JASON_TEAMS_PROACTIVE_TOKEN_FILE":
        "/run/jason-secrets/teams-proactive-gateway/token",
    "JASON_HOSTED_CONVERSATION_ENABLED": "false",
    "JASON_DYNAMIC_CONVERSATION_ENABLED": "false",
    "JASON_CONVERSATION_EXPERIENCE_ENABLED": "false",
    "JASON_AUTONOMY_SHADOW_ENABLED": "false",
    "JASON_PLAYBOOK_AUTONOMY_REVIEW_ENABLED": "false",
    "JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED": "false",
    "JASON_DRMM_RECENT_ALERT_RECONCILIATION_ENABLED": "false",
    "JASON_WINDOWS_TIME_SOURCE_SHADOW_ENABLED": "false",
    "JASON_UNIVERSAL_APPROVAL_MODE": "off",
    "JASON_UNIVERSAL_APPROVAL_WORKER_ENABLED": "false",
    "JASON_RELEASE_MOBILE_APPROVAL_MODE": "off",
    "JASON_RELEASE_MOBILE_APPROVAL_WORKER_ENABLED": "false",
    "JASON_OWNER_UAT_MODE": "off",
    "JASON_OWNER_UAT_WORKER_ENABLED": "false",
    "JASON_M365_GROUP_ADMIN_PROFILE": "",
    "JASON_AUTONOMOUS_REPAIR_DEPLOYMENT_PROFILE": "",
    "JASON_PM_V2_CONTROL_PROFILE": "",
    "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE": "",
    "JASON_PROCUREMENT_WEB_READ_PROFILE": "",
}

_REQUIRED_LIVE = {
    "JASON_AUTONOMY_WORKER_ENABLED": "true",
    "JASON_AUTONOMY_WORKER_DB":
        "/var/lib/jason/openclaw/autonomy-operational-work.sqlite3",
}
_SENSITIVE = re.compile(r"(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY|API_KEY)")
_PATHISH = re.compile(r"(?:_PATH|_FILE)$")

def reviewed_worker_environment(live: Mapping[str, str]) -> dict[str, str]:
    """Copy only JASON config; reject raw secret-like environment values."""
    for key, expected in _REQUIRED_LIVE.items():
        _need(str(live.get(key, "")).strip() == expected,
              "C_SERVICE_LIVE_BASELINE_MISMATCH:" + key)
    result: dict[str, str] = {}
    for key, value in live.items():
        if not isinstance(key, str) or not key.startswith("JASON_"):
            continue
        _need(isinstance(value, str), "C_SERVICE_ENV_NOT_STRING")
        if _SENSITIVE.search(key) and not _PATHISH.search(key):
            # Exact secret material belongs only in read-only file projections.
            raise ServiceManifestDenied("C_SERVICE_RAW_SECRET_ENV_DENIED:" + key)
        _need("\x00" not in value and "\n" not in value and "\r" not in value,
              "C_SERVICE_ENV_CONTROL_CHARACTER")
        result[key] = value
    result.update(FORCED_ENV)
    # No Ticket Core worker may gain production-manager or deployment-repair
    # control through a copied HTTP-runtime environment.
    for key in (
        "JASON_AUTONOMOUS_REPAIR_DEPLOYMENT_PROFILE",
        "JASON_PM_V2_CONTROL_PROFILE",
        "JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE",
        "JASON_PROCUREMENT_WEB_READ_PROFILE",
        "JASON_M365_GROUP_ADMIN_PROFILE",
    ):
        _need(result[key] == "", "C_SERVICE_HIGH_RISK_PROFILE_NOT_DISABLED")
    _need(result["JASON_AUTOTASK_MUTATION_ENABLED"].strip().lower() == "true",
          "C_SERVICE_AUTOTASK_MUTATION_PARITY_REQUIRED")
    return dict(sorted(result.items()))

def build_manifest(live_env: Mapping[str, str], *, source_sha: str,
                   image_digest: str) -> dict[str, Any]:
    _need(_exact_sha(source_sha), "C_SERVICE_SOURCE_SHA_INVALID")
    _need(_exact_digest(image_digest), "C_SERVICE_IMAGE_DIGEST_INVALID")
    env=reviewed_worker_environment(live_env)
    env["JASON_SOURCE_REVISION"]=source_sha
    env=dict(sorted(env.items()))
    mounts=tuple(expected_docker_mounts())
    manifest={
        "schema_version": "1.0",
        "component": "pmv4-ticket-core",
        "container_name": CONTAINER_NAME,
        "source_sha": source_sha,
        "image_digest": image_digest,
        "command": list(COMMAND),
        "user": USER,
        "network_mode": NETWORK,
        "read_only_rootfs": True,
        "privileged": False,
        "cap_drop": ["ALL"],
        "cap_add": [],
        "security_opt": ["no-new-privileges:true"],
        "restart_policy": "unless-stopped",
        "memory_bytes": MEMORY_BYTES,
        "nano_cpus": NANO_CPUS,
        "pids_limit": PIDS_LIMIT,
        "tmpfs": TMPFS,
        "port_bindings": {},
        "mounts": list(mounts),
        "environment": env,
        "healthcheck": {
            "test": [
                "CMD-SHELL", "python -m jason_runtime.ticket_worker_health"
            ],
            "interval_ns": 30_000_000_000,
            "timeout_ns": 5_000_000_000,
            "retries": 3,
            "start_period_ns": 120_000_000_000,
        },
        "labels": {
            "com.aot.jason.component": "pmv4-ticket-core",
            "com.aot.jason.source_revision": source_sha,
            "com.aot.jason.provider-mutation": "governed-only",
            "com.aot.jason.production-core": "false",
            "com.aot.jason.lifecycle": "production-candidate",
        },
        "owner_authorization_issued": False,
        "production_mutations": False,
    }
    manifest["environment_sha256"]=sha256(_canon(env)).hexdigest()
    manifest["manifest_sha256"]=sha256(_canon({
        k:v for k,v in manifest.items() if k!="manifest_sha256"
    })).hexdigest()
    return manifest

def validate_effective_inspect(inspect: Mapping[str, Any],
                               manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate actual Docker inspect; no creation or repair."""
    _need(inspect.get("Name") == "/" + CONTAINER_NAME,
          "C_SERVICE_CONTAINER_NAME_MISMATCH")
    state=inspect.get("State") or {}
    config=inspect.get("Config") or {}
    host=inspect.get("HostConfig") or {}
    _need(state.get("Running") is True, "C_SERVICE_NOT_RUNNING")
    _need((state.get("Health") or {}).get("Status") == "healthy",
          "C_SERVICE_NOT_HEALTHY")
    _need(inspect.get("Image") == manifest.get("image_digest"),
          "C_SERVICE_IMAGE_MISMATCH")
    _need(config.get("User") == USER, "C_SERVICE_USER_MISMATCH")
    _need(config.get("Cmd") == list(COMMAND), "C_SERVICE_COMMAND_MISMATCH")
    _need(host.get("NetworkMode") == NETWORK, "C_SERVICE_NETWORK_MISMATCH")
    _need(host.get("ReadonlyRootfs") is True, "C_SERVICE_ROOTFS_WRITABLE")
    _need(host.get("Privileged") is False, "C_SERVICE_PRIVILEGED")
    _need(host.get("CapDrop") == ["ALL"], "C_SERVICE_CAP_DROP_MISMATCH")
    _need(host.get("CapAdd") in (None, []), "C_SERVICE_CAP_ADD_PRESENT")
    _need(host.get("SecurityOpt") == ["no-new-privileges:true"],
          "C_SERVICE_SECURITY_OPT_MISMATCH")
    _need((host.get("RestartPolicy") or {}).get("Name") == "unless-stopped",
          "C_SERVICE_RESTART_POLICY_MISMATCH")
    _need(host.get("Memory") == MEMORY_BYTES, "C_SERVICE_MEMORY_MISMATCH")
    _need(host.get("NanoCpus") == NANO_CPUS, "C_SERVICE_CPU_MISMATCH")
    _need(host.get("PidsLimit") == PIDS_LIMIT, "C_SERVICE_PIDS_MISMATCH")
    _need((host.get("PortBindings") or {}) == {},
          "C_SERVICE_PORT_BINDING_PRESENT")
    _need((config.get("ExposedPorts") or {}) == {},
          "C_SERVICE_EXPOSED_PORT_PRESENT")
    actual_env={}
    for item in config.get("Env") or []:
        _need(isinstance(item,str) and "=" in item,
              "C_SERVICE_EFFECTIVE_ENV_INVALID")
        key,value=item.split("=",1)
        if key.startswith("JASON_"):
            actual_env[key]=value
    _need(actual_env == manifest.get("environment"),
          "C_SERVICE_ENV_MISMATCH")
    actual={
        (m.get("Source"),m.get("Destination"),m.get("RW"),m.get("Type"))
        for m in inspect.get("Mounts") or []
    }
    expected={
        (m.get("Source"),m.get("Destination"),m.get("RW"),m.get("Type"))
        for m in manifest.get("mounts") or []
    }
    _need(actual == expected, "C_SERVICE_MOUNT_MISMATCH")
    _need(config.get("Labels") == manifest.get("labels"),
          "C_SERVICE_LABEL_MISMATCH")
    health=config.get("Healthcheck") or {}
    expected_health=manifest.get("healthcheck") or {}
    _need(health.get("Test") == expected_health.get("test")
          and health.get("Interval") == expected_health.get("interval_ns")
          and health.get("Timeout") == expected_health.get("timeout_ns")
          and health.get("Retries") == expected_health.get("retries")
          and health.get("StartPeriod") == expected_health.get("start_period_ns"),
          "C_SERVICE_HEALTHCHECK_MISMATCH")
    return {
        "status": "effective_ticket_core_security_verified",
        "manifest_sha256": manifest["manifest_sha256"],
        "provider_requests_executed": False,
    }
