"""Pure Datto EDR/AV JSON source plan using the original Python state machine.

This retains the canonical deployed 1.3.0 source as deterministic capability
logic, but returns an isolated planning classification only. All potentially
disruptive plans fail closed and no provider execution authority is created.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from autonomous_remediation.datto_edr_av_playbook import (
    ActionKind, ApprovalClass, HealthObservation, PlaybookRun,
    PlaybookState, next_action,
)


class JsonEdrAvBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonEdrAvIntent:
    disposition: str
    step: str | None
    capability: str | None
    operation: str | None
    idempotency_key: str | None
    approval_class: str | None
    verify_after: bool
    prior_attempted_step_count: int
    source_state: str
    provider_execution_authorized: bool = False


def project_edr_av_source_action(
    *,
    run: PlaybookRun,
    expected_run_id: str,
    expected_client_id: str,
    expected_ticket_id: str,
    expected_device_id: str,
    health: HealthObservation | None,
) -> JsonEdrAvIntent:
    if (not expected_run_id or not expected_client_id or
        not expected_ticket_id or not expected_device_id or
        run.run_id != expected_run_id or
        run.client_id != expected_client_id or
        run.ticket_id != expected_ticket_id or
        run.device_id != expected_device_id):
        raise JsonEdrAvBoundaryError("EDR_EXACT_RUN_CLIENT_DEVICE_CHANGED")
    if run.state in (PlaybookState.ESCALATION_REQUIRED,
                     PlaybookState.FALSE_POSITIVE_REVIEW):
        return JsonEdrAvIntent(
            "human_review",None,None,None,None,None,False,
            len(run.attempted_steps),run.state.value)
    action = next_action(run, health)
    if action is None:
        disposition = (
            "source_health_and_security_verified"
            if run.completion_ready else
            "awaiting_evidence_or_human_review"
        )
        return JsonEdrAvIntent(
            disposition,None,None,None,None,None,False,
            len(run.attempted_steps),run.state.value)
    if (not action.idempotency_key or
        action.idempotency_key in run.completed_job_keys or
        action.step in run.attempted_steps):
        raise JsonEdrAvBoundaryError("EDR_ACTION_ALREADY_CLAIMED")
    if action.kind == ActionKind.SCHEDULED_REBOOT:
        return JsonEdrAvIntent(
            "disruptive_reboot_exact_owner_approval_required",
            action.step.value,None,action.operation,
            action.idempotency_key,action.approval_class.value,
            True,len(run.attempted_steps),run.state.value)
    if action.kind != ActionKind.COMPONENT:
        return JsonEdrAvIntent(
            "predefined_command_requires_separate_governed_source_capability",
            action.step.value,None,action.operation,
            action.idempotency_key,action.approval_class.value,
            action.verify_after,len(run.attempted_steps),run.state.value)
    return JsonEdrAvIntent(
        ("approved_component_candidate" if
         action.approval_class == ApprovalClass.STANDING_SAFE else
         "policy_gated_component_candidate"),
        action.step.value, "automation.component.execute",
        action.operation,action.idempotency_key,
        action.approval_class.value, action.verify_after,
        len(run.attempted_steps),run.state.value)
