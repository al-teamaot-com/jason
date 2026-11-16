"""Disposable A1 root policy transaction; NO production locks/files/containers."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel import signed_owner_release as signer
from tools import pmv4_a1_watchdog_policy_root as root
from tools import pmv4_a1_watchdog_one_owner as owner


@pytest.fixture
def disposable(tmp_path,monkeypatch):
    directory=tmp_path/"root_only_disposable"
    directory.mkdir(mode=0o700)
    path=directory/"production-desired-state.json"
    base={
        "schema_version":"1.0",
        "allowed_running_containers":["jason-runtime","jason-mcp-pilot",
                                      "historical-authorized"],
        "required_containers":["jason-runtime","jason-mcp-pilot"],
        "required_system_units":["jason-core.service"],
        "allowed_system_units":["jason-root-audit.service"],
        "required_user_units":["jason-kfs-collector.timer"],
        "allowed_user_units":["jason-kfs-collector.service"],
        "forbidden_execution_prefixes":["/tmp/"],
        "rollback_container_prefixes":["jason-runtime-rollback-"],
        "max_stopped_rollback_containers":20,
    }
    raw=(json.dumps(base,sort_keys=True,indent=2)+"\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    candidate=dict(base,allowed_running_containers=base["allowed_running_containers"]+[root.NAME])
    expected=(json.dumps(candidate,sort_keys=True,indent=2,
                         separators=(",",": "))+"\n").encode()
    for key,value in {
        "POLICY":path,"ROOT_DIR":directory,
        "AUDIT":directory/"audit","BACKUP":directory/"audit/original-policy.bin",
        "INTENT":directory/"audit/intent.json",
        "COMMIT":directory/"audit/committed.json",
        "RECOVERY":directory/"audit/recovered.json",
        "OLD_SHA":root.digest(raw),"NEW_SHA":root.digest(expected),
    }.items():
        monkeypatch.setattr(root,key,value)
    monkeypatch.setattr(root,"read_root_original",lambda:path.read_bytes())
    freeze=tmp_path/"freeze"
    hold=tmp_path/"hold"
    freeze.write_text("never unfreeze")
    hold.write_text("never unhold")
    monkeypatch.setattr(root,"FREEZE",freeze)
    monkeypatch.setattr(root,"HOLD",hold)
    monkeypatch.setattr(root,"FREEZE_SHA",root.digest(freeze.read_bytes()))
    monkeypatch.setattr(root,"HOLD_SHA",root.digest(hold.read_bytes()))
    monkeypatch.setattr(root,"source_attestation",lambda *_args,**_kwargs:None)
    return path,raw,expected,base


class FakeHost:
    def __init__(self):
        self.locks=0
        self.core=0
    @contextmanager
    def host_release_transaction(self):
        self.locks+=1
        yield
    def _assert_protected_release_state(self):
        return None
    def preexisting_core_health(self):
        self.core+=1
        return True
    def protected_release_status(self):
        return {"ready":True}


def test_exact_policy_retains_unrelated_fields(disposable):
    policy,raw,expected,base=disposable
    assert root.exact_policy(raw)==expected
    observed=json.loads(expected)
    assert observed["allowed_running_containers"][-1]==root.NAME
    assert observed["required_containers"]==base["required_containers"]
    assert all(observed[key]==base[key]
               for key in base if key!="allowed_running_containers")


def test_original_hash_or_extra_allowance_denied(disposable):
    policy,raw,expected,base=disposable
    with pytest.raises(root.PolicyRootDenied,match="ORIGINAL_SHA_CHANGED"):
        root.exact_policy(raw+b" ")
    before=json.loads(raw)
    before["allowed_running_containers"].append(root.NAME)
    with pytest.raises(root.PolicyRootDenied):
        root.exact_policy(json.dumps(before).encode())


def test_atomic_replace_keeps_uid_mode_and_fsync(disposable):
    policy,raw,expected,base=disposable
    root.replace_policy(expected,token="disposable-test")
    assert policy.read_bytes()==expected
    assert policy.stat().st_uid==os.geteuid()
    assert policy.stat().st_mode&0o777==0o600
    root.replace_policy(raw,token="disposable-restore")
    assert policy.read_bytes()==raw


def test_unapproved_random_policy_mutation_rejected(disposable):
    policy,raw,expected,base=disposable
    with pytest.raises(root.PolicyRootDenied,match="NOT_REVIEWED"):
        root.replace_policy(b'{"arbitrary":true}',token="attempt")
    assert policy.read_bytes()==raw


def test_owner_proof_one_signature_exact_scope_and_replay(disposable,monkeypatch,tmp_path):
    key=Ed25519PrivateKey.generate()
    fake=SimpleNamespace(
        TID=signer.TID,
        issue_exact_owner_release=signer.issue_exact_owner_release,
        read_service_owner_signing_key=lambda path:key,
    )
    plan={"scope_sha256":"1"*64}
    receipt=owner.sign_one_scope(
        signer=fake,owner_oid=signer.OWNER_OID,
        owner_principal=signer.OWNER_PRINCIPAL,
        plan=plan,at=datetime.now(timezone.utc),
        approval_id="owner-mcp-"+"a"*32,
    )
    out=signer.verify_exact_owner_release(
        receipt["signed_release"],public_key=key.public_key(),
        at=datetime.now(timezone.utc),
        expected_candidate_sha=root.SOURCE,
        expected_rollback_sha=root.BASE,
        expected_release_id="release-"+root.SOURCE[:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=root.digest(root.canon(plan)),
        expected_freeze_sha256=root.FREEZE_SHA,
    )
    assert out["approval_id"]==receipt["approval_id"]
    assert out["one_release_only"] is True
    assert out["standing_authority"] is False
    with pytest.raises(signer.OwnerReleaseProofDenied,
                       match="TRANSACTION_BINDING_MISMATCH"):
        signer.verify_exact_owner_release(
            receipt["signed_release"],public_key=key.public_key(),
            at=datetime.now(timezone.utc),
            expected_candidate_sha=root.SOURCE,
            expected_rollback_sha=root.BASE,
            expected_release_id="release-"+root.SOURCE[:16],
            expected_scope_sha256="f"*64,
            expected_manifest_sha256=root.digest(root.canon(plan)),
            expected_freeze_sha256=root.FREEZE_SHA,
        )
    with pytest.raises(signer.OwnerReleaseProofDenied,
                       match="ONE_USE_REPLAY"):
        signer.verify_exact_owner_release(
            receipt["signed_release"],public_key=key.public_key(),
            at=datetime.now(timezone.utc),
            expected_candidate_sha=root.SOURCE,
            expected_rollback_sha=root.BASE,
            expected_release_id="release-"+root.SOURCE[:16],
            expected_scope_sha256=plan["scope_sha256"],
            expected_manifest_sha256=root.digest(root.canon(plan)),
            expected_freeze_sha256=root.FREEZE_SHA,
            consumed_ids=frozenset({receipt["approval_id"]}),
        )


def test_successful_guarded_policy_commit_uses_legacy_lock(disposable,monkeypatch):
    path,raw,expected,base=disposable
    h=FakeHost()
    approval="owner-mcp-"+"b"*32
    plan={"scope_sha256":"2"*64,"reviewed_pr_head_sha":root.SOURCE}
    monkeypatch.setattr(root,"preflight",lambda:(plan,h))
    monkeypatch.setattr(root,"verify_owner",lambda *_args,**_kw:{"approval_id":approval})
    monkeypatch.setattr(root,"drift_now",lambda:None)
    root.execute()
    assert h.locks==1
    assert h.core>=2
    assert path.read_bytes()==expected
    assert root.BACKUP.read_bytes()==raw
    assert root.object_file(root.INTENT)["owner_approval_id"]==approval
    assert root.object_file(root.COMMIT)["drift_independently_verified"] is True
    assert not root.RECOVERY.exists()
    assert root.FREEZE.read_text()=="never unfreeze"
    assert root.HOLD.read_text()=="never unhold"


def test_failed_drift_postflight_restores_exact_original_bytes(disposable,monkeypatch):
    path,raw,expected,base=disposable
    h=FakeHost()
    approval="owner-mcp-"+"c"*32
    monkeypatch.setattr(root,"preflight",lambda:({"scope_sha256":"3"*64,"reviewed_pr_head_sha":root.SOURCE},h))
    monkeypatch.setattr(root,"verify_owner",lambda *_args,**_kw:{"approval_id":approval})
    def fail():
        raise root.PolicyRootDenied("A1_POLICY_INDEPENDENT_DRIFT_NOT_PASS")
    monkeypatch.setattr(root,"drift_now",fail)
    with pytest.raises(root.PolicyRootDenied,match="DRIFT_NOT_PASS"):
        root.execute()
    assert path.read_bytes()==raw
    assert root.BACKUP.read_bytes()==raw
    assert not root.COMMIT.exists()
    assert root.object_file(root.RECOVERY)["status"]=="original_bytes_restored"
    assert h.locks==1


def test_no_owner_proof_means_no_release_possible(disposable,monkeypatch):
    path,raw,expected,base=disposable
    h=FakeHost()
    def no_proof(*_args,**_kwargs):
        raise root.PolicyRootDenied("A1_POLICY_OWNER_PROOF_MISSING")
    monkeypatch.setattr(root,"preflight",lambda:({"scope_sha256":"4"*64,"reviewed_pr_head_sha":root.SOURCE},h))
    monkeypatch.setattr(root,"verify_owner",no_proof)
    with pytest.raises(root.PolicyRootDenied,match="OWNER_PROOF_MISSING"):
        root.execute()
    assert path.read_bytes()==raw
    assert not root.AUDIT.exists()
    assert h.locks==0


def test_reviewed_pr_head_and_executor_hash_bind_exact_plan(tmp_path,monkeypatch):
    root_dir=tmp_path/"evidence"
    root_dir.mkdir()
    p=root_dir/"exact-policy-plan.json"
    monkeypatch.setattr(root,"PLAN",p)
    approved=root.fixed_plan()
    approved["reviewed_pr_head_sha"]="a"*40
    approved["scope_sha256"]=root.digest(root.canon(approved))
    p.write_bytes(root.canon(approved))
    p.chmod(0o400)
    assert root.plan_valid()==approved
    altered=dict(approved,reviewed_pr_head_sha="b"*40)
    p.chmod(0o600)
    p.write_bytes(root.canon(altered))
    p.chmod(0o400)
    with pytest.raises(root.PolicyRootDenied,match="PLAN_HASH_OR_SCOPE_CHANGED"):
        root.plan_valid()


def test_root_executor_denies_direct_unprivileged_execution():
    if os.geteuid()!=0:
        with pytest.raises(root.PolicyRootDenied,match="ROOT_REQUIRED"):
            root.root_script_trusted()


def test_original_fingerprint_and_target_hash_are_fixed():
    assert root.OLD_SHA=="4af577ccc02c367607da0c221c288df71ddc72bf4561ee6d7c6a35138f37e61c"
    assert root.NEW_SHA=="9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804"
    assert root.SOURCE_POLICY_SHA=="db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50"
    assert root.BASE=="8c2064193d74cc41b52369681febbc0a74fa96f7"
    assert root.SOURCE=="860dc8b90cfd1cb847cb0713ac7908b280b2265d"
