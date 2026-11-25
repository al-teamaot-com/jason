"""VulScan real source pure KB/non-KB and ten-day approval wait tests."""
from datetime import datetime, timedelta, timezone
import pytest
from jason_runtime.json_vulscan_patch_classifier import (
    JsonVulscanPatchBoundaryError, classify_vulscan_readonly,
)
from jason_runtime.vulscan_non_kb import analyze_non_kb_vulscan,render_non_kb_assessment

NOW=datetime(2026,11,19,16,tzinfo=timezone.utc)
DEVICE={"resource_id":"uid-1","companyID":"777",
        "reboot_required":False}


def assess(*,status="Approved",approved=True,
           installed=False,superseded=False,**changes):
    args={
        "ticket_id":123,"company_id":777,"device_uid":"uid-1",
        "endpoint":DEVICE,"target_kb":"KB5129195",
        "patch_inventory":[{
            "kb":"KB5129195","status":status,"approved":approved,
            "installed":installed,"superseded":superseded,
        }],
        "source_text":"Missing KB5129195",
        "installed_software":[],
        "approved_patch_window_complete":True,
        "first_not_approved_at":None,
        "observed_at":NOW,
    }
    args.update(changes)
    return classify_vulscan_readonly(**args)


@pytest.mark.parametrize("states,expected",[
    ({"installed":True},"verified_installed_or_superseded"),
    ({"superseded":True},"verified_installed_or_superseded"),
    ({"approved":False},"waiting_patch_approval"),
    ({"approved_patch_window_complete":False},"waiting_approved_patch_window"),
    ({"status":"InstallError"},"install_failure_human_review"),
])
def test_exact_kb_status_is_source_classified_without_patch_execution(states,expected):
    result=assess(**states)
    assert result.disposition==expected
    assert result.exact_kb=="KB5129195"
    assert not result.patch_execution_authorized
    assert not result.client_notification_required


def test_unapproved_patch_after_ten_days_human_review():
    assert assess(
        approved=False,
        first_not_approved_at=NOW-timedelta(days=10)
    ).disposition=="unapproved_patch_aged_human_review"
    assert assess(
        approved=False,
        first_not_approved_at=NOW-timedelta(days=9)
    ).disposition=="waiting_patch_approval"


def test_reboot_is_separate_exact_owner_approval():
    result=assess(endpoint={**DEVICE,"reboot_required":True})
    assert result.disposition=="reboot_required_exact_approval_human_review"
    assert not result.patch_execution_authorized


@pytest.mark.parametrize("text",[
    "OpenSSL CVE-2026-12345 upgrade required",
    "EOL third-party software version",
    "TLS certificate misconfiguration",
    "SMBv1 protocol enabled",
])
def test_non_kb_uses_existing_pure_source_research_classifier(text):
    source=analyze_non_kb_vulscan(text,[])
    result=assess(target_kb=None,patch_inventory=[],
                  source_text=text)
    assert result.disposition=="non_kb_"+source.classification
    assert result.source_evidence==render_non_kb_assessment(source)
    assert not result.patch_execution_authorized


@pytest.mark.parametrize("change",[
    {"device_uid":"different"},
    {"company_id":666},
    {"endpoint":{**DEVICE,"companyID":"other"}},
    {"target_kb":"KBinvalid"},
    {"patch_inventory":[]},
    {"patch_inventory":[{"kb":"KB5129195"}]*2},
    {"first_not_approved_at":NOW+timedelta(days=1),
     "patch_inventory":[{"kb":"KB5129195","approved":False}]},
])
def test_missing_or_ambiguous_patch_identity_denied(change):
    with pytest.raises(JsonVulscanPatchBoundaryError):
        assess(**change)


def test_vulscan_json_has_no_patch_execute_and_fails_closed():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc=validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3]/
         "docs/playbooks/json/migration/candidates/vulscan_missing_patch.v1.json").read_text()))
    j=JsonPlaybookInterpreter(doc)
    assert "automation.component.execute" not in doc.capabilities
    assert j.instruction(step_id="ticket_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="classification_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="classification_gate",facts={
        "verified_vulscan_disposition":"waiting_patch_approval",
    }).step_id=="wait_approval"
    assert j.instruction(step_id="classification_gate",facts={
        "verified_vulscan_disposition":"install_failure_human_review",
    }).step_id=="human_review"
    assert j.instruction(step_id="note_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="policy_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="complete_gate",facts={}).step_id=="human_review"
    for step,cap in (
        ("create_note","service.ticket.note.create"),
        ("client_note","service.ticket.client.notification.create"),
        ("complete_ticket","service.ticket.update"),
    ):
        argument_name = {
            "create_note": "trusted_exact_update_evidence_note_arguments",
            "client_note": "trusted_exact_approved_vulscan_client_template_arguments",
            "complete_ticket": "trusted_exact_source_policy_ticket_status_arguments",
        }[step]
        instruction=j.instruction(
            step_id=step, facts={
                argument_name: {"payload": {"id": 123, "ticketID": 123}},
            })
        assert instruction.capability==cap
        assert instruction.approval_required
        assert instruction.approval_classification=="modifying"
