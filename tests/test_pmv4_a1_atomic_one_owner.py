"""One local Owner consent creates exactly bound A1 root+shadow proofs."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel import signed_owner_release as signature
from tools import pmv4_a1_atomic_one_owner as owner
from tools import pmv4_a1_atomic_shadow_root as root


def test_one_owner_one_approval_two_exact_signed_scopes(monkeypatch):
    key=Ed25519PrivateKey.generate()
    signer=SimpleNamespace(
        TID=signature.TID,
        read_service_owner_signing_key=lambda path:key,
        issue_exact_owner_release=signature.issue_exact_owner_release,
    )
    manifest={"scope_sha256":"1"*64}
    plan={"scope_sha256":"2"*64,"shadow_freeze_sha256":"3"*64}
    now=datetime.now(timezone.utc)
    aid="owner-mcp-"+"a"*32
    result=owner.issue_pair(
        owner_oid=signature.OWNER_OID,
        owner_principal=signature.OWNER_PRINCIPAL,
        signer=signer,at=now,approval_id=aid,
        plan=plan,manifest=manifest,
    )
    assert result["approval_id"]==aid
    root_signed=result["signed_root_release"]
    child_signed=result["signed_shadow_release"]
    assert root_signed["payload"]["approval_id"]==aid
    assert child_signed["payload"]["approval_id"]==aid
    assert root_signed["payload"]["issued_at"]==child_signed["payload"]["issued_at"]
    assert root_signed["payload"]["owner_oid"]==child_signed["payload"]["owner_oid"]
    assert root_signed["payload"]["scope_sha256"] != child_signed["payload"]["scope_sha256"]
    for signed,scope,manifest_hash in (
        (root_signed,plan["scope_sha256"],root.sha(root.canon(plan))),
        (child_signed,manifest["scope_sha256"],root.sha(root.canon(manifest))),
    ):
        verified=signature.verify_exact_owner_release(
            signed,public_key=key.public_key(),
            at=now,expected_candidate_sha=root.CANDIDATE,
            expected_rollback_sha=root.ROLLBACK,
            expected_release_id="release-"+root.CANDIDATE[:16],
            expected_scope_sha256=scope,
            expected_manifest_sha256=manifest_hash,
            expected_freeze_sha256=plan["shadow_freeze_sha256"],
        )
        assert verified["owner_oid"]==signature.OWNER_OID
        assert verified["approval_id"]==aid
    with pytest.raises(signature.OwnerReleaseProofDenied,
                       match="TRANSACTION_BINDING_MISMATCH"):
        signature.verify_exact_owner_release(
            root_signed,public_key=key.public_key(),at=now,
            expected_candidate_sha=root.CANDIDATE,
            expected_rollback_sha=root.ROLLBACK,
            expected_release_id="release-"+root.CANDIDATE[:16],
            expected_scope_sha256=manifest["scope_sha256"],
            expected_manifest_sha256=root.sha(root.canon(manifest)),
            expected_freeze_sha256=plan["shadow_freeze_sha256"],
        )


def test_owner_review_plan_has_one_consent_and_no_runtime_authority(tmp_path,monkeypatch):
    monkeypatch.setattr(root,"PLAN",tmp_path/"source-only-reviewed-plan.json")
    source={
        "schema_version":"1.0","action":root.ACTION,
        "candidate_sha":root.CANDIDATE,"rollback_sha":root.ROLLBACK,
        "root_executor_sha256":"a"*64,"owner_consents":1,
        "standing_authority":False,
        "root_stage_before_owner_authorization":False,
    }
    monkeypatch.setattr(owner,"expected_plan",lambda:source)
    doc=owner.exact_plan()
    assert doc["owner_consents"]==1
    assert doc["standing_authority"] is False
    assert doc["root_stage_before_owner_authorization"] is False
    assert doc["action"]==root.ACTION
    assert doc["root_executor_sha256"]=="a"*64
    assert doc["scope_sha256"]==root.sha(root.canon({
        key:value for key,value in doc.items() if key!="scope_sha256"
    }))
    assert owner.prepare_plan()==doc


def test_authentication_rejects_unverified_device_response(monkeypatch):
    stub=SimpleNamespace(TENANT="test",CLIENT_ID="test",SCOPE="Jason.Read",
                        _form=lambda url,data:{"error":"invalid_scope"})
    with pytest.raises(owner.A1OwnerDenied,match="DEVICE_FLOW_UNAVAILABLE"):
        owner.authenticate_owner(stub)


def test_authentication_requires_exact_user_confirmation(monkeypatch,tmp_path):
    plan=tmp_path/"test-plan.json"
    plan.write_text(json.dumps({"scope_sha256":"b"*64}))
    monkeypatch.setattr(root,"PLAN",plan)
    responses=iter([
        {"device_code":"test","user_code":"MOCK","verification_uri":"https://test.invalid",
         "expires_in":600,"interval":5},
        {"access_token":"synthetic-not-a-real-token"},
    ])
    stub=SimpleNamespace(
        TENANT="tenant",CLIENT_ID="client",SCOPE="Jason.Read",
        _form=lambda url,data: next(responses),
        jwt_owner=lambda token: signature.OWNER_OID,
    )
    monkeypatch.setattr(owner.time,"sleep",lambda _seconds:None)
    monkeypatch.setattr("builtins.input",lambda text:"NOT-APPROVED")
    with pytest.raises(owner.A1OwnerDenied,match="EXACT_CONSENT_NOT_GIVEN"):
        owner.authenticate_owner(stub)


def test_untrusted_owner_signer_is_denied(tmp_path):
    tmp=tmp_path/"signer.py"
    tmp.write_text("def insecure(): pass")
    with pytest.raises(owner.A1OwnerDenied,match="TRUSTED_LIBRARY_CHANGED"):
        owner.trusted(tmp,"a"*64,"fake_untrusted")
