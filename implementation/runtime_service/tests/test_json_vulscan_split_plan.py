"""Exact same-client bounded multi-device split plan, no external writes."""
import pytest
from jason_runtime.json_vulscan_split_plan import (
    JsonVulscanSplitBoundaryError, plan_json_vulscan_split,
)
from jason_runtime.ticket_split_runtime import TicketSplitExecutor

TICKET={
    "id":123,"companyID":208,"ticketNumber":"T20261119.0001",
    "title":"Vulnerability detected by VulScan - KB5129195",
    "description":(
        "Missing KB5129195\nAffected Nodes:\n"
        "Discovery Agent PC-A (vulnerable)\n"
        "Discovery Agent PC-B (vulnerable)\n"),
    "priority":1,"issueType":23,"subIssueType":497,"ticketType":3,
}


def ci(node,id,uid,*,company=208):
    return {"status":"succeeded","evidence":{"data":{"items":[{
        "id":id,"isActive":True,"companyID":company,
        "referenceTitle":node,"referenceNumber":uid,
    }]}}}


def endpoint(node,uid,*,company=208):
    return {"status":"succeeded","evidence":{"record":{
        "resource_id":uid,"hostname":node,"companyID":company,
    }}}


def plan(*,ticket=TICKET,ci_by=None,devices=None,**overrides):
    params={
        "source_ticket":ticket,"exact_client_id":"208",
        "ci_search_by_hostname":ci_by or {
            "PC-A":ci("PC-A",10,"uid-a"),
            "PC-B":ci("PC-B",11,"uid-b"),
        },
        "endpoint_read_by_uid":devices or {
            "uid-a":endpoint("PC-A","uid-a"),
            "uid-b":endpoint("PC-B","uid-b"),
        },
    }
    params.update(overrides)
    return plan_json_vulscan_split(**params)


def test_legacy_two_node_source_parses_exact_split_payload_without_write():
    result=plan()
    assert [x.target_key for x in result.targets]==["uid-a","uid-b"]
    assert result.company_id==208
    assert result.source_ticket_id==123
    assert result.queue_id=="Jason"
    assert result.status=="New"
    assert result.targets[0].configuration_item_id==10
    assert "Original VulScan finding:" in result.targets[1].description
    assert TicketSplitExecutor.marker(
        result.source_ticket_number, result.targets[0].target_key
    ).startswith("JASON-SPLIT:T20261119.0001:")


@pytest.mark.parametrize("override",[
    {"exact_client_id":"999"},
    {"ticket":{**TICKET,"companyID":0}},
    {"ticket":{**TICKET,"description":"No nodes"}},
    {"ticket":{**TICKET,"description":
               "Affected Nodes: PC-A (risk) PC-A (same) PC-B (risk)"}},
])
def test_missing_or_duplicate_client_source_fails_closed(override):
    with pytest.raises(JsonVulscanSplitBoundaryError):
        plan(**override)


def test_wrong_company_ci_fails_closed():
    with pytest.raises(JsonVulscanSplitBoundaryError,match="CI_NOT_UNIQUE"):
        plan(ci_by={"PC-A":ci("PC-A",10,"uid-a",company=999),
                    "PC-B":ci("PC-B",11,"uid-b")})


def test_wrong_endpoint_identity_fails_closed():
    with pytest.raises(JsonVulscanSplitBoundaryError,match="ENDPOINT_SCOPE_MISMATCH"):
        plan(devices={"uid-a":endpoint("OTHER","uid-a"),
                      "uid-b":endpoint("PC-B","uid-b")})


def test_duplicate_datto_uid_is_rejected_even_with_unique_ci():
    with pytest.raises(JsonVulscanSplitBoundaryError,match="TARGET_COLLISION"):
        plan(ci_by={"PC-A":ci("PC-A",10,"uid-same"),
                    "PC-B":ci("PC-B",11,"uid-same")},
             devices={"uid-same":endpoint("PC-A","uid-same")})


def test_incomplete_ci_page_rejected_before_any_child_proposal():
    source=ci("PC-A",10,"uid-a")
    source["evidence"]["data"]["has_more"]=True
    with pytest.raises(JsonVulscanSplitBoundaryError,match="CI_PAGE_INCOMPLETE"):
        plan(ci_by={"PC-A":source,"PC-B":ci("PC-B",11,"uid-b")})


def test_json_split_source_requires_independent_target_grant_and_all_children():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    doc=validate_playbook_document(json.loads(
        (Path(__file__).resolve().parents[3] /
         "docs/playbooks/json/migration/candidates/vulscan_multi_device_split.v1.json").read_text()))
    j=JsonPlaybookInterpreter(doc)
    assert j.instruction(step_id="source_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="target_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="split_ledger_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="all_children_gate",facts={}).step_id=="human_review"
    assert j.instruction(step_id="source_completion_gate",facts={}).step_id=="human_review"
    for id,cap,arg in [
        ("create_child","service.ticket.create","trusted_exact_next_child_create_arguments"),
        ("create_lineage_note","service.ticket.note.create","trusted_exact_source_split_note_arguments"),
        ("complete_source","service.ticket.update","trusted_exact_source_completion_arguments"),
    ]:
        step=j.instruction(step_id=id,facts={arg:{"payload":{"id":123}}})
        assert step.capability==cap
        assert step.approval_required is True
        assert step.approval_classification=="modifying"
