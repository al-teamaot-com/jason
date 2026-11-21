"""Deterministic *admission* gate for deferred, governed autonomous repairs.

This pure preproduction gate is not wired to execution. A READY result means
only that observations permit a proposal to the existing playbook-governance
and Central Orchestrator authority gates. No source or ticket text grants
permission. The policy is disabled by default until script certification and
the durable owner-approved playbook record are independently verified.

Use for long-running repairs such as Windows SFC/DISM, not for generic ad-hoc
PowerShell. Never infer safety from a vendor component description alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
import re


class AdmissionState(str, Enum):
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    READY_FOR_GOVERNANCE = "ready_for_governance"


@dataclass(frozen=True)
class RepairAdmission:
    state: AdmissionState
    reasons: tuple[str, ...]

    @property
    def may_propose_to_governance(self) -> bool:
        return self.state is AdmissionState.READY_FOR_GOVERNANCE


@dataclass(frozen=True)
class CertifiedRepairPolicy:
    """Immutable reviewed contract, supplied only by trusted server policy."""

    component_uid: str
    component_name: str
    certified_script_sha256: str
    approved_playbook_id: str
    approved_playbook_version: str
    active: bool = False
    script_review_passed: bool = False
    no_reboot_or_disruption_certified: bool = False
    durable_playbook_approval_verified: bool = False
    max_cpu_percent: float | None = None
    max_disk_busy_percent: float | None = None
    min_free_gb: float | None = None
    max_active_site_repairs: int | None = None
    max_active_global_repairs: int | None = None
    max_observation_age_seconds: int = 300


@dataclass(frozen=True)
class RepairObservation:
    """Server-verified evidence, never a model's arbitrary boolean claims."""

    ticket_id: str
    device_uid: str
    ticket_bound_device_uid: str
    ticket_site_id: str
    device_site_id: str
    ticket_client_id: str
    device_client_id: str
    component_uid: str
    component_name: str
    live_script_sha256: str
    playbook_id: str
    playbook_version: str
    os_family: str
    repair_evidence_codes: frozenset[str]
    observed_at: datetime | None
    online: bool | None
    user_idle: bool | None
    cpu_percent: float | None
    disk_busy_percent: float | None
    free_gb: float | None
    on_ac_power: bool | None
    existing_repair_job: bool | None
    active_site_repairs: int | None
    active_global_repairs: int | None
    incident_repair_attempts: int
    reboot_requested: bool | None


# Only independently verified corruption/servicing outcomes qualify.
# Do not derive these codes from conversational text or LLM confidence.
_REPAIR_TRIGGER_CODES = frozenset({
    "sfc_corruption_confirmed",
    "dism_component_store_corruption_confirmed",
    "windows_servicing_corruption_confirmed",
})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _valid_percent(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and 0 <= value <= 100
    )


