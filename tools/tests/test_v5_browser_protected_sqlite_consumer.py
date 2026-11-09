"""Read-only protected release consumer verifies native V5 SQLite evidence."""
from dataclasses import replace
from hashlib import sha256

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision, ApprovalRequestService, ApprovalResponse,
    SQLiteApprovalRequestRepository,
)
from jason_mcp.entra_release_browser_decision import _canonical
from jason_runtime.mobile_release_approval import MobileReleaseSignedEvidenceStore
from tools.release_mobile_approval_consumer import verify_protected_v5_browser_ledger
from tools.tests.test_verify_browser_release_evidence import environment


class Authority:
    def can_approve(self,**kwargs):return True


def fixture(tmp_path):
    state=environment(tmp_path)
    path=tmp_path/"native-approvals.sqlite3"
    repo=SQLiteApprovalRequestRepository(path)
    repo.put(state["request"])
    signed=MobileReleaseSignedEvidenceStore(path)
    digest=sha256(_canonical(state["envelope"])).hexdigest()
    signed.save(approval_id=state["exact_release"].approval_id,
                signed_envelope=state["envelope"],evidence_sha256=digest)
    flow=ApprovalRequestService(repo, Authority())
    response=ApprovalResponse(
        approval_id=state["exact_release"].approval_id,
        organization_id=state["organization_id"],
        approver_identity_id=state["owner_identity_ids"][0],
        decision=ApprovalDecision.APPROVE,decided_at=state["now"],
        channel="entra_browser_admin",channel_response_id=digest,
        authentication_evidence_hash=digest,
    )
    flow.accept_response(response,now=state["now"])
    opts={
        "repo":tmp_path, "database":path,
        "approval_id":state["exact_release"].approval_id,
        "exact_release":state["exact_release"],"route":state["route"],
        "policy_version":"5.0","policy_sha256":state["policy_sha256"],
        "organization_id":state["organization_id"],
        "owner_identity_ids":state["owner_identity_ids"],
        "root_trust_path":state["root_trust_path"],"now":state["now"],
    }
    return state,repo,signed,opts


def test_protected_host_reads_exact_native_sqlite_receipt_only(tmp_path):
    state,repo,signed,args=fixture(tmp_path)
    result=verify_protected_v5_browser_ledger(**args)
    assert result["status"]=="host_signed_browser_receipt_verified"
    assert result["release_authorized"] is False
    assert result["production_changed"] is False
    assert repo.accepted_decision(args["approval_id"]) is not None


@pytest.mark.parametrize("name,invalid",[
    ("policy_version","4.0"),("policy_sha256","0"*64),
    ("organization_id","different"),("owner_identity_ids",("regular",)),
    ("approval_id","relapproval-"+"0"*32),
])
def test_v4_or_wrong_actor_denied_without_rewrite(tmp_path,name,invalid):
    _,repo,_,args=fixture(tmp_path)
    args[name]=invalid
    with pytest.raises(PermissionError):
        verify_protected_v5_browser_ledger(**args)


def test_missing_database_denied_without_creating_new_db(tmp_path):
    _,repo,_,args=fixture(tmp_path)
    target=tmp_path/"missing-native.sqlite3"
    args["database"]=target
    with pytest.raises(PermissionError):
        verify_protected_v5_browser_ledger(**args)
    assert not target.exists()


def test_corrupt_signed_evidence_denied(tmp_path):
    state,repo,_,args=fixture(tmp_path)
    repo._connection.execute(
        "UPDATE mobile_release_signed_evidence SET evidence_sha256=? WHERE approval_id=?",
        ("f"*64,state["exact_release"].approval_id),
    )
    with pytest.raises(PermissionError):
        verify_protected_v5_browser_ledger(**args)


def test_v5_host_consumer_leaves_native_receipt_immutable(tmp_path):
    _,repo,_,args=fixture(tmp_path)
    before=repo._connection.execute(
        "SELECT payload FROM approval_requests WHERE approval_id=?",
        (args["approval_id"],),
    ).fetchone()[0]
    verify_protected_v5_browser_ledger(**args)
    after=repo._connection.execute(
        "SELECT payload FROM approval_requests WHERE approval_id=?",
        (args["approval_id"],),
    ).fetchone()[0]
    assert before==after
