"""Conservative live-legacy hardware diagnostic parity, no alert resolution."""
import pytest
from jason_runtime.json_hardware_triage import (
    JsonHardwareTriageError, classify_hardware_triage,
)

ENDPOINT={
    "resource_id":"dev-1","companyID":"777","hostname":"TEST-PC",
    "online":True,"device_type":{"category":"Desktop"},
}
POST={
    "alertUid":"post-1","ticketNumber":"T-POST-1","timestamp":100,
    "alertSourceInfo":{"deviceUid":"dev-1"},
    "alertContext":{"description":"Power-On-Self-Test errors occurred"},
}
DISK={
    "alertUid":"disk-1","ticketNumber":"T-DISK-1","timestamp":100,
    "alertSourceInfo":{"deviceUid":"dev-1"},
    "alertContext":{"code":"7","description":"The device, \\Device\\Harddisk1\\DR1, has a bad block."},
}
AUDIT={"attachedDevices":[{"Device":"USB SD Card Reader"}],
       "logicalDisks":[{"Drive":"C"}]}


def run(playbook, **kw):
    values={
        "playbook":playbook, "client_id":"777",
        "device_uid":"dev-1","device_hostname":"TEST-PC",
        "ticket_number":"T-POST-1" if playbook=="post_error_investigation" else "T-DISK-1",
        "endpoint":ENDPOINT,
        "alerts":[POST] if playbook=="post_error_investigation" else [DISK],
        "audit":AUDIT,
    }
    values.update(kw)
    return classify_hardware_triage(**values)


def test_current_post_baseline_diagnostic_not_auto_close():
    result=run("post_error_investigation")
    assert result.disposition=="isolated_post_diagnostic_only_human_review"
    assert result.source_alert_uid=="post-1"
    assert result.autonomous_alert_resolution_allowed is False


def test_protected_and_recurring_post_go_to_review():
    assert run("post_error_investigation",endpoint={
        **ENDPOINT,"device_type":{"category":"Server"}}).disposition == "protected_role_human_review"
    assert run("post_error_investigation",alerts=[POST,{
        **POST,"alertUid":"post-2","ticketNumber":"T-POST-2"
    }]).disposition=="recurring_post_human_review"


def test_disk_number_and_usb_hint_never_imply_physical_removable_mapping():
    result=run("disk_bad_block_event_7")
    assert result.disposition=="physical_disk_mapping_human_review"
    assert result.disk_number=="1"
    assert result.removable_hint_count==1
    assert not result.autonomous_alert_resolution_allowed
    assert not result.autonomous_hardware_mutation_allowed


def test_absent_mapping_cannot_autoclose_alert():
    result=run("disk_bad_block_event_7",audit={
        "attachedDevices":[],"logicalDisks":[]})
    assert result.disposition=="physical_disk_mapping_human_review"
    assert result.removable_hint_count==0


@pytest.mark.parametrize("change",[
    {"client_id":"other"},
    {"device_uid":"other"},
    {"device_hostname":"WRONG"},
    {"endpoint":{**ENDPOINT,"companyID":"other"}},
    {"alerts":[{**POST,"alertSourceInfo":{"deviceUid":"foreign"}}]},
    {"alerts":[{**POST,"alertUid":""}]},
])
def test_post_identity_fail_closed(change):
    with pytest.raises(JsonHardwareTriageError):
        run("post_error_investigation",**change)


def test_offline_no_expensive_diag_and_no_mutation():
    result=run("disk_bad_block_event_7",endpoint={
        **ENDPOINT,"online":False})
    assert result.disposition=="waiting_device_access"
    assert not result.autonomous_alert_resolution_allowed


def test_missing_audit_blocks_untrusted_disk_mapping():
    with pytest.raises(JsonHardwareTriageError,match="AUDIT_MISSING"):
        run("disk_bad_block_event_7",audit=None)


def test_no_matching_post_alert_escalates():
    result=run("post_error_investigation",alerts=[{
        **POST,"alertContext":{"description":"Unrelated Windows warning"}}])
    assert result.disposition=="no_authoritative_matching_alert_human_review"


@pytest.mark.parametrize("playbook", [
    "disk_bad_block_event_7", "post_error_investigation",
])
def test_source_json_hardware_actions_are_internal_notes_and_handoff_only(playbook):
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc = validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3] /
         f"docs/playbooks/json/migration/candidates/{playbook}.v1.json").read_text()))
    runner = JsonPlaybookInterpreter(doc)
    assert "endpoint.alert.resolve" not in doc.capabilities
    assert runner.instruction(step_id="ticket_gate", facts={}).step_id == "human_review"
    assert runner.instruction(step_id="classification_gate", facts={}).step_id == "human_review"
    for gate, fact, operation, action in (
        ("note_gate", "exact_approved_note_and_same_ticket_intent",
         "service.ticket.note.create", "create_note"),
        ("handoff_gate", "exact_owner_promotion_to_helpdesk_human_review",
         "service.ticket.update", "handoff_ticket"),
    ):
        assert runner.instruction(step_id=gate, facts={}).step_id == "human_review"
        intent=runner.instruction(step_id=gate, facts={fact:True,
           ("trusted_exact_internal_note_create_args" if action=="create_note"
            else "trusted_exact_helpdesk_human_review_args"): {
                "payload": {"id": 123, "status": "Human Review"}},
        })
        assert intent.step_id == action
        assert intent.capability == operation
        assert intent.approval_required
        assert intent.approval_classification == "modifying"
    assert runner.instruction(step_id="ticket_readback_gate", facts={}).step_id == "human_review"
