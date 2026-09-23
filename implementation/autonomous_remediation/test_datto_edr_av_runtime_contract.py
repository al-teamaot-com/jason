import pytest

from .datto_edr_av_playbook import (
    AV_FORCE_UPDATE_COMMAND,
    ActionKind,
    ApprovalClass,
    HealthObservation,
    PlannedAction,
    PlaybookRun,
    RepairStep,
)
from .datto_edr_av_runtime_contract import (
    AUTOMATION_COMPONENT_EXECUTE,
    AUTOMATION_JOB_OUTPUT_READ,
    AUTOMATION_JOB_READ,
    DATTO_AV_FORCE_UPDATE_POWERSHELL,
    RUN_AD_HOC_POWERSHELL_COMPONENT,
    RUN_AD_HOC_POWERSHELL_UID,
    RuntimeBindingError,
    VERIFIED_COMPONENTS,
    bind_execution,
    bind_job_output_read,
    bind_job_read,
    bind_playbook_internal_note,
    bind_ticket_work_handoff,
    bind_ticket_work_start,
)


def action(operation: str, *, kind: ActionKind = ActionKind.COMPONENT) -> PlannedAction:
    return PlannedAction(
        step=RepairStep.HEALTH_CHECK,
        kind=kind,
        approval_class=ApprovalClass.STANDING_SAFE,
        operation=operation,
        idempotency_key="run:T1:device:1.1.0:health_check",
    )


def test_verified_health_component_binds_to_governed_execution():
    name = "Check Datto EDR/AV Status AOT Ver 12122025-1"
    request = bind_execution(action(name), device_uid="device-1")
    assert request.capability == AUTOMATION_COMPONENT_EXECUTE
    assert request.arguments["device_uid"] == "device-1"
    assert request.arguments["component_uid"] == VERIFIED_COMPONENTS[name].uid
    assert request.arguments["component_name"] == name
    assert request.arguments["idempotency_key"]


def test_all_provider_components_have_exact_uid_and_name():
    assert len(VERIFIED_COMPONENTS) == 7
    for identity in VERIFIED_COMPONENTS.values():
        assert identity.uid
        assert identity.name
        assert "*" not in identity.uid
        assert "*" not in identity.name


def test_unknown_component_fails_closed():
    with pytest.raises(RuntimeBindingError):
        bind_execution(action("Some Other Component"), device_uid="device-1")


def test_datto_av_force_update_uses_exact_ad_hoc_powershell_component():
    request = bind_execution(
        action(AV_FORCE_UPDATE_COMMAND, kind=ActionKind.PREDEFINED_COMMAND),
        device_uid="device-1",
    )
    assert request.capability == AUTOMATION_COMPONENT_EXECUTE
    assert request.arguments["component_uid"] == RUN_AD_HOC_POWERSHELL_UID
    assert request.arguments["component_name"] == RUN_AD_HOC_POWERSHELL_COMPONENT
    assert request.arguments["variables"] == {"Command": DATTO_AV_FORCE_UPDATE_POWERSHELL}
    assert "datto-av" in request.arguments["variables"]["Command"]
    assert "--force-update" in request.arguments["variables"]["Command"]


def test_arbitrary_predefined_command_still_fails_closed():
    with pytest.raises(RuntimeBindingError, match="unapproved predefined command"):
        bind_execution(
            action("Write-Output arbitrary", kind=ActionKind.PREDEFINED_COMMAND),
            device_uid="device-1",
        )


def test_exact_device_uid_is_required():
    name = "Check Datto EDR/AV Status AOT Ver 12122025-1"
    with pytest.raises(RuntimeBindingError):
        bind_execution(action(name), device_uid="")


def test_job_status_read_uses_live_governed_read_capability():
    request = bind_job_read("job-1")
    assert request.capability == AUTOMATION_JOB_READ
    assert request.arguments == {"resource_id": "job-1"}


