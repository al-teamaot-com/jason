"""Exact migration transaction model; no independent authority or CLI.

The already authenticated native root release path supplies the adapter and
immutable reviewed plan. The model enforces ordering and fail-closed rollback.
No function here constructs a privileged systemctl request from caller input.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
import re

TIMERS = ("jason-pmv4-engineering.timer", "jason-self-heal-watchdog.timer")
SERVICES = tuple(n.replace(".timer", ".service") for n in TIMERS)
ACTION = "RELOCATE-EXACT-PMV4-ENGINEERING-AND-WATCHDOG-MANAGERS"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
PROFILE = "itglue-autotask-entra-dynamic-schema-read-catalog-v13"
ENV_BEFORE = ("JASON_EXPECTED_MCP_SOURCE_REVISION=" + LKG + "\n").encode()
PROFILE_SOURCE_SHA = "24ec1ad019c02ff8d93da3d9002ae0207cf05cd413e2da6ef73036f2b1e520d8"


def need(condition, reason):
    if not condition:
        raise PermissionError("ENGINEERING_MANAGER_TRANSACTION_" + reason)


def canonical(row):
    return json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def monitoring_environment(before, profile_raw, manifest):
    """Derive expectations from immutable approved state, not live discovery."""
    need(before == ENV_BEFORE, "MONITORING_BEFORE_CHANGED")
    need(digest(profile_raw) == PROFILE_SOURCE_SHA, "APPROVED_PROFILE_SOURCE_CHANGED")
    profile = json.loads(profile_raw)
    need(profile == {"schema_version": "1.0", "read_profile": PROFILE,
                     "rollback_read_profile": PROFILE}, "APPROVED_PROFILE_NOT_EXACT")
    need(manifest.get("complete") is True
         and all(manifest.get(k) == LKG for k in ("revision", "mcp_revision", "runtime_revision"))
         and manifest.get("mcp_image_id") == MCP_IMAGE, "ROOT_LKG_IMAGE_NOT_EXACT")
    return before + ("JASON_EXPECTED_MCP_IMAGE_PREFIX=" + MCP_IMAGE + "\n"
                     "JASON_EXPECTED_PROVIDER_PROFILE=" + PROFILE + "\n").encode()


def verify_plan(plan):
    need(isinstance(plan, dict) and plan.get("action") == ACTION
         and plan.get("policy", {}).get("rollback_sha") == LKG
         and re.fullmatch("[0-9a-f]{40}", str(plan.get("policy", {}).get("candidate_sha", "")))
         and plan["policy"]["candidate_sha"] != LKG, "PLAN_IDENTITY")
    need(plan.get("old_user_timers") == list(TIMERS)
         and plan.get("new_system_timers") == list(TIMERS)
         and plan.get("services") == list(SERVICES)
         and plan.get("production_authority") is False
         and plan.get("provider_writes") is False
         and plan.get("runtime_or_mcp_restart_allowed") is False
         and plan.get("freeze_or_hold_change") is False
         and plan.get("monitoring_restart") == "jason-production-health-exporter.service"
         and plan.get("pause_preserved_during_cutover") is True
         and plan.get("rollback_authorized") is True, "PLAN_SCOPE")
    return digest(canonical(plan))


def migrate(adapter, plan, approved_scope_sha):
    """Execute only after independent Owner verification by the native adapter.

    Native file/lock custody, actual systemd operations, exact approval evidence
    and all immutable bytes belong to the adapter. This is not a new signer.
    """
    need(verify_plan(plan) == approved_scope_sha, "APPROVED_SCOPE_CHANGED")
    original = deepcopy(plan)
    need(adapter.verify_owner_and_before(plan, approved_scope_sha) is True, "NATIVE_APPROVAL_REQUIRED")
    # No mutating operation may precede the durable before-image. A failed
    # receipt write is not a reason to start/stop otherwise unchanged services.
    adapter.persist_before_images(plan)
    try:
        adapter.stop_old_timers(TIMERS)
        adapter.verify_old_services_quiescent(SERVICES)
        adapter.publish_files_without_receipt(plan)
        adapter.reload_managers()
        adapter.verify_old_units_retired(TIMERS + SERVICES)
        adapter.enable_new_system_timers(TIMERS)
        adapter.verify_new_timers(TIMERS)
        adapter.restart_exact_monitoring_exporter()
        adapter.verify_approved_monitoring_expectations()
        adapter.publish_exact_native_receipt(plan, approved_scope_sha)
        adapter.verify_successor_topology_and_source()
        adapter.verify_preserved_pause_and_controls()
        adapter.verify_native_drift_and_lkg()
        need(plan == original, "PLAN_MUTATED")
        adapter.record_cutover_verified()
    except BaseException:
        # The native adapter restores only approved before/after identities,
        # never clobbers foreign state and never force-writes the breaker.
        adapter.restore_before_images_and_topology(original)
        adapter.verify_rollback_and_preserved_controls()
        adapter.record_rollback()
        raise


def verify_scheduled_acceptance(adapter):
    """Require real scheduled execution after the separately authorized resume."""
    evidence = adapter.actual_normal_cycle_evidence()
    need(isinstance(evidence, dict)
         and evidence.get("normal_timer_invocation") is True
         and evidence.get("native_manager_guard") == "pass"
         and evidence.get("worker_identity") == "al"
         and evidence.get("pipeline_completed") is True
         and evidence.get("dependency_admission_verified") is True
         and evidence.get("conflicting_work_blocked") is True
         and evidence.get("protected_peers_unchanged") is True
         and evidence.get("native_drift") == "pass"
         and evidence.get("breaker") == "closed"
         and evidence.get("production_authority") is False,
         "SCHEDULED_ACCEPTANCE_INCOMPLETE")
    return evidence
