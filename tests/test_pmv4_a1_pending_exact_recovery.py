"""A1 failed-transaction rollback proves original authorization without reauth."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from tools import pmv4_a1_pending_exact_recovery as rec


@pytest.fixture
def pending(tmp_path,monkeypatch):
    receipt=tmp_path/("owner-"+rec.APPROVAL_ID+".json")
    data={
        "schema_version":"1.0","service":"jason-pmv4-shadow",
        "state":"started","release_id":"release-"+rec.SOURCE[:16],
        "approval_id":rec.APPROVAL_ID,"candidate_sha":rec.SOURCE,
        "rollback_sha":rec.ROLLBACK,"manifest_sha256":"a"*64,
        "scope_sha256":"b"*64,"freeze_sha256":"c"*64,
        "started_at":datetime.now(timezone.utc).isoformat(),
        "no_pmv3_or_provider_mutation":True,
    }
    receipt.write_text(json.dumps(data)); receipt.chmod(0o600)
    monkeypatch.setattr(rec,"RECEIPT",receipt)
    return receipt,data


def test_exact_original_pending_receipt_read(pending):
    receipt,data=pending
    assert rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())==data


@pytest.mark.parametrize("field,wrong",[
    ("state","accepted"),("approval_id","owner-mcp-other"),
    ("candidate_sha","f"*40),("rollback_sha","2"*40),
    ("no_pmv3_or_provider_mutation",False),
    ("release_id","release-unrelated"),
])
def test_recovery_cannot_use_unrelated_transaction(pending,field,wrong):
    receipt,data=pending
    data[field]=wrong
    receipt.write_text(json.dumps(data))
    with pytest.raises(rec.A1RecoveryDenied):
        rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())


def test_receipt_wrong_permissions_denied(pending):
    receipt,data=pending
    receipt.chmod(0o666)
    with pytest.raises(rec.A1RecoveryDenied,match="METADATA_CHANGED"):
        rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())


def test_receipt_foreign_duplicate_denied(pending):
    receipt,data=pending
    (receipt.parent/("owner-"+"f"*32+".json")).write_text("{}")
    with pytest.raises(rec.A1RecoveryDenied,match="MULTIPLE_PENDING"):
        rec.read_exact_receipt(expected_uid=os.geteuid(),expected_gid=os.getegid())


def test_root_entrypoint_must_be_new_exact_root_copy():
    if os.geteuid()!=0:
        with pytest.raises(rec.A1RecoveryDenied,match="ROOT_TTY_REQUIRED"):
            rec.is_real_root_script()


def test_recover_uses_native_signed_rollback_and_no_new_owner(pending,monkeypatch):
    receipt,data=pending
    prior=receipt.parent/"releases"/rec.ROLLBACK
    prior.mkdir(parents=True)
    (prior/"baseline.json").write_text(json.dumps({
        "schema_version":"1.0","service":"jason-pmv4-shadow",
        "baseline":"no_prior_shadow_runtime"}))
    pointer=receipt.parent/"current"
    pointer.symlink_to("releases/"+rec.ROLLBACK)
    token=receipt.parent/"gateway-token"
    token.write_text("synthetic")
    events=[]
    class FakeController:
        def reconcile_pending_rollback(self,*,rollback_acceptance):
            events.append("native-reconcile")
            assert rollback_acceptance(prior) is True
            data["state"]="rolled_back"
            receipt.write_text(json.dumps(data))
            return {"status":"shadow_rollback_verified",
                    "rollback_sha":rec.ROLLBACK}
    class FakeAdapter:
        def _owned_or_absent(self):
            events.append("shadow-absent")
            return None
    class FakeHost:
        def preexisting_core_health(self):
            events.append("core-healthy")
            return True
        def protected_release_status(self):
            return {"ready":True}
    def cleanup(approval):
        assert approval==rec.APPROVAL_ID
        events.append("only-original-audit-files-cleaned")
    class FakeOriginal:
        CURRENT=pointer
        TARGET=receipt.parent/"not-present-target"
        APPROVED=receipt.parent/"not-present-approved"
        REVIEWED=receipt.parent/"not-present-review"
        TOKEN=receipt.parent/"not-present-token"
        shadow=SimpleNamespace(read_json=lambda x:json.loads(x.read_text()))
        def cleanup_exact_unpromoted(self,approval):cleanup(approval)
        def append(self,event,approval,details):
            assert event=="reconciled_original_exact_owner_rollback"
            assert approval==rec.APPROVAL_ID
            assert details["new_owner_approval"] is False
            events.append("original-audit-reconciled")
    original=FakeOriginal()
    monkeypatch.setattr(rec,"preflight",
                        lambda:(original,FakeHost(),FakeAdapter(),
                                FakeController(),{"scope_sha256":rec.EXACT_SCOPE}))
    rec.recover()
    assert data["state"]=="rolled_back"
    assert "native-reconcile" in events
    assert "only-original-audit-files-cleaned" in events
    assert "original-audit-reconciled" in events
    assert events.index("native-reconcile") < events.index(
        "only-original-audit-files-cleaned")


def test_recovery_does_not_modify_original_files_if_unproven(pending,monkeypatch):
    receipt,data=pending
    before=receipt.read_bytes()
    def denied():
        raise rec.A1RecoveryDenied("A1_ORIGINAL_SIGNATURE_INVALID")
    monkeypatch.setattr(rec,"preflight",denied)
    with pytest.raises(rec.A1RecoveryDenied,match="SIGNATURE_INVALID"):
        rec.recover()
    assert receipt.read_bytes()==before


def test_recovery_refuses_new_promotion_and_auth():
    script=(Path(__file__).resolve().parents[1]/
            "tools/pmv4_a1_pending_exact_recovery.py").read_text()
    for prohibited in ("--execute", "--authorize","--promote",
                       "issue_exact_owner_release(", "create_subprocess_shell("):
        assert prohibited not in script
    assert "reconcile_pending_rollback(" in script
    assert "cleanup_exact_unpromoted(" in script


def test_historical_signature_pair_bound_to_native_receipt(tmp_path,monkeypatch):
    from hashlib import sha256
    from types import SimpleNamespace
    import copy
    payload={
        "approval_id":rec.APPROVAL_ID,
        "issued_at":datetime.now(timezone.utc).isoformat(),
        "expires_at":datetime.now(timezone.utc).isoformat(),
        "owner_oid":"synthetic-owner",
        "owner_principal":"synthetic@invalid.local",
    }
    proof={
        "schema_version":"1.0","approval_id":rec.APPROVAL_ID,
        "source_sha":rec.SOURCE,"scope_sha256":rec.EXACT_SCOPE,
        "signed_root_release":{"payload":copy.deepcopy(payload)},
        "signed_shadow_release":{"payload":copy.deepcopy(payload)},
    }
    manifest={"candidate_sha":rec.SOURCE,"rollback_sha":rec.ROLLBACK,
              "scope_sha256":"e"*64}
    canon=lambda value:json.dumps(value,sort_keys=True).encode()
    sha=lambda raw:sha256(raw).hexdigest()
    plan={"scope_sha256":rec.EXACT_SCOPE,
          "shadow_manifest_sha256":"f"*64,
          "shadow_freeze_sha256":"a"*64}
    proof["manifest_sha256"]=sha(canon(plan))
    receipt={"manifest_sha256":sha(canon(manifest)),
             "scope_sha256":manifest["scope_sha256"],
             "freeze_sha256":plan["shadow_freeze_sha256"],
             "started_at":datetime.now(timezone.utc).isoformat()}
    journal=[{"event":"begin","approval_id":rec.APPROVAL_ID,
              "details":{"parent_scope_sha256":rec.EXACT_SCOPE,
                         "shadow_manifest_sha256":"f"*64}},
             {"event":"requires_review","approval_id":rec.APPROVAL_ID}]
    original=SimpleNamespace(
        plan_and_source=lambda:(plan,manifest,{}),
        read_json=lambda *_args,**_kwargs:proof,
        sha=sha,canon=canon,audit_rows=lambda:journal,
        ROOT_PIN=tmp_path/"mock-root-public-key",
    )
    monkeypatch.setattr(rec.shadow,"read_pinned_root_owner_public_key",
                        lambda *_args,**_kwargs:object())
    calls=[]
    def verifier(signed,**kw):
        calls.append(kw)
        assert kw["expected_candidate_sha"]==rec.SOURCE
        assert kw["expected_rollback_sha"]==rec.ROLLBACK
        assert kw["expected_freeze_sha256"]==plan["shadow_freeze_sha256"]
        return signed["payload"]
    monkeypatch.setattr(rec.shadow,"verify_exact_owner_release",verifier)
    assert rec.authenticate_historical_recovery(original,receipt)==plan
    assert len(calls)==2
    assert {x["expected_scope_sha256"] for x in calls}=={
        rec.EXACT_SCOPE,manifest["scope_sha256"]}
    bad_receipt=dict(receipt,manifest_sha256="0"*64)
    with pytest.raises(rec.A1RecoveryDenied,
                       match="NATIVE_JOURNAL_NOT_SIGNED_CHILD"):
        rec.authenticate_historical_recovery(original,bad_receipt)
    proof["signed_shadow_release"]["payload"]["owner_oid"]="other-owner"
    with pytest.raises(rec.A1RecoveryDenied,match="ONE_OWNER_PROOF_PAIR"):
        rec.authenticate_historical_recovery(original,receipt)
    journal[0]["details"]["parent_scope_sha256"]="0"*64
    with pytest.raises(rec.A1RecoveryDenied,match="ROOT_AUDIT_NOT_PENDING"):
        rec.authenticate_historical_recovery(original,receipt)
