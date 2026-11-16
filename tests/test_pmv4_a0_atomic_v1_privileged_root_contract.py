"""One pinned v1 root release: exact reviewed source, root audit and recovery.

The production root module is NEVER executed in production by these tests.
CI UID0 only uses disposable /tmp private stage paths for journal mutations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

import pytest

from tools import pmv4_a0_exact_v1_root_release as root
from tools import pmv4_a0_one_release_v1_proof as owner_v1
from test_pmv4_owner_objective_end_to_end import AT, OWNER_OID, enrolled


REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "config/pmv4-stage-a0/atomic-v1-root-policy-review.json"


def scoped_policy(monkeypatch):
    monkeypatch.setattr(root,"POLICY",POLICY)
    return root.reviewed_policy(require_root=False)


def test_reviewed_root_executor_digest_in_whole_signed_release(monkeypatch):
    p=scoped_policy(monkeypatch)
    signed=owner_v1.exact_v1_release_scopes()
    independent=root.full_release_scopes(p)
    assert signed["scope_sha256"]==independent["scope_sha256"]
    assert signed["manifest_sha256"]==independent["manifest_sha256"]
    assert len(p["ordered_actions"])==3
    assert signed["manifest"]["root_executor_sha256"]==sha256(
        (REPO/"tools/pmv4_a0_exact_v1_root_release.py").read_bytes()
    ).hexdigest()
    assert signed["manifest"]["production_runtime_or_mcp_replacement"] is False
    assert signed["manifest"]["production_freeze_or_hold_mutation"] is False
    assert p["production_apply_supported"] is False


def test_reviewed_root_code_denies_untrusted_source_invocation():
    proc=subprocess.run([
        "python3",str(REPO/"tools/pmv4_a0_exact_v1_root_release.py"),
        "--execute",
    ],text=True,capture_output=True)
    assert proc.returncode==2
    assert "A0_ATOMIC_TRUSTED_LOCAL_ROOT_REQUIRED" in proc.stderr


@pytest.mark.parametrize("bad",["extra_action","different_source","root_code_hash",
                                 "activate_generic_apply","unfreeze","other_scope"])
def test_root_policy_cannot_expand_root_authority(monkeypatch,tmp_path,bad):
    p=json.loads(POLICY.read_bytes())
    if bad=="extra_action":p["ordered_actions"].append(dict(p["ordered_actions"][-1]))
    elif bad=="different_source":p["candidate_sha"]="1"*40
    elif bad=="root_code_hash":p["root_executor_sha256"]="1"*64
    elif bad=="activate_generic_apply":p["production_apply_supported"]=True
    elif bad=="unfreeze":p["freeze_sha256"]="3"*64
    elif bad=="other_scope":p["ordered_actions"][1]["scope_sha256"]="a"*64
    source=tmp_path/"foreign-policy.json"
    source.write_text(json.dumps(p))
    monkeypatch.setattr(root,"POLICY",source)
    with pytest.raises(root.AtomicRootDenied):
        root.reviewed_policy(require_root=False)


def test_original_one_release_cryptographic_identity_enforces_exact_entire_scope(
    monkeypatch,enrolled,
):
    p=scoped_policy(monkeypatch)
    from kernel.signed_owner_release import issue_exact_owner_release,TID,OWNER_PRINCIPAL
    key=enrolled["owner_key"]
    original=root.full_release_scopes(p)
    signed=issue_exact_owner_release(
        approval_id="owner-mcp-"+"9"*32,
        release_id="release-"+root.CANDIDATE[:16],
        candidate_sha=root.CANDIDATE,rollback_sha=root.LKG,
        scope_sha256=original["scope_sha256"],
        manifest_sha256=original["manifest_sha256"],
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=TID,verified_owner_oid=OWNER_OID,
        verified_principal=OWNER_PRINCIPAL,verified_organization_id="aot",
        confirmed_decision="approve",at=AT,private_key=key,
    )
    bound=owner_v1.verify_existing_v1_whole_transaction(
        signed=signed,root_pinned_public_key=key.public_key(),
        at=AT+timedelta(seconds=1),
    )
    assert bound["approved_action_count"]==3
    assert bound["scope_sha256"]==original["scope_sha256"]


@pytest.fixture
def root_audit(monkeypatch,tmp_path):
    if os.geteuid()!=0:
        pytest.skip("actual disposable UID0 CI root test only")
    folder=tmp_path/"exact-root-audit"
    folder.mkdir(mode=0o700)
    monkeypatch.setattr(root,"JOURNAL",folder/"one-use-root.jsonl")
    proof={"approval_id":"owner-mcp-"+"a"*32,
           "proof_sha256":"b"*64}
    return proof


def test_root_audit_full_three_effects_never_early_commits(root_audit):
    proof=root_audit
    root.audit_append("begin",-1,{"reviewed":True},proof)
    for i in range(3):
        root.audit_append("intent",i,{"scope_sha256":root.STEPS[i][2]},proof)
        root.audit_append("installed",i,{"exact_verified":True},proof)
    root.audit_append("committed",-1,{"full":True},proof)
    rows=root.audit_rows()
    assert rows[-1]["action"]=="committed"
    assert [x["action"] for x in rows].count("installed")==3
    with pytest.raises(root.AtomicRootDenied,match="ALREADY_FINAL"):
        root.audit_append("intent",0,{},proof)


def test_root_audit_does_not_accept_partial_success(root_audit):
    proof=root_audit
    root.audit_append("begin",-1,{"reviewed":True},proof)
    root.audit_append("intent",0,{"reviewed":True},proof)
    with pytest.raises(root.AtomicRootDenied,match="PARTIAL_COMMIT"):
        root.audit_append("committed",-1,{"fake_full":True},proof)
    # The bad record cannot be rewritten or repaired by truncating the
    # journal: it remains failed closed for independent forensic review.


@pytest.mark.parametrize("fault",["safe_recovery","foreign_replacement"])
def test_root_audit_reverse_rollback_only_and_preserve_foreign(
    root_audit,monkeypatch,fault,
):
    proof=root_audit
    root.audit_append("begin",-1,{"reviewed":True},proof)
    for i in range(2):
        root.audit_append("intent",i,{},proof)
        root.audit_append("installed",i,{},proof)
    root.audit_append("intent",2,{},proof)
    attempts=[]
    monkeypatch.setattr(root,"recover_native_if_present",
                        lambda c,p: attempts.append(2))
    def stage1(c):
        attempts.append(1)
        if fault=="foreign_replacement":
            raise PermissionError("foreign root inode")
    monkeypatch.setattr(root,"recover_source_if_present",stage1)
    monkeypatch.setattr(root,"recover_bootstrap_if_present",
                        lambda c: attempts.append(0))
    from types import SimpleNamespace
    stage=SimpleNamespace(
        recover_exact_source=lambda release_root,scope:
            (attempts.append("source-stage"),True)[1],
    )
    recovery_ctx={"stage":stage,"original":{"scope_sha256":root.SPARSE_SCOPE}}
    if fault=="safe_recovery":
        done=root.revert_all(recovery_ctx,proof)
        assert done["status"]=="exact_original_root_absence_restored"
        assert attempts==[2,1,0,"source-stage"]
        assert root.audit_rows()[-1]["action"]=="rolled_back"
    else:
        with pytest.raises(root.AtomicRootDenied,match="FOREIGN_OR_UNVERIFIED"):
            root.revert_all(recovery_ctx,proof)
        assert attempts==[2,1]
        assert root.audit_rows()[-1]["action"]=="requires_review"


def test_root_journal_tamper_fails_closed(root_audit):
    proof=root_audit
    root.audit_append("begin",-1,{"approved":True},proof)
    raw=root.JOURNAL.read_bytes()
    root.JOURNAL.write_bytes(raw[:-1])
    with pytest.raises(root.AtomicRootDenied,match="AUDIT_TORN"):
        root.audit_rows()


def test_no_generic_file_writer_or_machine_command_surface():
    script=(REPO/"tools/pmv4_a0_exact_v1_root_release.py").read_text()
    assert "eval(" not in script
    assert "os.system(" not in script
    assert "shell=True" not in script
    assert "STEPS = (" in script
    assert len(root.STEPS)==3
    assert "pmv4-a0-exact-three-action-one-release-v1" in script
    assert "A0_ATOMIC_TRUSTED_LOCAL_ROOT_REQUIRED" in script

@pytest.mark.parametrize("bad_gate", ["none", "breaker", "ticket_worker", "mcp"])
def test_actual_native_root_substep_retains_protected_breaker_and_ticket_checks(
    monkeypatch, tmp_path, bad_gate,
):
    from types import SimpleNamespace
    from test_pmv4_a0_atomic_actual_root_components import FREEZE_BYTES, HOLD_BYTES
    frozen=tmp_path/"freeze"; frozen.write_bytes(FREEZE_BYTES)
    hold=tmp_path/"promotion-hold";hold.write_bytes(HOLD_BYTES)
    monkeypatch.setattr(root,"FREEZE",frozen)
    monkeypatch.setattr(root,"HOLD",hold)
    actions=[]
    class FakeNative:
        def __init__(self,**kwargs):
            assert kwargs["production"] is True and kwargs["owner_metadata"] is True
            self._new_fd=None
        def _trusted_journal_parent(self): actions.append("trusted-journal")
        def _assert_parents(self): actions.append("root-parents")
        def _journal(self,sha): return tmp_path/"atomic-native-install.jsonl"
        def _append(self,journal,event,binding): actions.append(event)
        def _create(self,src,scope,journal,binding,after): actions.append("create-native")
        def _verify_objects(self,scope,*,partial): actions.append("verified-objects")
        def _assert_new_lock(self,scope): actions.append("native-lock-verified")
    state={"runtime_healthy":True,"mcp_running":True,"worker_scan_fresh":True}
    if bad_gate=="ticket_worker": state["worker_scan_fresh"]=False
    if bad_gate=="mcp": state["mcp_running"]=False
    breaker="breaker"!=bad_gate
    class RootGuard:
        def protected_release_status(self): return {"ready":breaker}
        def core_health_evidence(self): return state
    packet=SimpleNamespace(IndependentHostGuard=RootGuard)
    native=SimpleNamespace(
        NativeStageAInstaller=FakeNative,
        production_root_health_readback=lambda:{
            "stage_a_empty_baseline_verified":True,
            "root_only_target_parent_verification_needed":False,
        },
    )
    proof={"approval_id":"owner-mcp-"+"a"*32,
           "proof_sha256":"c"*64}
    if bad_gate=="none":
        result=root.native_install_under_outer_lock(
            packet,native,{"scope_sha256":root.NATIVE_SCOPE},{},proof)
        assert result[2]["owner_approval_id"]==proof["approval_id"]
        assert actions[-1]=="verified_installed"
    else:
        with pytest.raises(root.AtomicRootDenied):
            root.native_install_under_outer_lock(
                packet,native,{"scope_sha256":root.NATIVE_SCOPE},{},proof)
        assert "prepared" in actions
        assert "verified_installed" not in actions
    assert "create-native" in actions and "native-lock-verified" in actions

@pytest.mark.parametrize("detected_failure",[False,True])
def test_exact_original_owner_proof_committed_rollback_only_on_failed_postflight(
    root_audit,monkeypatch,detected_failure,
):
    from contextlib import nullcontext
    proof=root_audit
    root.audit_append("begin",-1,{"reviewed":True},proof)
    for i in range(3):
        root.audit_append("intent",i,{"scope_sha256":root.STEPS[i][2]},proof)
        root.audit_append("installed",i,{"source_verified":True},proof)
    root.audit_append("committed",-1,{"all_three_pass":True},proof)
    calls=[]
    monkeypatch.setattr(root,"trusted_entry",lambda:{"policy":"reviewed"})
    monkeypatch.setattr(root,"root_release_lock",lambda:nullcontext())
    monkeypatch.setattr(root,"read_one_user_proof",lambda:{
        "signed_owner_proof":{"payload":{"issued_at":"2026-11-15T10:00:00+00:00"}}
    })
    monkeypatch.setattr(root,"verify_proof",lambda p,at:dict(proof))
    from types import SimpleNamespace
    stage=SimpleNamespace(recover_exact_source=lambda parent,scope:
                          (calls.append("staged-source"),True)[1])
    monkeypatch.setattr(root,"build_recovery_context",lambda:{
        "stage":stage,"original":{"scope_sha256":root.SPARSE_SCOPE},
    })
    monkeypatch.setattr(root,"recover_native_if_present",lambda c,p:calls.append(2))
    monkeypatch.setattr(root,"recover_source_if_present",lambda c:calls.append(1))
    monkeypatch.setattr(root,"recover_bootstrap_if_present",lambda c:calls.append(0))
    if detected_failure:
        def unhealthy(p):
            raise root.AtomicRootDenied("independently observed postcommit unhealthy")
        monkeypatch.setattr(root,"verify_all_stage_postflights",unhealthy)
        root.recover()
        assert calls==[2,1,0,"staged-source"]
        assert root.audit_rows()[-1]["action"]=="rolled_back"
        root.recover() # already rolled-back original receipt is idempotent
    else:
        monkeypatch.setattr(root,"verify_all_stage_postflights",lambda p:None)
        with pytest.raises(root.AtomicRootDenied,match="HEALTHY_COMMITTED_RELEASE"):
            root.recover()
        assert calls==[]
        assert root.audit_rows()[-1]["action"]=="committed"


def test_root_late_commit_audit_cannot_reopen_for_new_stage(root_audit):
    proof=root_audit
    root.audit_append("begin",-1,{},proof)
    for i in range(3):
        root.audit_append("intent",i,{},proof)
        root.audit_append("installed",i,{},proof)
    root.audit_append("committed",-1,{},proof)
    with pytest.raises(root.AtomicRootDenied,match="ALREADY_FINAL"):
        root.audit_append("intent",0,{},proof)
    root.audit_append("rollback_begin",-1,{"failed_final_postflight":True},proof)
    for i in (2,1,0):
        root.audit_append("rollback_verified",i,{"exact_owned_inode_absent":True},proof)
    root.audit_append("rolled_back",-1,{"full_previous_baseline":True},proof)
    with pytest.raises(root.AtomicRootDenied,match="ALREADY_FINAL"):
        root.audit_append("rollback_begin",-1,{},proof)
