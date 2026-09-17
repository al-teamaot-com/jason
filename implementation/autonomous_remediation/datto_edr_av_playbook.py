"""Governed Datto EDR/AV diagnose-and-repair playbook.

This module is provider-neutral orchestration logic. It never contacts Datto
RMM, Autotask, or an endpoint directly. The central Jason orchestrator resolves
named operations to governed capabilities and enforces authorization at runtime.

The workflow is intentionally bounded and deterministic:

* every meaningful repair is followed by the authoritative health component;
* provider job success is never interpreted as endpoint health;
* every remediation step has an explicit per-run attempt limit;
* duplicate provider jobs are prevented with deterministic idempotency keys;
* scheduled 02:30 local reboot is standing-authorized only inside this named
  playbook and always resumes verification at 03:30 local time;
* immediate reboot remains approval-required;
* clean uninstall/recovery remains policy-gated during the supervised pilot;
* read/poll failure never causes a second remediation dispatch;
* the only terminal outcomes are Healthy or EscalationRequired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


PLAYBOOK_NAME = "Jason - Datto EDR/AV Diagnose & Repair"
PLAYBOOK_VERSION = "1.1.0"
HEALTHY_STATUS = "Healthy"

HEALTH_CHECK_COMPONENT = "Check Datto EDR/AV Status AOT Ver 12122025-1"
SERVICE_DETAIL_COMPONENT = "Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1"
EDR_MAINTENANCE_COMPONENT = "Datto EDR Maintenance [WIN]"
EDR_FORCE_REINSTALL_COMPONENT = "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"
EDR_AV_UNINSTALL_COMPONENT = "Uninstall Datto EDR / AV AOT Ver 11052025-1"
SCHEDULED_REBOOT_COMPONENT = "230 AM Scheduled Reboot AOT Ver 11282024"

# This is a predefined governed operation, not permission for arbitrary shell.
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
    POST_REBOOT_AV_FORCE_UPDATE = "post_reboot_av_force_update"
    SCHEDULED_REBOOT = "scheduled_reboot"
    CLEAN_UNINSTALL = "clean_uninstall"
    RECOVERY_REBOOT = "recovery_reboot"
    RECOVERY_MAINTENANCE = "recovery_maintenance"
    RECOVERY_FORCE_REINSTALL = "recovery_force_reinstall"
    RECOVERY_AV_FORCE_UPDATE = "recovery_av_force_update"
    POST_REBOOT_VERIFY = "post_reboot_verify"


@dataclass(frozen=True)
class HealthObservation:
    """Normalized result of the authoritative Datto EDR/AV health check."""

    status: str
    hunt_agent_installed: bool | None = None
    hunt_agent_running: bool | None = None
    hunt_agent_startup: str | None = None
    edr_current: bool | None = None
    edr_version: str | None = None
    hunt_agent_path: str | None = None
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
class ExecutionObservation:
    """Provider execution evidence used only to control the next safe step."""

    terminal: bool
    provider_status: str
    job_id: str = ""
    stdout_reference: str = ""
    stdout_observed: bool = True
    timed_out: bool = False
    read_failed: bool = False
    evidence_refs: tuple[str, ...] = ()

    @property
    def force_update_appears_hung(self) -> bool:
        return self.timed_out or (self.terminal is False and not self.stdout_observed)


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
    attempt_order: list[RepairStep] = field(default_factory=list)
    completed_job_keys: set[str] = field(default_factory=set)
    evidence_refs: list[str] = field(default_factory=list)
    provider_job_ids: list[str] = field(default_factory=list)
    last_health: HealthObservation | None = None
    escalation_reasons: list[str] = field(default_factory=list)
    force_update_pending_reboot: bool = False
    scheduled_reboot_used: bool = False
    recovery_reboot_used: bool = False

    def idempotency_key(self, step: RepairStep) -> str:
        return f"{self.run_id}:{self.ticket_id}:{self.device_id}:{PLAYBOOK_VERSION}:{step.value}"

    def record_job(self, action: PlannedAction, *, evidence_refs: Sequence[str] = ()) -> None:
        """Record one governed dispatch and make redispatch impossible."""

        if action.idempotency_key in self.completed_job_keys:
            raise DuplicateExecutionError(action.idempotency_key)
        self.completed_job_keys.add(action.idempotency_key)
        self.attempted_steps.add(action.step)
        self.attempt_order.append(action.step)
        self.evidence_refs.extend(evidence_refs)
        if action.step == RepairStep.SCHEDULED_REBOOT:
            self.scheduled_reboot_used = True
        if action.step == RepairStep.RECOVERY_REBOOT:
            self.recovery_reboot_used = True

    def record_execution(self, action: PlannedAction, result: ExecutionObservation) -> None:
        """Attach provider evidence without treating provider success as health."""

        self.evidence_refs.extend(result.evidence_refs)
        if result.job_id and result.job_id not in self.provider_job_ids:
            self.provider_job_ids.append(result.job_id)

        # A failed read/poll is a read problem, not permission to redispatch.
        if result.read_failed:
            return

        if action.step in {
            RepairStep.AV_FORCE_UPDATE,
            RepairStep.POST_REBOOT_AV_FORCE_UPDATE,
            RepairStep.RECOVERY_AV_FORCE_UPDATE,
        } and result.force_update_appears_hung:
            self.force_update_pending_reboot = True

    def record_health(self, observation: HealthObservation) -> None:
        self.last_health = observation
        self.evidence_refs.extend(observation.evidence_refs)
        if observation.is_authoritatively_healthy:
            self.force_update_pending_reboot = False
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
    """Return the next bounded action after authoritative health evidence."""

    if observation is not None:
        run.record_health(observation)

    if run.state in {PlaybookState.HEALTHY, PlaybookState.ESCALATION_REQUIRED}:
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

    # Once clean recovery starts, stay in that deterministic branch.
    if RepairStep.CLEAN_UNINSTALL in run.attempted_steps:
        return _next_recovery_action(run, health)

    # A force-update that produces no useful output is never redispatched. One
    # low-impact overnight reboot is scheduled and the same endpoint is checked
    # again at 03:30 local time.
    if run.force_update_pending_reboot and RepairStep.SCHEDULED_REBOOT not in run.attempted_steps:
        return _scheduled_reboot_action(run, RepairStep.SCHEDULED_REBOOT)

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

    if _edr_missing_or_broken(health) and RepairStep.EDR_FORCE_REINSTALL not in run.attempted_steps:
        run.state = PlaybookState.REPAIRING
        return _component_action(
            run,
            RepairStep.EDR_FORCE_REINSTALL,
            EDR_FORCE_REINSTALL_COMPONENT,
            ApprovalClass.STANDING_SAFE,
            reason="EDR remains missing, unhealthy, or out of date after maintenance.",
            verify_after=True,
        )

    if _av_needs_repair(health) and RepairStep.AV_FORCE_UPDATE not in run.attempted_steps:
        return _av_update_action(run, RepairStep.AV_FORCE_UPDATE)

    # One additional AV refresh is allowed after the approved overnight reboot.
    # If it still fails, the playbook does not loop.
    if (
        _av_needs_repair(health)
        and RepairStep.SCHEDULED_REBOOT in run.attempted_steps
        and RepairStep.POST_REBOOT_AV_FORCE_UPDATE not in run.attempted_steps
    ):
        return _av_update_action(run, RepairStep.POST_REBOOT_AV_FORCE_UPDATE)

    if health.reboot_required and RepairStep.SCHEDULED_REBOOT not in run.attempted_steps:
        return _scheduled_reboot_action(run, RepairStep.SCHEDULED_REBOOT)

    # The clean recovery branch is deliberately not standing-safe. It may be
    # offered only after bounded normal repair is exhausted.
    if _ordinary_repairs_exhausted(run, health) and RepairStep.CLEAN_UNINSTALL not in run.attempted_steps:
        run.state = PlaybookState.AWAITING_APPROVAL
        return _component_action(
            run,
            RepairStep.CLEAN_UNINSTALL,
            EDR_AV_UNINSTALL_COMPONENT,
            ApprovalClass.POLICY_GATED,
            reason=(
                "Standard EDR/AV repair paths are exhausted. Clean uninstall is the supervised overnight "
                "recovery branch and requires the configured policy authorization before execution."
            ),
            verify_after=False,
        )

    run.escalate(_escalation_summary(run, health))
    return None


def _next_recovery_action(run: PlaybookRun, health: HealthObservation) -> PlannedAction | None:
    """Continue the bounded uninstall -> reboot -> reinstall recovery branch."""

    if RepairStep.RECOVERY_REBOOT not in run.attempted_steps:
        return _scheduled_reboot_action(run, RepairStep.RECOVERY_REBOOT)

    if _edr_missing_or_broken(health) and RepairStep.RECOVERY_MAINTENANCE not in run.attempted_steps:
        run.state = PlaybookState.REPAIRING
        return _component_action(
            run,
            RepairStep.RECOVERY_MAINTENANCE,
            EDR_MAINTENANCE_COMPONENT,
            ApprovalClass.POLICY_GATED,
            reason="Restore the base EDR installation after the clean recovery reboot.",
            verify_after=True,
        )

    if _edr_missing_or_broken(health) and RepairStep.RECOVERY_FORCE_REINSTALL not in run.attempted_steps:
        run.state = PlaybookState.REPAIRING
        return _component_action(
            run,
            RepairStep.RECOVERY_FORCE_REINSTALL,
            EDR_FORCE_REINSTALL_COMPONENT,
            ApprovalClass.POLICY_GATED,
            reason="Base recovery did not return authoritative health; perform one recovery reinstall/upgrade.",
            verify_after=True,
        )

    if _av_needs_repair(health) and RepairStep.RECOVERY_AV_FORCE_UPDATE not in run.attempted_steps:
        return _av_update_action(run, RepairStep.RECOVERY_AV_FORCE_UPDATE, approval=ApprovalClass.POLICY_GATED)

    run.escalate(_escalation_summary(run, health))
    return None


def verification_action(run: PlaybookRun) -> PlannedAction:
    """Build the fresh authoritative check required after a repair or reboot."""

    if run.state in {PlaybookState.HEALTHY, PlaybookState.ESCALATION_REQUIRED}:
        raise InvalidPlaybookTransition(f"Cannot verify from terminal state {run.state.value}")
    run.state = PlaybookState.VERIFYING

    latest = run.attempt_order[-1].value if run.attempt_order else "initial"
    is_post_reboot = bool(
        run.attempt_order
        and run.attempt_order[-1] in {RepairStep.SCHEDULED_REBOOT, RepairStep.RECOVERY_REBOOT}
    )
    return PlannedAction(
        step=RepairStep.POST_REBOOT_VERIFY if is_post_reboot else RepairStep.HEALTH_CHECK,
        kind=ActionKind.COMPONENT,
        approval_class=ApprovalClass.STANDING_SAFE,
        operation=HEALTH_CHECK_COMPONENT,
        reason="Verify the endpoint with the authoritative Datto EDR/AV health component.",
        verify_after=False,
        idempotency_key=f"{run.run_id}:{run.ticket_id}:{run.device_id}:{PLAYBOOK_VERSION}:verify:{latest}",
    )


def internal_ticket_note(run: PlaybookRun) -> str:
    """Return a concise internal-only Autotask note for meaningful milestones."""

    if run.state == PlaybookState.HEALTHY:
        version = f" EDR {run.last_health.edr_version}." if run.last_health and run.last_health.edr_version else ""
        reboot = "Yes" if run.scheduled_reboot_used or run.recovery_reboot_used else "No"
        return f"{PLAYBOOK_NAME}: remediation complete. Status=Healthy.{version} Reboot required: {reboot}."

    if run.state == PlaybookState.AWAITING_SCHEDULED_REBOOT:
        return f"{PLAYBOOK_NAME}: repair pending 02:30 local reboot; automatic health verification scheduled for 03:30."

    if run.state == PlaybookState.AWAITING_APPROVAL:
        return f"{PLAYBOOK_NAME}: standard repair exhausted; policy-gated clean recovery is pending authorization."

    if run.state == PlaybookState.ESCALATION_REQUIRED:
        reasons = "; ".join(run.escalation_reasons) or "bounded repair ladder exhausted"
        return f"{PLAYBOOK_NAME}: escalation required - {reasons}"

    health = run.last_health.status if run.last_health else "Unknown"
    latest = run.attempt_order[-1].value if run.attempt_order else "initial_check"
    return f"{PLAYBOOK_NAME}: Status={health}; latest step={latest}; automated remediation in progress."


def metrics_payload(run: PlaybookRun) -> Mapping[str, Any]:
    """Small stable payload for Jason/Grafana playbook metrics."""

    return {
        "playbook": PLAYBOOK_NAME,
        "version": PLAYBOOK_VERSION,
        "state": run.state.value,
        "healthy": run.state == PlaybookState.HEALTHY,
        "escalated": run.state == PlaybookState.ESCALATION_REQUIRED,
        "attempt_count": len(run.attempt_order),
        "scheduled_reboot_used": run.scheduled_reboot_used,
        "recovery_reboot_used": run.recovery_reboot_used,
        "clean_recovery_used": RepairStep.CLEAN_UNINSTALL in run.attempted_steps,
    }


def escalation_payload(run: PlaybookRun) -> Mapping[str, Any]:
    """Evidence-oriented escalation handoff without embedding secrets."""

    health = run.last_health
    return {
        "playbook": PLAYBOOK_NAME,
        "version": PLAYBOOK_VERSION,
        "ticket_id": run.ticket_id,
        "device_id": run.device_id,
        "organization_id": run.organization_id,
        "provider_job_ids": tuple(run.provider_job_ids),
        "attempted_steps": tuple(step.value for step in run.attempt_order),
        "evidence_refs": tuple(run.evidence_refs),
        "edr_version": health.edr_version if health else None,
        "hunt_agent_path": health.hunt_agent_path if health else None,
        "hunt_agent_running": health.hunt_agent_running if health else None,
        "av_present": health.av_present if health else None,
        "av_healthy": health.av_healthy if health else None,
        "endpoint_protection_service_running": health.endpoint_protection_service_running if health else None,
        "security_center_healthy": health.security_center_healthy if health else None,
        "reasons": tuple(run.escalation_reasons),
    }


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


def _av_update_action(
    run: PlaybookRun,
    step: RepairStep,
    *,
    approval: ApprovalClass = ApprovalClass.STANDING_SAFE,
) -> PlannedAction:
    run.state = PlaybookState.REPAIRING
    return PlannedAction(
        step=step,
        kind=ActionKind.PREDEFINED_COMMAND,
        approval_class=approval,
        operation=AV_FORCE_UPDATE_COMMAND,
        reason="Datto AV is missing, stale, or unhealthy; request one governed AV refresh/update.",
        verify_after=True,
        idempotency_key=run.idempotency_key(step),
    )


def _scheduled_reboot_action(run: PlaybookRun, step: RepairStep) -> PlannedAction:
    run.state = PlaybookState.AWAITING_SCHEDULED_REBOOT
    return PlannedAction(
        step=step,
        kind=ActionKind.SCHEDULED_REBOOT,
        approval_class=(
            ApprovalClass.STANDING_SAFE if step == RepairStep.SCHEDULED_REBOOT else ApprovalClass.POLICY_GATED
        ),
        operation=SCHEDULED_REBOOT_COMPONENT,
        reason="Schedule the playbook's bounded 02:30 local reboot and resume verification at 03:30 local.",
        verify_after=True,
        idempotency_key=run.idempotency_key(step),
        schedule_local="02:30",
        resume_local="03:30",
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
    if run.scheduled_reboot_used and needs_av:
        av_done = av_done and RepairStep.POST_REBOOT_AV_FORCE_UPDATE in run.attempted_steps
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