def evaluate_repair_admission(
    policy: CertifiedRepairPolicy,
    observed: RepairObservation,
    *,
    now: datetime | None = None,
) -> RepairAdmission:
    """Fail closed; never dispatch, grant authority, or touch the provider."""
    now = now or datetime.now(timezone.utc)
    blocked: list[str] = []
    deferred: list[str] = []

    if not policy.active:
        blocked.append("AUTONOMOUS_REPAIR_DISABLED")
    if not policy.script_review_passed or not policy.no_reboot_or_disruption_certified:
        blocked.append("SCRIPT_SAFETY_CERTIFICATION_REQUIRED")
    if not policy.durable_playbook_approval_verified:
        blocked.append("DURABLE_PLAYBOOK_AUTHORITY_REQUIRED")

    if not policy.component_uid or not policy.component_name:
        blocked.append("COMPONENT_IDENTITY_REQUIRED")
    if (observed.component_uid != policy.component_uid
            or observed.component_name != policy.component_name):
        blocked.append("COMPONENT_IDENTITY_MISMATCH")
    if (observed.playbook_id != policy.approved_playbook_id
            or observed.playbook_version != policy.approved_playbook_version
            or not observed.playbook_id or not observed.playbook_version):
        blocked.append("PLAYBOOK_VERSION_MISMATCH")

    expected = policy.certified_script_sha256
    actual = observed.live_script_sha256
    if not (_SHA256.fullmatch(expected) and _SHA256.fullmatch(actual)
            and expected == actual):
        blocked.append("LIVE_SCRIPT_REVISION_UNVERIFIED")

    if (not observed.ticket_id or not observed.device_uid
            or not observed.ticket_site_id or not observed.device_site_id
            or observed.ticket_site_id != observed.device_site_id
            or not observed.ticket_bound_device_uid
            or observed.device_uid != observed.ticket_bound_device_uid
            or not observed.ticket_client_id or not observed.device_client_id
            or observed.ticket_client_id != observed.device_client_id):
        blocked.append("TICKET_DEVICE_SCOPE_MISMATCH")
    if observed.os_family != "windows":
        blocked.append("OS_NOT_ELIGIBLE")
    if not observed.repair_evidence_codes.intersection(_REPAIR_TRIGGER_CODES):
        blocked.append("CONFIRMED_CORRUPTION_EVIDENCE_REQUIRED")
    if observed.reboot_requested is not False:
        blocked.append("REBOOT_REQUEST_NOT_ALLOWED")
    if (isinstance(observed.incident_repair_attempts, bool)
            or not isinstance(observed.incident_repair_attempts, int)
            or observed.incident_repair_attempts != 0):
        blocked.append("REPAIR_ATTEMPT_ALREADY_CONSUMED")

    age = None
    if (observed.observed_at is not None
            and observed.observed_at.tzinfo is not None
            and now.tzinfo is not None):
        age = (now - observed.observed_at).total_seconds()
    if (age is None or not 0 <= age <= policy.max_observation_age_seconds
            or policy.max_observation_age_seconds <= 0):
        deferred.append("CURRENT_DEVICE_OBSERVATION_REQUIRED")

    # Unknown safety conditions are a wait state, not permission to execute.
    if observed.online is not True:
        deferred.append("WAIT_DEVICE_ONLINE")
    if observed.user_idle is not True:
        deferred.append("WAIT_VERIFIED_IDLE_USER")
    if observed.on_ac_power is not True:
        deferred.append("WAIT_SAFE_POWER_STATE")
    if observed.existing_repair_job is not False:
        deferred.append("WAIT_EXISTING_REPAIR_JOB")

    # Heavy repairs must remain fleet-bounded, even on different endpoints.
    # A missing/invalid trusted policy cap blocks; missing/stale live counts
    # defer. This is independent of exact per-device idempotency.
    concurrency_limits = (
        (policy.max_active_site_repairs, observed.active_site_repairs,
         "WAIT_SITE_REPAIR_CAPACITY"),
        (policy.max_active_global_repairs, observed.active_global_repairs,
         "WAIT_GLOBAL_REPAIR_CAPACITY"),
    )
    for limit, active, reason in concurrency_limits:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            blocked.append("CONCURRENCY_LIMIT_NOT_CONFIGURED")
        elif (isinstance(active, bool) or not isinstance(active, int)
              or active < 0 or active >= limit):
            deferred.append(reason)

    limits = (
        (policy.max_cpu_percent, observed.cpu_percent, "WAIT_CPU_IDLE"),
        (policy.max_disk_busy_percent, observed.disk_busy_percent, "WAIT_DISK_IDLE"),
    )
    for limit, measured, reason in limits:
        if not _valid_percent(limit):
            blocked.append("RESOURCE_LIMIT_NOT_CONFIGURED")
        elif not _valid_percent(measured) or measured > limit:
            deferred.append(reason)

    if (policy.min_free_gb is None
            or isinstance(policy.min_free_gb, bool)
            or not isinstance(policy.min_free_gb, (int, float))
            or not isfinite(policy.min_free_gb)
            or policy.min_free_gb <= 0):
        blocked.append("FREE_SPACE_LIMIT_NOT_CONFIGURED")
    elif (observed.free_gb is None
          or isinstance(observed.free_gb, bool)
          or not isinstance(observed.free_gb, (int, float))
          or not isfinite(observed.free_gb)
          or observed.free_gb < policy.min_free_gb):
        deferred.append("WAIT_SUFFICIENT_FREE_SPACE")

    if blocked:
        return RepairAdmission(AdmissionState.BLOCKED, tuple(dict.fromkeys(blocked)))
    if deferred:
        return RepairAdmission(AdmissionState.DEFERRED, tuple(dict.fromkeys(deferred)))
    return RepairAdmission(AdmissionState.READY_FOR_GOVERNANCE, ())
