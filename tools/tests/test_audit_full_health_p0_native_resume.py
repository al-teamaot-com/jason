"""Authenticated exact-action recovery, one-use Root native-only test suite."""
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat
import subprocess
import threading
import pytest
from tools import audit_full_health_p0_native_resume as x
from tools import audit_full_health_p0_finalize as f
from tools import audit_full_health_p0_recovery as r0
from tools.tests.test_audit_full_health_p0_finalize import fake_original

def setup_case(tmp_path,monkeypatch):
    r,old_claim,old_result,system,override,full,release=fake_original(tmp_path,monkeypatch)
    previous_sha="a"*40
    approved_raw=b"exact previously reviewed Main source under independent Entra owner"
    current_scope=f.scope(previous_sha,r,old_claim,old_result,approved_raw)
    old_approved_source_sha=f.sha(approved_raw)
    owner_record={
        "candidate_sha":previous_sha,
        "owner_oid":x.OWNER_OID,
        "scope":current_scope,
        "scope_sha256":f.sha(f.canon(current_scope)),
        "independently_verified_entra_owner":True,
        "status":"exact_one_use_claimed_before_root_mutation",
        "claimed_at":datetime.now(timezone.utc).isoformat(),
    }
    failed={
        "action":x.ACTION,
        "scope_sha256":owner_record["scope_sha256"],
        "status":"failed","failure_class":"KeyError",
        "failure_code":"SENSITIVE_DETAILS_REDACTED",
        "full_integrity_verified":True,
        "installed_exact_93_override_removed":True,
        "native_breaker_closed":False,
        "database_modified":False,"archive_migration":False,
    }
    current_receipt=tmp_path/"previous_owner_completed_partial"
    current_receipt.mkdir()
    (current_receipt/"attempt.json").write_bytes(x.canon(owner_record))
    (current_receipt/"result.json").write_bytes(x.canon(failed))
    # Simulate exactly the completed and authorized temporary 93 cleanup.
    override.unlink()
    system[(x.FULL,"User")]="al"
    system[(x.FULL,"ActiveState")]="inactive"
    system[(x.FULL,"ExecMainStatus")]="0"
    system[(x.FULL,"TimeoutStartUSec")]="1h 35min"
    system[(x.FULL,"ExecStart")]=f.CURRENT_92
    drift=release/"production-drift.json"
    drift.write_text(json.dumps({"status":"pass","problems":[],
        "observed_at":datetime.now(timezone.utc).isoformat()}))
    # Pre-existing approval for original 45 GiB P0 is represented by
    # fake_original() Root evidence; no second authentication function.
    f_ns=dict(
      read_approval=f.read_approval,RECEIPT=current_receipt,
      ORIGINAL_SCOPE_SHA=f.ORIGINAL_SCOPE_SHA,
      proven_live_health=f.proven_live_health,CURRENT_92=f.CURRENT_92,
      verified_ci=lambda *args:None)
    monkeypatch.setattr(x,"APPROVED_FINALIZER_SHA",previous_sha)
    monkeypatch.setattr(x,"APPROVED_FINALIZER_SOURCE_SHA256",
                        old_approved_source_sha)
    monkeypatch.setattr(x,"APPROVED_FINALIZER_SCOPE_SHA256",
                        owner_record["scope_sha256"])
    monkeypatch.setattr(x,"RECEIPT",tmp_path/"new_resume_record")
    monkeypatch.setattr(x,"AUDIT_RECORD",tmp_path/"archive-not-installed")
    monkeypatch.setattr(x,"reviewed_git",lambda *_:
       b"def protected_peer_inventory():\n return {'p'+str(i):{} for i in range(6)}\n")
    return r,old_claim,old_result,owner_record,failed,current_scope,f_ns,override,release

def check(tmp_path,monkeypatch):
    r,old_claim,old_result,owner_record,failed,current_scope,f_ns,override,release=setup_case(tmp_path,monkeypatch)
    row=x.check_root_state(f_ns,r,f_ns,old_claim,owner_record,failed,
                           "b"*40,b"current reviewed source")
    return r,old_claim,owner_record,failed,current_scope,f_ns,override,release,row