def test_job_output_read_is_bound_to_job_device_component_and_stream():
    request = bind_job_output_read(
        "job-1",
        device_uid="device-1",
        component_uid="component-1",
        stream="stdout",
    )
    assert request.capability == AUTOMATION_JOB_OUTPUT_READ
    assert request.arguments["resource_id"] == "job-1"
    assert request.arguments["device_uid"] == "device-1"
    assert request.arguments["component_uid"] == "component-1"
    assert request.arguments["stream"] == "stdout"


def test_playbook_state_generates_governed_internal_note_request():
    run = PlaybookRun(
        run_id="run-1",
        ticket_id="T20260918.0005",
        device_id="AOT-50282",
        organization_id="ORG1",
        client_id="CLIENT1",
    )
    run.record_health(HealthObservation(status="Healthy", edr_version="3.17.1.6224"))

    request = bind_playbook_internal_note(run, ticket_id=140629)

    assert request.capability == "service.ticket.note.create"
    assert request.arguments["ticket_id"] == 140629
    assert request.arguments["title"].startswith("Jason - Datto EDR/AV")
    assert "Status=Healthy" in request.arguments["note"]


def test_ticket_work_start_uses_standing_lifecycle_binding():
    request = bind_ticket_work_start(
        140629,
        device_online=True,
        device_name="AOT-50282",
        issue_type="Endpoint Security",
        sub_issue_type="Antivirus",
    )

    assert request.capability == "service.ticket.update"
    assert request.arguments == {
        "ticket_id": 140629,
        "begin_work": True,
        "device_online": True,
        "work_kind": "diagnostic",
        "device_name": "AOT-50282",
        "issue_type": "Endpoint Security",
        "sub_issue_type": "Antivirus",
    }


def test_ticket_work_start_omits_blank_classification_hints():
    request = bind_ticket_work_start(
        123,
        device_online=True,
        issue_type="  ",
    )
    assert request.arguments == {
        "ticket_id": 123,
        "begin_work": True,
        "device_online": True,
        "work_kind": "diagnostic",
    }


def test_ticket_work_start_rejects_offline_device():
    with pytest.raises(RuntimeBindingError, match="online"):
        bind_ticket_work_start(123, device_online=False)


def test_ticket_work_handoff_uses_reason_and_blocker_fingerprint():
    request = bind_ticket_work_handoff(
        123,
        reason_class="human_intervention_required",
        blocker_fingerprint="needs-onsite-usb",
    )
    assert request.capability == "service.ticket.update"
    assert request.arguments == {
        "ticket_id": 123,
        "return_work": True,
        "handoff_reason_class": "human_intervention_required",
        "blocker_fingerprint": "needs-onsite-usb",
    }

def test_threat_branch_binds_live_scan_start_and_verification_reads():
    from .datto_edr_av_runtime_contract import (
        bind_security_detection_search,
        bind_security_scan_history,
        bind_security_scan_start,
        bind_security_status_read,
    )
    scan = bind_security_scan_start(device_uid="device-1", agent_id="agent-1", scan_type="FULL")
    assert scan.capability == "endpoint.security.scan.start"
    assert scan.arguments == {"resource_id": "device-1", "agent_id": "agent-1", "scan_type": "full"}
    assert bind_security_status_read(device_uid="device-1").capability == "endpoint.security.status.read"
    assert bind_security_detection_search(agent_id="agent-1").capability == "endpoint.security.detection.search"
    assert bind_security_scan_history(agent_id="agent-1").capability == "endpoint.security.scan.history.search"


def test_threat_branch_scan_binding_fails_closed_on_ambiguous_inputs():
    from .datto_edr_av_runtime_contract import bind_security_scan_start
    with pytest.raises(RuntimeBindingError):
        bind_security_scan_start(device_uid="", agent_id="agent-1", scan_type="quick")
    with pytest.raises(RuntimeBindingError):
        bind_security_scan_start(device_uid="device-1", agent_id="agent-1", scan_type="custom")
