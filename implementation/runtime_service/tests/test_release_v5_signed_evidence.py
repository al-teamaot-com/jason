"""V5 root-verifiable admin decision: exact AOT identities, SHA and signature."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from jason_runtime.mobile_release_approval import (
    create_mobile_release_request,read_eligible_release,read_mobile_release_policy,
)
from jason_runtime.release_v5_signed_evidence import (
    sign_browser_release_decision,verify_browser_release_decision,
    public_key_fingerprint,
)
from implementation.runtime_service.tests.v5_synthetic_identity import AOT_ADMIN_OID,AOT_TENANT,CHANNEL
from implementation.runtime_service.tests.test_mobile_release_approval import (
    NOW,RELEASE,release_record,mark_release_high_impact,
)
from implementation.runtime_service.tests.test_release_v5_aot_policy import (
    base_payload,new_policy,
)


def _fixture(tmp_path):
    key=Ed25519PrivateKey.generate()
    payload=base_payload()
    payload["entra_browser_approval"]["signer_public_key_sha256"] = (
        public_key_fingerprint(key.public_key())
    )
    policy=read_mobile_release_policy(new_policy(tmp_path,payload))
    root,_=release_record(tmp_path)
    mark_release_high_impact(root)
    path=root/"records"/(RELEASE+".json")
    record=json.loads(path.read_text())
    record["manual_scope_review"]={"scope_sha256":"f"*64}
    path.write_text(json.dumps(record))
    evidence=read_eligible_release(root,RELEASE,policy)
    req=create_mobile_release_request(evidence,policy,now=NOW)
    return key,policy,req


def _admin_proof(request,now):
    return {
        "release_authorized":False,
        "channel":CHANNEL,
        "tenant_id":AOT_TENANT,
        "authenticated_admin_oid":AOT_ADMIN_OID,
        "approval_id":request.approval_id,
        "candidate_sha":request.metadata["candidate_sha"],
        "rollback_sha":request.metadata["rollback_sha"],
        "scope_sha256":request.metadata["scope_sha256"],
        "manifest_sha256":request.metadata["manifest_sha256"],
        "evidence_sha256":"a"*64,
        "auth_time":int((now-timedelta(seconds=10)).timestamp()),
    }


def _signed(key,policy,req,**changes):
    kwargs={
        "request":req,"policy":policy,
        "authenticated_admin_proof":_admin_proof(req,NOW+timedelta(seconds=15)),
        "ca_policy_receipt_sha256":policy.browser_policy.ca_enforcement_receipt_sha256,
        "decision":"approve",
        "when":NOW+timedelta(seconds=15),
        "private_key":key,
    }
    kwargs.update(changes)
    return sign_browser_release_decision(**kwargs)


def test_signature_roundtrip_binds_entire_immutable_release(tmp_path):
    key,policy,req=_fixture(tmp_path)
    signed=_signed(key,policy,req)
    proof=verify_browser_release_decision(
        signed=signed,request=req,policy=policy,
        public_key=key.public_key(),now=NOW+timedelta(seconds=16),
    )
    assert proof["decision"]=="approve"
    assert proof["authenticated_admin_oid"]==AOT_ADMIN_OID
    assert proof["notice_recipient_oid"]!=AOT_ADMIN_OID
    assert proof["standing_authority"] is False
    assert proof["single_transaction"] is True
    assert "client_secret" not in json.dumps(signed)
    assert "id_token" not in json.dumps(signed)


@pytest.mark.parametrize("field,wrong",[
    ("candidate_sha","0"*40),
    ("rollback_sha","0"*40),
    ("scope_sha256","0"*64),
    ("manifest_sha256","0"*64),
    ("authenticated_admin_oid","00000000-0000-0000-0000-000000000001"),
    ("tenant_id","00000000-0000-0000-0000-000000000001"),
    ("notice_recipient_oid","00000000-0000-0000-0000-000000000001"),
    ("standing_authority",True),
    ("decision","invalid"),
    ("owner_identity_id","person-eve"),
    ("ca_policy_receipt_sha256","0"*64),
])
def test_changed_signed_payload_invalidates_signature(tmp_path,field,wrong):
    key,policy,req=_fixture(tmp_path)
    signed=_signed(key,policy,req)
    payload=deepcopy(signed)
    payload["payload"][field]=wrong
    with pytest.raises(PermissionError,match="SIGNATURE_INVALID"):
        verify_browser_release_decision(
            signed=payload,request=req,policy=policy,
            public_key=key.public_key(),now=NOW+timedelta(seconds=16),
        )


def test_wrong_public_key_is_never_release_authority(tmp_path):
    key,policy,req=_fixture(tmp_path)
    signed=_signed(key,policy,req)
    other=Ed25519PrivateKey.generate()
    with pytest.raises(PermissionError,match="SIGNATURE_INVALID"):
        verify_browser_release_decision(
            signed=signed,request=req,policy=policy,
            public_key=other.public_key(),now=NOW+timedelta(seconds=16),
        )


def test_other_approver_even_with_valid_oidc_proof_denied(tmp_path):
    key,policy,req=_fixture(tmp_path)
    proof=_admin_proof(req,NOW+timedelta(seconds=15))
    proof["authenticated_admin_oid"]="00000000-0000-0000-0000-000000000001"
    with pytest.raises(PermissionError,match="PROOF_NOT_EXACT"):
        _signed(key,policy,req,authenticated_admin_proof=proof)


def test_client_teams_notice_cannot_serve_as_admin_decision(tmp_path):
    key,policy,req=_fixture(tmp_path)
    proof=_admin_proof(req,NOW+timedelta(seconds=15))
    proof["channel"]="microsoft_teams"
    with pytest.raises(PermissionError,match="PROOF_NOT_EXACT"):
        _signed(key,policy,req,authenticated_admin_proof=proof)


def test_missing_ca_policy_receipt_denies_signing(tmp_path):
    key,policy,req=_fixture(tmp_path)
    with pytest.raises(PermissionError,match="PROOF_NOT_EXACT"):
        _signed(key,policy,req,ca_policy_receipt_sha256="0"*64)


def test_expired_pending_request_cannot_sign_or_verify(tmp_path):
    key,policy,req=_fixture(tmp_path)
    with pytest.raises(PermissionError,match="REQUEST_NOT_AUTHORIZED"):
        _signed(key,policy,req,when=req.expires_at)
    signed=_signed(key,policy,req)
    with pytest.raises(PermissionError,match="SCOPE_MISMATCH"):
        verify_browser_release_decision(
            signed=signed,request=req,policy=policy,
            public_key=key.public_key(),now=req.expires_at,
        )


def test_edited_request_metadata_cannot_reuse_an_old_signature(tmp_path):
    key,policy,req=_fixture(tmp_path)
    signed=_signed(key,policy,req)
    altered=replace(req,metadata={**req.metadata,"scope_sha256":"0"*64})
    with pytest.raises(PermissionError,match="SCOPE_MISMATCH"):
        verify_browser_release_decision(
            signed=signed,request=altered,policy=policy,
            public_key=key.public_key(),now=NOW+timedelta(seconds=16),
        )


def test_wrong_browser_signing_key_not_in_root_policy_denied(tmp_path):
    key,policy,req=_fixture(tmp_path)
    other=Ed25519PrivateKey.generate()
    with pytest.raises(PermissionError,match="SIGNING_KEY_MISMATCH"):
        _signed(other,policy,req)


def test_denial_is_signed_but_not_approval(tmp_path):
    key,policy,req=_fixture(tmp_path)
    signed=_signed(key,policy,req,decision="deny")
    proof=verify_browser_release_decision(
        signed=signed,request=req,policy=policy,
        public_key=key.public_key(),now=NOW+timedelta(seconds=16),
    )
    assert proof["decision"]=="deny"
