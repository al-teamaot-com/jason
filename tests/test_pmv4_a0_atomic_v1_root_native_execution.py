"""Disposable UID0 execute original signed v1 full release with ONE legacy lock.

Root script itself uses fixed old pinned releases and absolute root parents;
this test monkeypatches only those global protected paths to disposable
/tmp fixtures and calls the real transaction/rollback methods. No live root.
"""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from kernel.signed_owner_release import canonical,OWNER_OID
from tools import pmv4_a0_exact_v1_root_release as root
from tools import pmv4_a0_one_release_v1_proof as signature
from tools import pmv4_stage_a_packet as packet
from tools.pmv4_a0_atomic_plan_transaction import A0AtomicTransactionDenied
from test_pmv4_a0_atomic_actual_root_components import real_three
from test_pmv4_owner_objective_end_to_end import AT, enrolled


@pytest.fixture
def root_native(real_three,monkeypatch,tmp_path):
    if os.geteuid()!=0:
        pytest.skip("real disposable UID0 release transaction only")
    env,old_v2,_,make_adapter=real_three
    root.POLICY=Path(__file__).parents[1]/"config/pmv4-stage-a0/atomic-v1-root-policy-review.json"
    policy=root.reviewed_policy(require_root=False)
    signed=signature.issue_source_only_existing_v1_proof(
        approval_id="owner-mcp-"+"e"*32,
        signer_key=env["owner_key"],
        verified_owner_oid=OWNER_OID,
        at=AT,
        independent_entra_owner_was_verified=True,
        confirmed_exact_full_plan=True,
    )
    assert len(env["consents"])==1
    own=old_v2.directory.parent/"source-only-disposable-full-root"
    own.mkdir(mode=0o700)
    monkeypatch.setattr(root,"JOURNAL",own/"root-protected-transaction.jsonl")
    a=make_adapter()
    a.outer_lock_held=True
    lock=a.old_lock
    os.chown(lock,1000,1000)
    lock.chmod(0o664)
    monkeypatch.setattr(root,"LOCK",lock)
    baseline={"safe":"unchanged","runtime_id":"r-unchanged","mcp_id":"m-unchanged"}
    monkeypatch.setattr(root,"trusted_entry",lambda:policy)
    monkeypatch.setattr(root,"read_root_preflight",lambda:{
        "bootstrap":__import__(
            "tools.pmv4_a0_closure_bootstrap_root",
            fromlist=["validate_plan"]
        ),
        "baseline":baseline,
        "stage":SimpleNamespace(protected_preflight=lambda sp:{
            "runtime_id":baseline["runtime_id"],"mcp_id":baseline["mcp_id"]}),
        "sparse":{},
    })
    boot=__import__("tools.pmv4_a0_closure_bootstrap_root",fromlist=["publish"])
    monkeypatch.setattr(boot,"validate_plan",lambda:({},a.blobs))
    monkeypatch.setattr(boot,"readback",lambda:dict(baseline))
    original_publish=boot.publish
    def publish_with_native_inode_evidence(data,before):
        original_publish(data,before)
        for path in [Path(x) for x in a.blobs]+[boot.LEDGER]:
            a._retain_inode(path)
        if a.fault==0:
            raise InterruptedError("bootstrap postflight interruption")
    monkeypatch.setattr(boot,"publish",publish_with_native_inode_evidence)
    monkeypatch.setattr(root,"verify_proof",lambda p,at: (
        signature.verify_existing_v1_whole_transaction(
            signed=signed,
            root_pinned_public_key=env["owner_key"].public_key(),
            at=AT+timedelta(seconds=1)
        ) and {
            "approval_id":signed["payload"]["approval_id"],
            "proof_sha256":sha256(canonical(signed)).hexdigest(),
            "full_manifest_sha256":signature.exact_v1_release_scopes()["manifest_sha256"],
        }
    ))
    monkeypatch.setattr(root,"close_source",lambda ctx: (
        a.apply(1,{"signed_v1_whole":signed})
        and {"after":{"disposable":"root_verified_before_test"}}
    ))
    monkeypatch.setattr(root,"load_native_exact_source",
                        lambda ctx,after:(packet,None,a.scope,a.manifest))
    def apply_native(p,n,s,m,proof):
        a.apply(2,{"signed_v1_whole":signed})
        engine=a.installer()
        return engine,engine._journal(a.candidate),{
            "source_sha":a.candidate,
            "scope_sha256":a.scope["scope_sha256"],
            "owner_approval_id":proof["approval_id"],
            "manifest_sha256":sha256(canonical(a.manifest)).hexdigest(),
            "freeze_sha256":root.FREEZE_SHA,
            "signed_proof_sha256":proof["proof_sha256"],
        }
    monkeypatch.setattr(root,"native_install_under_outer_lock",apply_native)
    monkeypatch.setattr(root,"build_recovery_context",lambda:{
        "bootstrap":boot,
        "stage":None,"sparse":None,
    })
    monkeypatch.setattr(root,"recover_native_if_present",lambda ctx,proof: (
        a.rollback_exact(2) if not a.verify_absent(2) else None
    ))
    monkeypatch.setattr(root,"recover_source_if_present",lambda ctx: (
        a.rollback_exact(1) if not a.verify_absent(1) else None
    ))
    monkeypatch.setattr(root,"recover_bootstrap_if_present",lambda ctx: (
        a.rollback_exact(0) if not a.verify_absent(0) else None
    ))
    return env,a,signed,own


@pytest.mark.parametrize("fault",[None,0,1,2])
def test_one_existing_native_v1_root_lease_covers_all_three_actual_effects(
    root_native, fault,
):
    env,a,signed,private=root_native
    a.fault=fault
    try:
        if fault is None:
            root.execute()
            assert root.audit_rows()[-1]["action"]=="committed"
            assert all(a.verify_installed(i) for i in range(3))
        else:
            with pytest.raises(InterruptedError):
                root.execute()
            assert root.audit_rows()[-1]["action"]=="rolled_back"
            assert all(a.verify_absent(i) for i in range(3))
        assert len(env["consents"])==1
        with pytest.raises(root.AtomicRootDenied):
            root.execute()
    finally:
        a.close()


def test_root_native_failure_preserves_foreign_replacement(root_native):
    env,a,signed,private=root_native
    orig_apply=a.apply
    def substituted(index,evidence):
        out=orig_apply(index,evidence)
        if index==1:
            a.exact_file.write_bytes(b"foreign")
            raise InterruptedError("foreign inode changed")
        return out
    a.apply=substituted
    try:
        with pytest.raises(root.AtomicRootDenied,match="FOREIGN_OR_UNVERIFIED"):
            root.execute()
        assert a.exact_file.read_bytes()==b"foreign"
        assert root.audit_rows()[-1]["action"]=="requires_review"
        assert len(env["consents"])==1
    finally:
        a.close()
