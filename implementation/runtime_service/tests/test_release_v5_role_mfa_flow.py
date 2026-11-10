"""Role MFA V5 browser decision still uses the original signed release ledger."""
from datetime import timedelta
from hashlib import sha256
import json

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService,ApprovalRequestStatus,
)
from jason_runtime.mobile_release_approval import (
    read_mobile_release_policy,read_eligible_release,create_mobile_release_request,
)
from implementation.runtime_service.tests.test_mobile_release_approval import (
    NOW,RELEASE,SimpleOwnerAuthority,
)
from implementation.runtime_service.tests.test_release_v5_aot_policy import new_policy
from implementation.runtime_service.tests.test_release_v5_browser_flow import _fixture
from implementation.runtime_service.tests.test_release_v5_role_mfa_policy import (
    role_payload,role_receipt,
)
from jason_runtime.release_v5_signed_evidence import public_key_fingerprint


def test_existing_admin_role_mfa_uses_same_approval_ledger_with_no_new_authority(tmp_path):
    flow,old_req,db,old_policy,key,proof,ca_path,root=_fixture(tmp_path)
    evidence=role_receipt()
    evidence["checked_at"]=NOW.isoformat()
    raw=json.dumps(evidence,sort_keys=True,separators=(",",":")).encode()
    ca_path.write_bytes(raw);ca_path.chmod(0o600)
    data=role_payload()
    bp=data["entra_browser_approval"]
    bp["ca_enforcement_receipt_sha256"]=sha256(raw).hexdigest()
    bp["signer_public_key_sha256"]=public_key_fingerprint(key.public_key())
    flow.policy_path=new_policy(tmp_path,data)
    policy=read_mobile_release_policy(flow.policy_path)
    assert policy.browser_policy.mfa_profile=="existing_admin_role_mfa"
    assert policy.browser_policy.auth_context_id is None
    pending=create_mobile_release_request(
        read_eligible_release(root,RELEASE,policy),policy,now=NOW)
    ApprovalRequestService(db,SimpleOwnerAuthority()).create(pending,now=NOW)
    exact_proof=dict(proof)
    exact_proof["approval_id"]=pending.approval_id
    exact_proof["candidate_sha"]=pending.metadata["candidate_sha"]
    exact_proof["rollback_sha"]=pending.metadata["rollback_sha"]
    exact_proof["scope_sha256"]=pending.metadata["scope_sha256"]
    exact_proof["manifest_sha256"]=pending.metadata["manifest_sha256"]
    result=flow.handle(
        approval_id=pending.approval_id,decision="approve",
        authenticated_admin_proof=exact_proof,
        when=NOW+timedelta(seconds=5),
    )
    assert result["status"]=="signed_decision_recorded"
    assert result["release_authorized"] is False
    assert result["production_deployed"] is False
    assert db.get(pending.approval_id).status is ApprovalRequestStatus.APPROVED
    assert db.get(old_req.approval_id).status is ApprovalRequestStatus.PENDING
