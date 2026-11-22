"""Exact Python 1.3.0 EDR/AV planner reuse; no production execution."""
import pytest

from autonomous_remediation.datto_edr_av_playbook import (
    HealthObservation, PlaybookRun, PlaybookState,
    RepairStep, next_action,
)
from jason_runtime.json_edr_av_planner import (
    JsonEdrAvBoundaryError, project_edr_av_source_action,
)


def run():
    return PlaybookRun(
        run_id="synthetic-run",ticket_id="T-SYNTHETIC",
        device_id="synthetic-device",organization_id="synthetic-org",
        client_id="synthetic-client",
    )


def project(r=None,health=None,**changed):
    r=r or run()
    params={
        "run":r, "expected_run_id":"synthetic-run",
        "expected_client_id":"synthetic-client",
        "expected_ticket_id":"T-SYNTHETIC",
        "expected_device_id":"synthetic-device",
        "health":health,
    }
    params.update(changed)
    return project_edr_av_source_action(**params)


def test_exact_initial_health_component_and_source_key():
    r=run()
    got=project(r)
    assert got.disposition=="approved_component_candidate"
    assert got.step==RepairStep.HEALTH_CHECK.value
    assert got.capability=="automation.component.execute"
    assert got.idempotency_key==r.idempotency_key(RepairStep.HEALTH_CHECK)
    assert not got.provider_execution_authorized


def test_unhealthy_edr_maintenance_uses_deployed_next_action():
    r=run()
    health=HealthObservation(status="Unhealthy",hunt_agent_installed=False,
                             av_present=True,av_healthy=True)
    got=project(r,health)
    assert got.step==RepairStep.EDR_MAINTENANCE.value
    assert got.disposition=="approved_component_candidate"
    assert got.verify_after is True


def test_healthy_security_product_without_threat_resolves_no_mutation():
    got=project(run(),HealthObservation(status="Healthy"))
    assert got.disposition=="source_health_and_security_verified"
    assert got.capability is None


def test_unreachable_or_tamper_health_escalates():
    for health in (
        HealthObservation(status="Unhealthy",endpoint_reachable=False),
        HealthObservation(status="Unhealthy",tamper_or_registration_blocked=True),
    ):
        got=project(run(),health)
        assert got.disposition=="human_review" or (
            got.disposition=="awaiting_evidence_or_human_review")
        assert got.capability is None


def test_av_predefined_command_is_not_given_unapproved_provider_transport():
    got=project(run(),HealthObservation(
        status="Unhealthy",hunt_agent_installed=True,
        hunt_agent_running=True,edr_current=True,av_present=False))
    assert got.step==RepairStep.AV_FORCE_UPDATE.value
    assert got.disposition=="predefined_command_requires_separate_governed_source_capability"
    assert got.capability is None


def test_scheduled_reboot_is_disruptive_and_never_autorun():
    r=run()
    r.force_update_pending_reboot=True
    got=project(r,HealthObservation(status="Unhealthy"))
    assert got.step==RepairStep.SCHEDULED_REBOOT.value
    assert got.capability is None
    assert got.disposition=="disruptive_reboot_exact_owner_approval_required"
    assert not got.provider_execution_authorized


@pytest.mark.parametrize("changed",[
    {"expected_client_id":"other"},
    {"expected_device_id":"other"},
    {"expected_ticket_id":"other"},
    {"expected_run_id":"other"},
])
def test_cross_run_identity_denied(changed):
    with pytest.raises(JsonEdrAvBoundaryError,match="EXACT_RUN"):
        project(**changed)


def test_started_step_is_idempotently_not_replanned_without_readback():
    r=run()
    r.attempted_steps.add(RepairStep.EDR_MAINTENANCE)
    got=project(r,HealthObservation(status="Unhealthy",
                                   hunt_agent_installed=False))
    assert got.step==RepairStep.EDR_FORCE_REINSTALL.value
    assert not got.provider_execution_authorized


def test_edr_json_source_gate_rejects_missing_authority_or_disruptive_plan():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc=validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3]/
         "docs/playbooks/json/migration/candidates/datto_edr_av.v1.json").read_text()))
    j=JsonPlaybookInterpreter(doc)
    assert j.instruction(step_id="identity_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="classify",facts={}).step_id=="human_review"
    assert j.instruction(step_id="component_grant_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="classify",facts={
        "source_planned_disposition":"disruptive_reboot_exact_owner_approval_required"
    }).step_id=="human_review"
    assert j.instruction(step_id="classify",facts={
        "source_planned_disposition":"policy_gated_component_candidate"
    }).step_id=="human_review"
    intent=j.instruction(step_id="classify",facts={
        "source_planned_disposition":"approved_component_candidate",
        "exact_standing_safe_component_identity_and_owner_promotion":True,
        "trusted_exact_component_dispatch_arguments":{
            "device_uid":"synthetic-device","component_uid":"synthetic-component",
        },
    })
    assert intent.step_id=="run_component"
    assert intent.capability=="automation.component.execute"
    assert intent.approval_required
    assert intent.approval_classification=="modifying"