def test_exact_prior_authenticated_owner_scope_passes_without_new_challenge(
        tmp_path,monkeypatch):
    r,old_claim,owner_record,failed,current_scope,f_ns,override,release,row=check(tmp_path,monkeypatch)
    assert row["original_owner_oid"]==x.OWNER_OID
    assert row["original_owner_claim_sha256"]==x.sha(
        (f_ns["RECEIPT"]/"attempt.json").read_bytes())
    assert row["original_data_identity"]==old_claim["scope"]["live_source_identity"]
    assert row["actions_remaining"]==[
       "existing_fast_health_oneshot","three_native_drift_observations",
       "native_root_breaker_revalidation"]
    assert row["new_owner_approval"] is False
    assert row["archive_installation"] is False
    assert row["provider_writes"] is False
    assert row["delete_or_replace_files"] is False
    assert not x.RECEIPT.exists()
    assert not override.exists()

@pytest.mark.parametrize("mutate,expected",[
 (lambda c,r:c.update(owner_oid="foreign"),"EXACT_PREVIOUS_OWNER_ENTRA_CLAIM"),
 (lambda c,r:c.update(independently_verified_entra_owner=False),"EXACT_PREVIOUS_OWNER_ENTRA_CLAIM"),
 (lambda c,r:c.update(status="unclaimed"),"EXACT_PREVIOUS_OWNER_ENTRA_CLAIM"),
 (lambda c,r:c.update(candidate_sha="0"*40),"EXACT_PREVIOUS_OWNER_ENTRA_CLAIM"),
 (lambda c,r:c.update(scope_sha256="0"*64),"EXACT_PREVIOUS_OWNER_ENTRA_CLAIM"),
 (lambda c,r:r.update(status="verified"),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
 (lambda c,r:r.update(failure_class="PermissionError"),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
 (lambda c,r:r.update(installed_exact_93_override_removed=False),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
 (lambda c,r:r.update(native_breaker_closed=True),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
 (lambda c,r:r.update(full_integrity_verified=False),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
 (lambda c,r:r.update(database_modified=True),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
 (lambda c,r:r.update(archive_migration=True),"NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE"),
])
def test_wrong_owner_approval_or_partial_result_denied(
        tmp_path,monkeypatch,mutate,expected):
    r,old_claim,old_result,record,failed,scope,f_ns,*_=setup_case(tmp_path,monkeypatch)
    mutate(record,failed)
    with pytest.raises(x.Denied,match=expected):
        x.check_root_state(f_ns,r,f_ns,old_claim,record,failed,"b"*40,b"safe")
    assert not x.RECEIPT.exists()

@pytest.mark.parametrize("mutate",[
    lambda s:s.update(action="foreign"),
    lambda s:s.update(candidate_sha="0"*40),
    lambda s:s.update(rollback_sha="0"*40),
    lambda s:s.update(policy={}),
    lambda s:s.update(provider_writes=True),
    lambda s:s.update(database_writes=True),
    lambda s:s.update(archive_installation=True),
    lambda s:s.update(data_reclamation=True),
    lambda s:s.update(root_unit_restart=True),
    lambda s:s.update(queue_cutover=True),
    lambda s:s.update(native_drift_observations=1),
    lambda s:s.update(only_change_delete_exact_93_and_restore_existing_health=False),
    lambda s:s.update(native_breaker_revalidation_only=False),
    lambda s:s.update(original_root_worker_sha256="0"*64),
    lambda s:s.update(original_data_identity={}),
    lambda s:s.update(installation_targets=["/etc/sudoers"]),
])
def test_unapproved_scope_mutations_denied(tmp_path,monkeypatch,mutate):
    r,old_claim,old_result,record,failed,scope,f_ns,*_=setup_case(tmp_path,monkeypatch)
    mutate(scope)
    with pytest.raises(x.Denied):
        x.check_root_state(f_ns,r,f_ns,old_claim,record,failed,"b"*40,b"safe")
    assert not x.RECEIPT.exists()

def test_changed_original_database_identity_denied(tmp_path,monkeypatch):
    r,old_claim,old_result,record,failed,scope,f_ns,*_=setup_case(tmp_path,monkeypatch)
    r.dataset=lambda:{"device":0,"inode":0}
    with pytest.raises(x.Denied,match="APPROVED_CANONICAL_DATABASE_DEVICE_INODE_CHANGED"):
        x.check_root_state(f_ns,r,f_ns,old_claim,record,failed,"b"*40,b"safe")

def test_reappearing_temporary_override_denied(tmp_path,monkeypatch):
    r,old_claim,old_result,record,failed,scope,f_ns,override,*_=setup_case(tmp_path,monkeypatch)
    override.write_bytes(b"foreign-Root-dropin")
    with pytest.raises(x.Denied,match="TEMPORARY_93_MUST_BE_ALREADY_REMOVED"):
        x.check_root_state(f_ns,r,f_ns,old_claim,record,failed,"b"*40,b"safe")
    assert override.exists()

def test_unrelated_breaker_or_drift_denied(tmp_path,monkeypatch):
    r,old_claim,old_result,record,failed,scope,f_ns,override,release=setup_case(tmp_path,monkeypatch)
    control=release/"production-control-state.json"
    payload=json.loads(control.read_bytes());payload["circuit_breaker"]["state"]="closed"
    control.write_bytes(x.canon(payload))
    with pytest.raises(x.Denied,match="NATIVE_BREAKER_OR_DRIFT_NOT_IN_APPROVED_STATE"):
        x.check_root_state(f_ns,r,f_ns,old_claim,record,failed,"b"*40,b"safe")

def test_prior_claim_is_one_use_when_recovery_attempt_started(tmp_path,monkeypatch):
    r,old_claim,owner_record,failed,scope,f_ns,override,release,row=check(tmp_path,monkeypatch)
    monkeypatch.setattr(x.os,"chown",lambda *args:None)
    first=x.claim_one_use(r,"b"*40,row)
    assert first["original_entra_approval_reused_only_within_same_exact_scope"] is True
    assert first["one_use_native_resume"] is True
    assert first["scope_sha256"]==x.sha(x.canon(row))
    with pytest.raises(x.Denied,match="REPEATED_USE_DENIED"):
        x.claim_one_use(r,"b"*40,row)


def test_native_only_completion_uses_existing_root_verified_breaker(
        tmp_path,monkeypatch):
    r,original,record,failed,scope,f_ns,override,release,planned=check(tmp_path,monkeypatch)
    monkeypatch.setattr(x,"reviewed_native_root_controller",lambda *_:None)
    actions=[]
    def native_dispatch(r,stop,outcome):
        actions.append("exact-native-dispatch")
        outcome["native_controller_started"]=True
        outcome["native_readback_published"]=True
    monkeypatch.setattr(x,"dispatch_only_exact_native_request",native_dispatch)
    def original_native_full_revalidate(approved_at):
        actions.append("original-native-health-and-three-drift")
        p=release/"production-control-state.json"
        control=json.loads(p.read_bytes())
        control["circuit_breaker"]={
           "state":"closed","reason":"root_verified_revalidate",
           "revalidated_revision":r.LKG}
        p.write_bytes(x.canon(control))
        return ["observed-1","observed-2","observed-3"]
    r.after_full_native_revalidation=original_native_full_revalidate
    x.RECEIPT.mkdir(mode=0o700)
    x.finish_native(r,original,record,{"scope":planned})
    assert actions==[
       "exact-native-dispatch","original-native-health-and-three-drift"]
    result=json.loads((x.RECEIPT/"result.json").read_bytes())
    assert result["state"]=="verified"
    assert result["native_breaker_closed"] is True
    assert result["native_root_controller_started"] is True
    assert result["native_root_readback_published"] is True
    assert result["genuine_full_integrity_verified"] is True
    assert result["archive_installation"] is False
    assert result["archive_data_reclamation"] is False
    assert result["replayed_93_cleanup"] is False
    assert not override.exists()

@pytest.mark.parametrize("wrong_reason,wrong_revision",[
    ("fabricated_reason",None),
    ("root_verified_revalidate","0"*40),
])
def test_native_completion_requires_exact_root_verified_result(
        tmp_path,monkeypatch,wrong_reason,wrong_revision):
    r,original,record,failed,scope,f_ns,override,release,planned=check(tmp_path,monkeypatch)
    monkeypatch.setattr(x,"reviewed_native_root_controller",lambda *_:None)
    monkeypatch.setattr(x,"dispatch_only_exact_native_request",
                        lambda r,stop,o:o.update(native_controller_started=True,native_readback_published=True))
    def fake(r0):
        p=release/"production-control-state.json"
        a=json.loads(p.read_bytes());a["circuit_breaker"]={
           "state":"closed","reason":wrong_reason,
           "revalidated_revision":wrong_revision or r.LKG}
        p.write_bytes(x.canon(a))
        return ["a","b","c"]
    r.after_full_native_revalidation=fake
    x.RECEIPT.mkdir()
    with pytest.raises(x.Denied,match="ROOT_NATIVE_BREAKER_NOT_INDEPENDENTLY_CLOSED"):
        x.finish_native(r,original,record,{"scope":planned})
    status=json.loads((x.RECEIPT/"result.json").read_bytes())
    assert status["state"]=="failed" and status["native_breaker_closed"] is False
    assert not override.exists()

def test_native_worker_failure_does_not_claim_success(tmp_path,monkeypatch):
    r,original,record,failed,scope,f_ns,override,release,planned=check(tmp_path,monkeypatch)
    monkeypatch.setattr(x,"reviewed_native_root_controller",lambda *_:None)
    monkeypatch.setattr(x,"dispatch_only_exact_native_request",
                        lambda *args:args[-1].update(
                          native_controller_started=True,native_readback_published=True))
    def failed_revalidate(*args):
        raise x.Denied("NATIVE_DRIFT_NOT_PASS")
    r.after_full_native_revalidation=failed_revalidate
    x.RECEIPT.mkdir()
    with pytest.raises(x.Denied,match="NATIVE_DRIFT_NOT_PASS"):
        x.finish_native(r,original,record,{"scope":planned})
    assert json.loads((x.RECEIPT/"result.json").read_bytes())["state"]=="failed"

def make_native_request(candidate,*,action="revalidate",revision=None,
                        uid=1000,mode=0o100600):
    import uuid
    raw={
        "request_id":uuid.uuid4().hex,"action":action,
        "revision":revision or candidate,
        "reason":"","release_id":""}
    data=x.canon(raw)
    class FakeFile:
        stem=raw["request_id"]
        suffix=".json"
        def __init__(self):
            self.bytes=data
            self.meta=SimpleNamespace(
                st_mode=mode,st_uid=uid,st_gid=uid,st_nlink=1,st_size=len(data))
        def lstat(self):return self.meta
        def is_symlink(self):return False
        def read_bytes(self):return self.bytes
    return FakeFile()

@pytest.mark.parametrize("action,rev,uid,mode,allowed",[
    ("revalidate","matches",1000,0o100600,True),
    ("open","matches",1000,0o100600,False),
    ("set_last_known_good","matches",1000,0o100600,False),
    ("revalidate","different",1000,0o100600,False),
    ("revalidate","matches",0,0o100600,False),
    ("revalidate","matches",1000,0o100666,False),
])
def test_root_transition_dispatcher_allows_only_exact_reviewed_request(
        tmp_path,monkeypatch,action,rev,uid,mode,allowed):
    revision="b"*40
    native=make_native_request(revision,action=action,
             revision=("0"*40 if rev=="different" else revision),
             uid=uid,mode=mode)
    class FakeDirectory:
        def iterdir(self):return [native]
    monkeypatch.setattr(x,"NATIVE_REQUESTS",FakeDirectory())
    calls=[]
    monkeypatch.setattr(x.subprocess,"run",
        lambda args,**kw:(calls.append(list(args)),
          SimpleNamespace(returncode=0))[1])
    outcome={}
    x.dispatch_only_exact_native_request(
        SimpleNamespace(LKG=revision),threading.Event(),outcome)
    if allowed:
        assert outcome=={"native_controller_started":True,
                         "native_readback_published":True}
        assert calls==[["/usr/bin/systemctl","start",
                        "jason-release-control-transition.service"],
                       ["/usr/bin/systemctl","start",
                        "jason-release-control-readback.service"]]
    else:
        assert isinstance(outcome.get("error"),x.Denied)
        assert not calls

def test_one_time_native_root_request_denies_multiple_pending(
        monkeypatch):
    class FakeDirectory:
        def iterdir(self):return [object(),object()]
    monkeypatch.setattr(x,"NATIVE_REQUESTS",FakeDirectory())
    calls=[]
    monkeypatch.setattr(x.subprocess,"run",lambda *a,**k:calls.append(a))
    result={}
    x.dispatch_only_exact_native_request(
        SimpleNamespace(LKG="b"*40),threading.Event(),result)
    assert isinstance(result.get("error"),x.Denied)
    assert not calls

def test_current_root_controller_sha_and_systemd_service_pins():
    assert x.NATIVE_ROOT_CONTROLLER_SHA==(
        "02ce315d9e96e1e655c3465f5fc2761661f78e5ced5b13f849680a85f2a1ff7e")
    assert x.NATIVE_ROOT_UNIT_SHA==(
        "759837f9c873ebe2964031343166e1b59e7f99aab76c8d89c506c09aaffd3192")
    assert x.NATIVE_READBACK_WORKER_SHA==(
        "a5a1eee07ca5afd26fd204e6575eb6c709c3fd6d5cd0b0b2a719694e16dadfec")
    assert x.NATIVE_READBACK_UNIT_SHA==(
        "7b6b55bfcfb9b0a88b2c4705bd87a740b61c1c2f6182d73ea09ec211d17e3b83")
    assert x.APPROVED_FINALIZER_SCOPE_SHA256==(
        "74e53eef7fb774546c3cb6eebb3ad1cdabeb32030265cd825075de00a077abe7")
    assert x.APPROVED_FINALIZER_SOURCE_SHA256==(
        "a2f3713e0c91e6612abdb71b76694d642ce67051e53633770dfc30959451d3c8")


def test_cli_readonly_preflight_without_new_owner_authentication(
        tmp_path,monkeypatch,capsys):
    import contextlib
    r,original,record,failed,scope,f_ns,override,release,planned=check(
        tmp_path,monkeypatch)
    def forbidden_new_owner(*args):
        pytest.fail("must not open a new Owner consent challenge")
    auth={"locks":lambda:contextlib.nullcontext(),
          "owner":forbidden_new_owner}
    monkeypatch.setattr(x,"load_root_source",lambda c:(
        f_ns,r,auth,b"current source"))
    monkeypatch.setattr(x,"read_existing_exact_claim",lambda *args:(
        original,{},record,failed))
    monkeypatch.setattr(x,"check_root_state",lambda *args:planned)
    monkeypatch.setattr(x.sys,"argv",[
        "resume.py","--candidate-sha","b"*40,"--preflight-only"])
    monkeypatch.setattr(x,"claim_one_use",lambda *args:pytest.fail(
        "read-only preflight must not claim one-use"))
    x.main()
    out=capsys.readouterr().out
    assert "P0_SAME_OWNER_AUTHORIZED_NATIVE_REVALIDATION_PREFLIGHT=PASS" in out
    assert "NO_NEW_APPROVAL_PROMPT_OR_PRODUCTION_MUTATION=true" in out
    assert not x.RECEIPT.exists()

def test_cli_once_uses_original_owner_claim_not_new_entra(
        tmp_path,monkeypatch,capsys):
    import contextlib
    r,original,record,failed,scope,f_ns,override,release,planned=check(
        tmp_path,monkeypatch)
    events=[]
    auth={"locks":lambda:contextlib.nullcontext(),
          "owner":lambda *args:pytest.fail("new Owner auth was called")}
    monkeypatch.setattr(x,"load_root_source",lambda c:(
        f_ns,r,auth,b"current source"))
    monkeypatch.setattr(x,"read_existing_exact_claim",lambda *args:(
        original,{},record,failed))
    monkeypatch.setattr(x,"check_root_state",
        lambda *args:(events.append("reviewed-exact-scope"),planned)[1])
    monkeypatch.setattr(x,"claim_one_use",
        lambda r,c,s:(events.append("root-oneuse-before-native"),
                    {"scope":s})[1])
    monkeypatch.setattr(x,"finish_native",
        lambda *args:events.append("root-native-verified"))
    monkeypatch.setattr(x.sys,"argv",[
        "resume.py","--candidate-sha","b"*40,
        "--resume-existing-exact-owner"])
    x.main()
    assert events==[
       "reviewed-exact-scope","reviewed-exact-scope",
       "root-oneuse-before-native","root-native-verified"]
    assert "P0_SAME_OWNER_AUTHORIZED_NATIVE_REVALIDATION_PREFLIGHT=PASS" in (
        capsys.readouterr().out)
    assert not x.RECEIPT.exists()

def test_resume_source_never_calls_new_owner_or_archiver():
    source=Path(x.__file__).read_text()
    assert 'auth["owner"]' not in source
    assert "devicecode" not in source
    assert "audit_journal_install.py" not in source
    assert "sudo" not in source
    assert "r.after_full_native_revalidation" in source
    assert "native_controller_started" in source
    assert "one_use_native_resume" in source
    assert "APPROVED_FINALIZER_SCOPE_SHA256" in source


def test_prior_auth_expiry_never_shorter_than_existing_full_integrity_ttl():
    assert x.PROOF_WINDOW_SECONDS==f.MAX_PROOF_AGE==30*3600
