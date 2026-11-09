"""V5 Entra browser decision uses the existing approval service and evidence DB."""
from __future__ import annotations
from datetime import timedelta
from hashlib import sha256
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from connectors.src.jason_connectors.approval_requests import (
    SQLiteApprovalRequestRepository,ApprovalRequestService,ApprovalRequestStatus,
)
from jason_runtime.mobile_release_approval import (
    read_mobile_release_policy,read_eligible_release,create_mobile_release_request,
    MobileReleaseSignedEvidenceStore,
)
from jason_runtime.release_v5_browser_flow import GovernedV5BrowserReleaseDecision
from jason_runtime.release_v5_signed_evidence import (
    public_key_fingerprint,verify_browser_release_decision,
)
from implementation.runtime_service.tests.v5_synthetic_identity import AOT_TENANT,AOT_ADMIN_OID,CHANNEL
from implementation.runtime_service.tests.test_mobile_release_approval import (
    NOW,RELEASE,release_record,mark_release_high_impact,SimpleOwnerAuthority,
)
from implementation.runtime_service.tests.test_release_v5_aot_policy import (
    base_payload,new_policy,
)
from implementation.runtime_service.tests.test_release_v5_ca_attestation import receipt


def _fixture(tmp_path):
    key=Ed25519PrivateKey.generate()
    root,_=release_record(tmp_path)
    mark_release_high_impact(root)
    record_path=root/"records"/(RELEASE+".json")
    record=json.loads(record_path.read_text())
    record["manual_scope_review"]={"scope_sha256":"e"*64}
    record_path.write_text(json.dumps(record))
    ca=receipt();ca["checked_at"]=NOW.isoformat()
    ca_path=tmp_path/"ca.json"
    raw=json.dumps(ca,sort_keys=True,separators=(",",":")).encode()
    ca_path.write_bytes(raw);ca_path.chmod(0o600)
    data=base_payload()
    data["entra_browser_approval"]["ca_enforcement_receipt_sha256"]=sha256(raw).hexdigest()
    data["entra_browser_approval"]["signer_public_key_sha256"]=public_key_fingerprint(key.public_key())
    policy_path=new_policy(tmp_path,data)
    policy=read_mobile_release_policy(policy_path)
    evidence=read_eligible_release(root,RELEASE,policy)
    req=create_mobile_release_request(evidence,policy,now=NOW)
    db=tmp_path/"approvals.sqlite3"
    repository=SQLiteApprovalRequestRepository(db)
    approvals=ApprovalRequestService(repository,SimpleOwnerAuthority())
    approvals.create(req,now=NOW)
    signed=MobileReleaseSignedEvidenceStore(db)
    flow=GovernedV5BrowserReleaseDecision(
        policy_path=policy_path,release_state_root=root,
        ca_attestation_path=ca_path,requests=repository,
        approvals=approvals,signed_evidence=signed,signing_key=key,
    )
    proof={
        "release_authorized":False,"channel":CHANNEL,
        "tenant_id":AOT_TENANT,"authenticated_admin_oid":AOT_ADMIN_OID,
        "approval_id":req.approval_id,
        "candidate_sha":req.metadata["candidate_sha"],
        "rollback_sha":req.metadata["rollback_sha"],
        "scope_sha256":req.metadata["scope_sha256"],
        "manifest_sha256":req.metadata["manifest_sha256"],
        "evidence_sha256":"a"*64,
        "auth_time":int((NOW+timedelta(seconds=2)).timestamp()),
    }
    return flow,req,repository,policy,key,proof,ca_path,root


def test_browser_decision_is_one_exact_existing_atomic_approval(tmp_path):
    flow,req,db,policy,key,proof,ca_path,root=_fixture(tmp_path)
    result=flow.handle(
        approval_id=req.approval_id,decision="approve",
        authenticated_admin_proof=proof,
        when=NOW+timedelta(seconds=5),
    )
    assert result["status"]=="signed_decision_recorded"
    assert result["release_authorized"] is False
    assert result["production_deployed"] is False
    assert db.get(req.approval_id).status is ApprovalRequestStatus.APPROVED
    accepted=db.accepted_decision(req.approval_id)
    assert accepted is not None and accepted.channel==CHANNEL
    assert accepted.decided_by=="person-al"
    assert accepted.authentication_evidence_hash=="a"*64
    stored=flow.signed_evidence.db.execute(
        "SELECT signed_envelope_json,evidence_sha256 FROM mobile_release_signed_evidence WHERE approval_id=?",
        (req.approval_id,),
    ).fetchone()
    assert stored is not None
    signed=json.loads(stored[0])
    verified=verify_browser_release_decision(
        signed=signed,request=db.get(req.approval_id),
        policy=policy,public_key=key.public_key(),
        now=NOW+timedelta(seconds=6),
    )
    assert verified["candidate_sha"]==req.metadata["candidate_sha"]
    assert stored[1]==accepted.authentication_evidence_hash
    with pytest.raises(PermissionError,match="PENDING_REQUEST_NOT_FOUND"):
        flow.handle(
            approval_id=req.approval_id,decision="approve",
            authenticated_admin_proof=proof,
            when=NOW+timedelta(seconds=7),
        )


def test_browser_deny_is_terminal_without_release_authority(tmp_path):
    flow,req,db,policy,key,proof,ca_path,root=_fixture(tmp_path)
    result=flow.handle(
        approval_id=req.approval_id,decision="deny",
        authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5),
    )
    assert result["release_authorized"] is False
    assert db.get(req.approval_id).status is ApprovalRequestStatus.DENIED
    assert db.accepted_decision(req.approval_id).status=="denied"


@pytest.mark.parametrize("mutation",[
    {"authenticated_admin_oid":"00000000-0000-0000-0000-000000000001"},
    {"channel":"microsoft_teams"},
    {"release_authorized":True},
    {"scope_sha256":"b"*64},
])
def test_browser_flow_rejects_untrusted_teams_or_scope_and_writes_no_receipt(tmp_path,mutation):
    flow,req,db,policy,key,proof,ca_path,root=_fixture(tmp_path)
    proof.update(mutation)
    with pytest.raises(PermissionError):
        flow.handle(
            approval_id=req.approval_id,decision="approve",
            authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5),
        )
    assert db.get(req.approval_id).status is ApprovalRequestStatus.PENDING
    assert db.accepted_decision(req.approval_id) is None


def test_unreviewed_ca_receipt_blocks_before_approval(tmp_path):
    flow,req,db,policy,key,proof,ca_path,root=_fixture(tmp_path)
    ca_path.unlink()
    with pytest.raises(PermissionError,match="CA_POLICY_ATTESTATION_MISSING"):
        flow.handle(
            approval_id=req.approval_id,decision="approve",
            authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5),
        )
    assert db.get(req.approval_id).status is ApprovalRequestStatus.PENDING


def test_root_policy_must_be_version_5_and_admin_bound(tmp_path):
    flow,req,db,policy,key,proof,ca_path,root=_fixture(tmp_path)
    flow.required_policy_version="4.0"
    with pytest.raises(PermissionError,match="POLICY_NOT_ACTIVATED"):
        flow.handle(
            approval_id=req.approval_id,decision="approve",
            authenticated_admin_proof=proof,when=NOW+timedelta(seconds=5),
        )
    assert db.get(req.approval_id).status is ApprovalRequestStatus.PENDING
