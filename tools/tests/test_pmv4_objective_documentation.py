"""Fixed native documentation actions with disposable files and service ports."""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time

import pytest
from tools import pmv4_objective_documentation as docs
from tools.pmv4_teams_objective_admission import TeamsObjectiveDenied,canonical


@pytest.fixture
def native_case(tmp_path,monkeypatch):
    base=tmp_path/"publisher";base.mkdir()
    dropin=tmp_path/"dropins/20-reviewed-publisher.conf"
    work=tmp_path/"worktree";work.mkdir()
    generated=work/"docs/control";generated.mkdir(parents=True)
    (generated/"AUTOMATED-CHANGE-STATE.json").write_text(json.dumps(
        {"validated_source":{"revision":"a"*40}}))
    monkeypatch.setattr(docs,"PUBLISHER_BASE",base)
    monkeypatch.setattr(docs,"DROPIN",dropin)
    monkeypatch.setattr(docs,"WORKTREE",work)
    calls=[];state={"ActiveState":"inactive","ExecStart":"original","DropInPaths":""}
    job={"Result":"success","ExecMainStatus":"0","InvocationID":"old",
         "ExecMainStartTimestampMonotonic":"1"}
    def write(path,raw,mode=0o400,uid=0):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
        with os.fdopen(fd,"wb") as stream:stream.write(raw)
        path.chmod(mode)
    def systemctl(args):
        calls.append(args)
        if args==["daemon-reload"]:
            state["ExecStart"]=str(base/docs.PUBLISHER_SOURCE) if dropin.exists() else "original"
        if args==["start","--no-block",docs.UNIT]:
            job.update(InvocationID="new",ExecMainStartTimestampMonotonic=str(time.monotonic_ns()//1000))
    native=dict(directory=lambda p,*a:p.mkdir(mode=0o700,exist_ok=True),
        read=lambda p,*a:p.read_bytes(),write=write,props=lambda *a:state.copy(),
        systemctl=systemctl,run=lambda *a:"\n".join(k+"="+v for k,v in job.items()))
    actions=docs.DocumentationObjectiveActions(manifest={"candidate_sha":"a"*40,
        "step_arguments":{"candidate_sha":"a"*40,"scope_sha256":"b"*64,"manifest_sha256":"c"*64}},
        native=native,verify_source=lambda _:True,receipt_directory=tmp_path/"receipts",production=False)
    # This fixture covers action/recovery semantics; full protection preflight
    # is independently tested with real supplied source/identity ports.
    def preflight(*,after_restore=False):
        if after_restore:
            assert dropin.read_bytes()==docs.override_bytes()
            assert str(base/docs.PUBLISHER_SOURCE) in state["ExecStart"]
        else:assert not dropin.exists()
        return True
    monkeypatch.setattr(actions,"preflight",preflight)
    def claim(index):
        return dict(approval_id="planapproval-objective-"+"1"*32,plan_fingerprint="d"*64,
            step_index=index,claim_id=str(index)*64,
            step_material={"capability_name":(docs.RESTORE,docs.VERIFY)[index],
                           "arguments":actions.manifest["step_arguments"]})
    return actions,claim,calls,base,dropin,job


def test_two_steps_write_exact_override_and_native_acceptance(native_case):
    actions,claim,calls,base,dropin,job=native_case
    actions.execute(claim(0));result=actions.execute(claim(1))
    assert result["status"]=="verified"
    assert dropin.read_bytes()==docs.override_bytes()
    assert json.loads((base/"accepted.json").read_bytes())["authorization"]=="original_signed_teams_owner_objective"
    assert calls.count(["start","--no-block",docs.UNIT])==1
    assert actions.readback(claim(1))==result


def test_restore_crash_before_small_receipt_recovers_exact_root_configuration(native_case):
    actions,claim,calls,base,dropin,job=native_case
    actions.execute(claim(0))
    (actions.receipts/(claim(0)["claim_id"]+".json")).unlink()
    assert actions.readback(claim(0))["status"]=="verified"
    assert calls==[["daemon-reload"]]


def test_crash_after_native_job_before_acceptance_recovers_without_restart(native_case,monkeypatch):
    actions,claim,calls,base,dropin,job=native_case
    actions.execute(claim(0))
    finish=actions._finish_verified_job
    monkeypatch.setattr(actions,"_finish_verified_job",
        lambda c:(_ for _ in ()).throw(SystemExit("synthetic stop before receipt")))
    with pytest.raises(SystemExit):actions.execute(claim(1))
    assert not (base/"accepted.json").exists()
    monkeypatch.setattr(actions,"_finish_verified_job",finish)
    assert actions.readback(claim(1))["status"]=="verified"
    assert calls.count(["start","--no-block",docs.UNIT])==1


def test_old_success_cannot_satisfy_a_new_claim_without_started_phase(native_case):
    actions,claim,calls,base,dropin,job=native_case
    actions.execute(claim(0))
    with pytest.raises(FileNotFoundError):actions.readback(claim(1))
    assert not (base/"accepted.json").exists()


def test_failed_native_job_never_creates_acceptance_and_cannot_restart(native_case):
    actions,claim,calls,base,dropin,job=native_case
    actions.execute(claim(0));job["Result"]="exit-code";job["ExecMainStatus"]="1"
    with pytest.raises(TeamsObjectiveDenied,match="NOT_VERIFIED"):actions.execute(claim(1))
    with pytest.raises(TeamsObjectiveDenied,match="ALREADY_CLAIMED"):actions.execute(claim(1))
    assert not (base/"accepted.json").exists()
    assert calls.count(["start","--no-block",docs.UNIT])==1


def test_failed_restore_rolls_back_only_its_own_exact_override(native_case,monkeypatch):
    actions,claim,calls,base,dropin,job=native_case
    preflight=actions.preflight
    def fail(*,after_restore=False):
        if after_restore:raise RuntimeError("synthetic failed verification")
        return preflight()
    monkeypatch.setattr(actions,"preflight",fail)
    with pytest.raises(RuntimeError):actions.execute(claim(0))
    assert not dropin.exists() and not dropin.parent.exists()
    assert calls==[["daemon-reload"],["daemon-reload"]]


@pytest.fixture
def preflight_case(native_case,monkeypatch):
    actions,claim,calls,base,dropin,job=native_case
    monkeypatch.undo()
    # Restore only the test-specific constants; exercise actual preflight.
    monkeypatch.setattr(docs,"PUBLISHER_BASE",base)
    monkeypatch.setattr(docs,"DROPIN",dropin)
    work=base.parent/"worktree"
    monkeypatch.setattr(docs,"WORKTREE",work)
    repository=Path(__file__).resolve().parents[2]
    files={}
    manifest=actions.manifest
    manifest["protected_peers"]={"protected":{"id":"exact-before-image"}}
    peers=deepcopy(manifest["protected_peers"])
    for path,field in (
        (Path("/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json"),"engineering_pause_sha256"),
        (Path("/usr/local/lib/jason/release_host_reconcile_worker.py"),"shared_worker_sha256")):
        files[path]=str(path).encode()
        manifest[field]=sha256(files[path]).hexdigest()
    native_root=base.parent/"test-native"
    manifest["accepted_native_files_sha256"]={}
    actions.native["NATIVE"]=native_root
    for index in range(64):
        name="code-"+str(index)
        raw=("unchanged accepted code "+name).encode()
        files[native_root/name]=raw
        manifest["accepted_native_files_sha256"][name]=sha256(raw).hexdigest()
    for field in ("freeze","hold","root_policy","stage_e_marker"):
        path=base.parent/(field+".json")
        raw=(field+" exact bytes").encode()
        manifest[field+"_path"]=str(path)
        manifest[field+"_sha256"]=sha256(raw).hexdigest()
        files[path]=raw
    unit=Path("/etc/systemd/system")/docs.UNIT
    files[unit]=b"exact original unit"
    manifest["original_unit_sha256"]=sha256(files[unit]).hexdigest()
    for name in docs.PAYLOAD:
        files[base/docs.PUBLISHER_SOURCE/name]=(repository/name).read_bytes()
    control={"circuit_breaker":{"state":"closed"}}
    drift={"status":"pass","problems":[],"observed_at":datetime.now(timezone.utc).isoformat()}
    dirty=False
    def read(path,*args):
        if path==docs.MANAGER/"production-control-state.json":return canonical(control)
        if path==docs.MANAGER/"production-drift.json":return canonical(drift)
        return files[path]
    def git(path,*args):
        return ("dirty" if dirty else "") if args[0]=="status" else "same-common-git-dir"
    actions.native.update(read=read,peers=lambda:peers,git=git)
    return actions,manifest,files,control,drift,peers


def test_full_native_preflight_accepts_unchanged_source_and_protections(preflight_case):
    assert preflight_case[0].preflight()


@pytest.mark.parametrize("change",["source","peer","policy","breaker","drift","stale"])
def test_full_native_preflight_denies_changed_independent_gate(preflight_case,change):
    actions,m,files,control,drift,peers=preflight_case
    if change=="source":actions.verify_source=lambda _:False
    if change=="peer":peers["protected"]["id"]="different"
    if change=="policy":files[Path(m["root_policy_path"])]=b"changed policy"
    if change=="breaker":control["circuit_breaker"]["state"]="open"
    if change=="drift":drift["status"]="drift_detected"
    if change=="stale":drift["observed_at"]="2020-01-01T00:00:00+00:00"
    with pytest.raises(TeamsObjectiveDenied):actions.preflight()
