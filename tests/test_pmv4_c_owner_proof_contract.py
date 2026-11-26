"""Stage C exact signed release proof compatibility, no production signer key.

The test token/key are synthetic, never persisted and never used to approve
any release. The installed pinned signer is also exercised, when available.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import inspect
import json
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import pmv4_c_atomic_owner as owner
from tools import pmv4_c_atomic_root as root

SOURCE = "a"*40
ROLLBACK = "b"*40
REGULAR = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ADMIN = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"


def plan():
    return {
        "candidate_sha":SOURCE,
        "rollback_sha":ROLLBACK,
        "scope_sha256":"c"*64,
        "freeze_sha256":"d"*64,
    }


class TestOnlySigner:
    Ed25519PrivateKey=Ed25519PrivateKey
    TID="f7054323-d52b-4863-8c2f-1898f0b6077c"
    EXACT_OWNER_OAUTH_SUBJECTS={
        REGULAR:"person-entra-"+REGULAR.replace("-",""),
        ADMIN:"person-entra-"+ADMIN.replace("-",""),
    }

    @classmethod
    def issue_exact_owner_release(cls, **kwargs):
        assert kwargs["release_id"]=="release-"+kwargs["candidate_sha"][:16]
        assert kwargs["verified_owner_oid"] in cls.EXACT_OWNER_OAUTH_SUBJECTS
        assert kwargs["verified_principal"]==cls.EXACT_OWNER_OAUTH_SUBJECTS[
            kwargs["verified_owner_oid"]
        ]
        return {
            "payload":{
                "owner_oid":kwargs["verified_owner_oid"],
                "release_id":kwargs["release_id"],
                "approval_id":kwargs["approval_id"],
            },
            "synthetic_key":True,
        }

    @classmethod
    def verify_exact_owner_release(cls,signed,**kwargs):
        assert signed["synthetic_key"] is True
        assert kwargs["expected_release_id"]==signed["payload"]["release_id"]
        return signed["payload"]


def test_signed_release_identity_uses_native_issuer_namespace():
    assert owner.release_id(plan())=="release-"+SOURCE[:16]
    assert owner.release_id(plan())!="pmv4-c-"+SOURCE[:16]
    with pytest.raises(owner.StageCOwnerDenied,match="RELEASE_ID_SOURCE_INVALID"):
        owner.release_id({"candidate_sha":"bad"})


def test_synthetic_owner_proof_contract_checks_both_accounts_without_approval(
    tmp_path,monkeypatch,
):
    seen=[]
    signer=SimpleNamespace(
        Ed25519PrivateKey=Ed25519PrivateKey,
        TID=TestOnlySigner.TID,
        EXACT_OWNER_OAUTH_SUBJECTS=TestOnlySigner.EXACT_OWNER_OAUTH_SUBJECTS,
        issue_exact_owner_release=lambda **kw: (
            seen.append(kw["verified_owner_oid"])
            or TestOnlySigner.issue_exact_owner_release(**kw)
        ),
        verify_exact_owner_release=TestOnlySigner.verify_exact_owner_release,
    )
    monkeypatch.chdir(tmp_path)
    before={p.name for p in tmp_path.iterdir()}
    owner.signer_contract_preflight(signer,plan())
    after={p.name for p in tmp_path.iterdir()}
    assert before==after
    assert sorted(seen)==sorted([REGULAR,ADMIN])


def test_root_verification_requires_same_native_release_id(monkeypatch):
    verified=[]
    fake=SimpleNamespace(
        read_pinned_root_owner_public_key=lambda p:"synthetic_public_key",
        verify_exact_owner_release=lambda signed,**kw: (
            verified.append(kw["expected_release_id"])
            or {"approval_id":signed["approval_id"]}
        ),
    )
    proof={"schema_version":"1.0","action":root.ACTION,
           "source_sha":SOURCE,
           "scope_sha256":"c"*64,
           "plan_sha256":root.sha(root.canon(plan())),
           "approval_id":"owner-mcp-"+"f"*32,
           "signed_release":{"approval_id":"owner-mcp-"+"f"*32}}
    monkeypatch.setattr(root,"read_json",lambda p:proof)
    monkeypatch.setattr(root,"_trusted_module",lambda *args:fake)
    result=root._verify_owner(
        Path("/tmp/fake-pmv4-c-exact/root-release-plan.json"),
        plan(),
    )
    assert result["approval_id"]==proof["approval_id"]
    assert verified==["release-"+SOURCE[:16]]


def test_real_pinned_native_signer_accepts_both_accounts_without_user_token():
    pinned=owner.OWNER_SIGNER
    if not pinned.is_file():
        pytest.skip("Production native signer is absent from CI worker")
    # A file present but changed from the signed trust digest must FAIL.
    signer=owner.trusted(pinned,owner.OWNER_SIGNER_SHA,"test_c_pinned_signer")
    assert set(signer.EXACT_OWNER_OAUTH_SUBJECTS)=={REGULAR,ADMIN}
    owner.signer_contract_preflight(signer,plan())
    # Demonstrate the original defect is rejected for *either* account.
    key=Ed25519PrivateKey.generate()
    with pytest.raises(signer.OwnerReleaseProofDenied,
                       match="OWNER_RELEASE_PROOF_FIELDS_INVALID"):
        signer.issue_exact_owner_release(
            approval_id="owner-mcp-"+uuid.uuid4().hex,
            release_id="pmv4-c-"+SOURCE[:16],
            candidate_sha=SOURCE,
            rollback_sha=ROLLBACK,
            scope_sha256="c"*64,
            manifest_sha256=owner.sha(owner.canon(plan())),
            freeze_sha256="d"*64,
            verified_tenant_id=signer.TID,
            verified_owner_oid=REGULAR,
            verified_principal=signer.EXACT_OWNER_OAUTH_SUBJECTS[REGULAR],
            verified_organization_id="aot",
            confirmed_decision="approve",
            at=datetime.now(timezone.utc),
            private_key=key,
        )


def test_owner_synthetic_preflight_precedes_entra_device_flow():
    source=inspect.getsource(owner.authorize)
    assert source.index("signer_contract_preflight(signer,plan)") < (
        source.index("authenticate(auth,plan)")
    )
    check_only=inspect.getsource(owner.main)
    assert "signer_contract_preflight(signer,plan)" in check_only
    assert "PMV4_C_PINNED_SIGNER_EXACT_PROOF_PREFLIGHT=PASS" in check_only
