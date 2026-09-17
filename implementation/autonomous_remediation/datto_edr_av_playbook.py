"""Governed Datto EDR/AV diagnose-and-repair playbook.

This module is deliberately provider-neutral orchestration logic. It does not
contact Datto RMM, Autotask, or an endpoint. The central Jason orchestrator is
responsible for resolving the named capabilities below to governed provider
operations and for enforcing authorization before every execution.

The playbook is intentionally bounded:

* every meaningful repair is followed by an authoritative health check;
* a repair step is attempted at most once per playbook run;
* duplicate provider jobs are prevented with deterministic idempotency keys;
* immediate reboot is approval-gated;
* a scheduled 02:30 local reboot may be proposed, then verification resumes at
  03:30 local time;
* clean uninstall/reinstall is a policy-gated overnight recovery step;
* the only terminal outcomes are healthy or escalation required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


PLAYBOOK_NAME = "Jason - Datto EDR/AV Diagnose & Repair"
PLAYBOOK_VERSION = "1.0.0"
HEALTHY_STATUS = "Healthy"

# Existing governed Datto component names already proven/identified in Jason.
HEALTH_CHECK_COMPONENT = "Check Datto EDR/AV Status AOT Ver 12122025-1"
SERVICE_DETAIL_COMPONENT = "Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1"
EDR_MAINTENANCE_COMPONENT = "Datto EDR Maintenance [WIN]"
EDR_FORCE_REINSTALL_COMPONENT = "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"
EDR_AV_UNINSTALL_COMPONENT = "Uninstall Datto EDR / AV AOT Ver 11052025-1"

# This command is a governed, predefined Datto AV operation. It must be routed
# through Jason's registered execution capability rather than an ad-hoc shell.
AV_FORCE_UPDATE_COMMAND = "agent.exe datto-av --force-update"


class PlaybookState(str, Enum):
    NEW = "new"
    DIAGNOSING = "diagnosing"
    REPAIRING = "repairing"
    VERIFYING = "verifying"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_SCHEDULED_REBOOT = "awaiting_scheduled_reboot"
    AWAITING_POST_REBOOT_VERIFY = "awaiting_post_reboot_verify"
    HEALTHY = "healthy"
    ESCALATION_REQUIRED = "escalation_required"


class ActionKind(str, Enum):
    COMPONENT = "component"
    PREDEFINED_COMMAND = "predefined_command"
    SCHEDULED_REBOOT = "scheduled_reboot"
    IMMEDIATE_REBOOT = "immediate_reboot"


class ApprovalClass(str, Enum):
    STANDING_SAFE = "standing_safe"
    APPROVAL_REQUIRED = "approval_required"
    POLICY_GATED = "policy_gated"


class RepairStep(str, Enum):
    HEALTH_CHECK = "health_check"
    SERVICE_DETAIL = "service_detail"
    EDR_MAINTENANCE = "edr_maintenance"
    EDR_FORCE_REINSTALL = "edr_force_reinstall"
    AV_FORCE_UPDATE = "av_force_update"
    SCHEDULED_REBOOT = "scheduled_reboot"
    CLEAN_UNINSTALL = "clean_uninstall"
    POST_REBOOT_VERIFY = "post_reboot_verify"


@dataclass(frozen=True)
class HealthObservation:
    """Normalized result of the authoritative Datto EDR/AV health check."""

    status: str
    hunt_agent_installed: bool | None = None
    hunt_agent_running: bool | None = None
    hunt_agent_startup: str | None = None
    edr_current: bool | None = None
    av_present: bool | None = None
    av_healthy: bool | None = None
    endpoint_protection_service_running: bool | None = None
    security_center_healthy: bool | None = None
    reboot_required: bool = False
    endpoint_reachable: bool = True
    tamper_or_registration_blocked: bool = False
    summary: str = ""
    evidence_refs: tuple[str, ...] = ()

    @property
    def is_authoritatively_healthy(self) -> bool:
        return self.status.strip().lower() == HEALTHY_STATUS.lower()


@dataclass(frozen=True)
class PlannedAction:
    step: RepairStep
    kind: ActionKind
    approval_class: ApprovalClass
    operation: str
    variables: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    verify_after: bool = False
    idempotency_key: str = ""
    schedule_local: str | None = None
    resume_local: str | None = None


@dataclass
class PlaybookRun:
    """Persistable state for one ticket/device playbook run."""

    run_id: str
    ticket_id: str
    device_id: str
    organization_id: str
    client_id: str
    state: PlaybookState = PlaybookState.NEW
    attempted_steps: set[RepairStep] = field(default_factory=set)
    completed_job_keys: set[str] = field(default_factory=set)
    evidence_refs: list[str] = field(default_factory=list)
    last_health: HealthObservation | None = None
    escalation_reasons: list[str] = field(default_factory=list)

    def idempotency_key(self, step: RepairStep) -> str:
        return f"{self.run_id}:{self.ticket_id}:{self.device_id}:{PLAYBOOK_VERSION}:{step.value}"

    def record_job(self, action: PlannedAction, *, evidence_refs: Sequence[str] = ()) -> None:
        """Record one governed execution and make a duplicate attempt impossible."""

        if action.idempotency_key in self.completed_job_keys:
            raise DuplicateExecutionError(action.idempotency_key)
        self.completed_job_keys.add(action.idempotency_key)
        self.attempted_steps.add(action.step)
        self.evidence_refs.extend(evidence_refs)

    def record_health(self, observation: HealthObservation) -> None:
        self.last_health = observation
        self.evidence_refs.extend(observation.evidence_refs)
        if observation.is_authoritatively_healthy:
            self.state = PlaybookState.HEALTHY
        else:
            self.state = PlaybookState.VERIFYING

    def escalate(self, reason: str) -> None:
        if reason not in self.escalation_reasons:
            self.escalation_reasons.append(reason)
        self.state = PlaybookState.ESCALATION_REQUIRED


class DuplicateExecutionError(RuntimeError):
    pass


class InvalidPlaybookTransition(RuntimeError):
    pass


def initial_health_check(run: PlaybookRun) -> PlannedAction:
    """Always begin with a fresh authoritative health check."""

    run.state = PlaybookState.DIAGNOSING
    return _component_action(
        run,
        RepairStep.HEALTH_CHECK,
        HEALTH_CHECK_COMPONENT,
        ApprovalClass.STANDING_SAFE,
        reason="Establish current Datto EDR/AV state before any remediation.",
        verify_after=False,
    )


def next_action(run: PlaybookRun, observation: HealthObservation | None = None) -> PlannedAction | None:
    """Return the next bounded action after a health observation.

    The caller must pass results only from the authoritative health-check path.
    Provider job success alone is never interpreted as endpoint health.
    """

    if observation is not None:
        run.record_health(observation)

    if run.state == PlaybookState.HEALTHY:
        return None
    if run.state == PlaybookState.ESCALATION_REQUIRED:
        return None

    health = run.last_health
    if health is None:
        return initial_health_check(run)

    if not health.endpoint_reachable:
        run.escalate("Endpoint is unreachable; governed remediation cannot be verified safely.")
        return None

    if health.tamper_or_registration_blocked:
        run.escalate("Datto EDR/AV tamper or registration state blocks safe automated recovery.")
        return None

    # When AV's EndpointProtectionService is the observed problem, collect a
    # narrowly scoped service diagnostic before broad repair. Service restarts
    # remain disruptive and are not silently performed by this playbook.
    if health.endpoint_protection_service_running is False and RepairStep.SERVICE_DETAIL not in run.attempted_steps:
        run.state = PlaybookState.DIAGNOSING
        return _component_action(
            run,
            RepairStep.SERVICE_DETAIL,
            SERVICE_DETAIL_COMPONENT,
            ApprovalClass.STANDING_SAFE,
            variables={"ServiceName": "EndpointProtectionService"},
            reason="AV service is stopped; collect service-specific evidence before repair.",
            verify_after=False,
        )

    # Missing/broken EDR receives one bounded maintenance attempt first.
    if _edr_missing_or_broken(health) and RepairStep.EDR_MAINTENANCE not in run.attempted_steps:
        run.state = PlaybookState.REPAIRING
        return _component_action(
            run,
            RepairStep.EDR_MAINTENANCE,
            EDR_MAINTENANCE_COMPONENT,
            ApprovalClass.STANDING_SAFE,
            reason="EDR is missing or unhealthy; run the least disruptive registered maintenance repair.",
            verify_after=True,
        )

    # If maintenance did not produce authoritative health, allow one forced
    # reinstall/upgrade before considering reboot or destructive recovery.
    if _edr_missing_or_broken(health) and RepairStep.EDR_FORCE_REINSTALL not in run.attempted_steps:
        run.state = PlaybookState.REPAIRING
        return _component_action(
            run,
            RepairStep.EDR_FORCE_REINSTALL,
            EDR_FORCE_REINSTALL_COMPONENT,
            ApprovalClass.STANDING_SAFE,
            reason="EDR remains missing, unhealthy, or out of date after the maintenance stage.",
            verify_after=True,
        )

    # AV missing/unhealthy receives one governed force-update attempt. This is
    # intentionally a predefined command, not free-form shell execution.
    if _av_needs_repair(health) and RepairStep.AV_FORCE_UPDATE not in run.attempted_steps:
        run.state = PlaybookState.REPAIRING
        return PlannedAction(
            step=RepairStep.AV_FORCE_UPDATE,
            kind=ActionKind.PREDEFINED_COMMAND,
            approval_class=ApprovalClass.STANDING_SAFE,
            operation=AV_FORCE_UPDATE_COMMAND,
            reason="AV remains missing, stale, or unhealthy; request Datto AV refresh/update.",
            verify_after=True,
            idempotency_key=run.idempotency_key(RepairStep.AV_FORCE_UPDATE),
        )

    # A reported pending reboot is handled as a resumable overnight action.
    # The default playbook proposal is a 02:30 local reboot followed by a fresh
    # 03:30 health check. Immediate reboot is not inferred from diagnosis.
    if health.reboot_required and RepairStep.SCHEDULED_REBOOT not in run.attempted_steps:
        run.state = PlaybookState.AWAITING_SCHEDULED_REBOOT
        return PlannedAction(
            step=RepairStep.SCHEDULED_REBOOT,
            kind=ActionKind.SCHEDULED_REBOOT,
            approval_class=ApprovalClass.APPROVAL_REQUIRED,
            operation="device.reboot.schedule",
            reason="Repair is pending reboot; schedule low-impact overnight reboot and resume verification.",
            verify_after=True,
            idempotency_key=run.idempotency_key(RepairStep.SCHEDULED_REBOOT),
            schedule_local="02:30",
            resume_local="03:30",
        )

    # If ordinary repair paths are exhausted and the endpoint is still
    # unhealthy, expose (but do not auto-authorize) the clean recovery branch.
    if _ordinary_repairs_exhausted(run, health) and RepairStep.CLEAN_UNINSTALL not in run.attempted_steps:
        run.state = PlaybookState.AWAITING_APPROVAL
        return _component_action(
            run,
            RepairStep.CLEAN_UNINSTALL,
            EDR_AV_UNINSTALL_COMPONENT,
            ApprovalClass.POLICY_GATED,
            reason=(
                "Standard EDR/AV repair paths are exhausted. Clean uninstall is the supervised overnight "
                "recovery branch and requires policy/technician authorization before execution."
            ),
            verify_after=True,
        )

    run.escalate(_escalation_summary(run, health))
    return None


def verification_action(run: PlaybookRun) -> PlannedAction:
    """Build the fresh authoritative check required after a repair or reboot."""

    if run.state in {PlaybookState.HEALTHY, PlaybookState.ESCALATION_REQUIRED}:
        raise InvalidPlaybookTransition(f"Cannot verify from terminal state {run.state.value}")
    run.state = PlaybookState.VERIFYING
    # Verification jobs use a distinct key from the first health check while
    # remaining deterministic for each repair attempt.
    completed_repairs = sorted(step.value for step in run.attempted_steps if step != RepairStep.HEALTH_CHECK)
    suffix = completed_repairs[-1] if completed_repairs else "initial"
    return PlannedAction(
        step=RepairStep.POST_REBOOT_VERIFY if RepairStep.SCHEDULED_REBOOT in run.attempted_steps else RepairStep.HEALTH_CHECK,
        kind=ActionKind.COMPONENT,
        approval_class=ApprovalClass.STANDING_SAFE,
        operation=HEALTH_CHECK_COMPONENT,
        reason="Verify the endpoint with the authoritative Datto EDR/AV health component.",
        verify_after=False,
        idempotency_key=f"{run.run_id}:{run.ticket_id}:{run.device_id}:{PLAYBOOK_VERSION}:verify:{suffix}",
    )


def internal_ticket_note(run: PlaybookRun) -> str:
    """Return a concise internal-only Autotask progress/final note."""

    health = run.last_health.status if run.last_health is not None else "not yet verified"
    attempts = ", ".join(sorted(step.value for step in run.attempted_steps)) or "none"
    if run.state == PlaybookState.HEALTHY:
        outcome = "Healthy - authoritative Datto EDR/AV verification passed."
    elif run.state == PlaybookState.ESCALATION_REQUIRED:
        reasons = "; ".join(run.escalation_reasons) or "Repair ladder exhausted without authoritative health."
        outcome = f"EscalationRequired - {reasons}"
    elif run.state == PlaybookState.AWAITING_SCHEDULED_REBOOT:
        outcome = "Pending approved 02:30 local reboot; resume health verification at 03:30 local."
    elif run.state == PlaybookState.AWAITING_APPROVAL:
        outcome = "Pending approval for policy-gated clean EDR/AV recovery."
    else:
        outcome = "Diagnosis/repair in progress."

    return (
        f"{PLAYBOOK_NAME}\n"
        f"Device: {run.device_id}\n"
        f"State: {run.state.value}\n"
        f"Last health: {health}\n"
        f"Attempted: {attempts}\n"
        f"Outcome: {outcome}"
    )


def _component_action(
    run: PlaybookRun,
    step: RepairStep,
    component: str,
    approval_class: ApprovalClass,
    *,
    variables: Mapping[str, Any] | None = None,
    reason: str,
    verify_after: bool,
) -> PlannedAction:
    return PlannedAction(
        step=step,
        kind=ActionKind.COMPONENT,
        approval_class=approval_class,
        operation=component,
        variables=dict(variables or {}),
        reason=reason,
        verify_after=verify_after,
        idempotency_key=run.idempotency_key(step),
    )


def _edr_missing_or_broken(health: HealthObservation) -> bool:
    return any(
        value is False
        for value in (
            health.hunt_agent_installed,
            health.hunt_agent_running,
            health.edr_current,
        )
    )


def _av_needs_repair(health: HealthObservation) -> bool:
    return any(
        value is False
        for value in (
            health.av_present,
            health.av_healthy,
            health.endpoint_protection_service_running,
            health.security_center_healthy,
        )
    )


def _ordinary_repairs_exhausted(run: PlaybookRun, health: HealthObservation) -> bool:
    needs_edr = _edr_missing_or_broken(health)
    needs_av = _av_needs_repair(health)
    edr_done = not needs_edr or {
        RepairStep.EDR_MAINTENANCE,
        RepairStep.EDR_FORCE_REINSTALL,
    }.issubset(run.attempted_steps)
    av_done = not needs_av or RepairStep.AV_FORCE_UPDATE in run.attempted_steps
    return (needs_edr or needs_av) and edr_done and av_done and not health.reboot_required


def _escalation_summary(run: PlaybookRun, health: HealthObservation) -> str:
    details: list[str] = []
    if _edr_missing_or_broken(health):
        details.append("EDR remains unhealthy after bounded repair attempts")
    if _av_needs_repair(health):
        details.append("AV remains unhealthy after bounded repair attempts")
    if not details:
        details.append("Datto health status remains non-Healthy with no safe remaining playbook step")
    if RepairStep.CLEAN_UNINSTALL in run.attempted_steps:
        details.append("clean recovery was already attempted")
    return "; ".join(details) + "."
