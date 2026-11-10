"""Host consumer V5 signed receipt readback is bounded and nonauthorizing."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json

import pytest

from connectors.src.jason_connectors.approval_requests import ApprovalRequestStatus
from jason_mcp.entra_release_browser_decision import _canonical
from tools.tests.test_verify_browser_release_evidence import environment
from tools.v5_browser_release_host_consumer import verify_v5_browser_release_receipt


def fixture(tmp_path):
    state=environment(tmp_path)
    evidence=state["envelope"]
    digest=sha256(_canonical(evidence)).hexdigest()
    request=replace(state["request"], status=ApprovalRequestStatus.APPROVED)
    response={
        "approval_id":state["exact_release"].approval_id,
        "organization_id":state["organization_id"],
        "approver_identity_id":state["owner_identity_ids"][0],
        "decision":"approve",
        "decided_at":state["now"].isoformat(),
        "channel":"entra_browser_admin",
        "channel_response_id":digest,
        "authentication_evidence_hash":digest,
    }
    kwargs={
        "request":request, "response":response,"envelope":evidence,
        "evidence_sha256":digest,"exact_release":state["exact_release"],
        "route":state["route"],"policy_version":"5.0",
        "policy_sha256":state["policy_sha256"],
        "organization_id":state["organization_id"],
        "owner_identity_ids":state["owner_identity_ids"],
        "root_trust_path":state["root_trust_path"],"now":state["now"],
    }
    return kwargs


def test_host_native_receipt_verified_without_release_authority(tmp_path):
    values=fixture(tmp_path)
    result=verify_v5_browser_release_receipt(**values)
    assert result["status"]=="host_signed_browser_receipt_verified"
    assert result["release_authorized"] is False
    assert result["ccc_attested"] is False
    assert result["production_changed"] is False
    assert result["candidate_sha"]==values["exact_release"].candidate_sha


@pytest.mark.parametrize("attribute,bad",[
    ("policy_version","4.0"),("policy_version","5"),("policy_sha256","0"*64),
    ("organization_id","other"),("owner_identity_ids",("regular-user",)),
    ("evidence_sha256","0"*64),
])
def test_host_rejects_unreviewed_policy_identity_or_hash(tmp_path,attribute,bad):
    args=fixture(tmp_path);args[attribute]=bad
    with pytest.raises(PermissionError):
        verify_v5_browser_release_receipt(**args)


@pytest.mark.parametrize("field,bad",[
    ("approval_id","relapproval-"+"f"*32),("decision","deny"),
    ("channel","microsoft_teams"),("channel","ordinary_message"),
    ("organization_id","different-org"),
    ("approver_identity_id","regular-licensed-user"),
    ("authentication_evidence_hash","0"*64),
    ("channel_response_id","0"*64),
    ("decided_at","2025-01-01T00:00:00+00:00"),
])
def test_host_rejects_forged_or_teams_receipt(tmp_path,field,bad):
    args=fixture(tmp_path)
    args["response"][field]=bad
    with pytest.raises(PermissionError):
        verify_v5_browser_release_receipt(**args)


def test_host_rejects_pending_or_denied_ledger_status(tmp_path):
    args=fixture(tmp_path)
    args["request"]=replace(args["request"],status=ApprovalRequestStatus.PENDING)
    with pytest.raises(PermissionError):
        verify_v5_browser_release_receipt(**args)


def test_host_rejects_changed_release_after_signature(tmp_path):
    args=fixture(tmp_path)
    args["exact_release"]=replace(args["exact_release"],rollback_sha="0"*40)
    with pytest.raises(PermissionError):
        verify_v5_browser_release_receipt(**args)


def test_host_rejects_tampered_envelope_and_does_not_create_grant(tmp_path):
    args=fixture(tmp_path)
    args["envelope"]=json.loads(json.dumps(args["envelope"]))
    args["envelope"]["payload"]["decision"]="deny"
    with pytest.raises(PermissionError):
        verify_v5_browser_release_receipt(**args)


def test_host_rejects_missing_root_trust(tmp_path):
    args=fixture(tmp_path)
    args["root_trust_path"]=tmp_path/"missing-review.json"
    with pytest.raises(PermissionError):
        verify_v5_browser_release_receipt(**args)
