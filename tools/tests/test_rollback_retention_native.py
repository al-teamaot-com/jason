from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tarfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools import rollback_retention_native as n, rollback_retention_plan as p

POLICY=json.loads((Path(__file__).resolve().parents[2]/"config/operations/rollback-retention-v1.json").read_bytes())
NOW=datetime(2026,11,27,tzinfo=timezone.utc)

def row(index, day="10"):
    return {"Name":"/jason-runtime-rollback-202611"+day+"T120000Z",
            "Id":format(index,"064x"),"Image":"sha256:"+"a"*64,
             "State":{"Status":"exited","Running":False,"Pid":0,
                     "FinishedAt":"2026-11-"+day+"T12:00:00Z"},
            "Config":{"Labels":{"com.teamaot.jason.source_revision":"b"*40}},
            "HostConfig":{"AutoRemove":False},"Mounts":[{"Type":"bind","Source":"/test","Destination":"/data"}],
            "SizeRw":100,"SizeRootFs":1000}

@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setattr(n,"now",lambda:NOW)
    rows=[row(1),row(2,"12")]
    index={x["Name"][1:]:x for x in rows}
    plan=p.choose(rows,inventory=sorted(index),maximum=2,free_slots=1,now=NOW,policy=POLICY)
    plan["before_ids"]={k:v["Id"] for k,v in index.items()}
    return index,plan

def test_exact_inventory_only_approved_absence_and_id(fixture):
    rows,plan=fixture
    assert n.verify_inventory(plan,sorted(rows),rows,vars(p),POLICY)==[]
    target=plan["retirements"][0]["target"]["name"]
    sibling=plan["retirements"][0]["retained_siblings"][0]["name"]
    after={sibling:rows[sibling]}
    assert n.verify_inventory(plan,sorted(after),after,vars(p),POLICY)==[target]
    with pytest.raises(PermissionError):
        n.verify_inventory(plan,[target],{target:rows[target]},vars(p),POLICY)
    foreign=deepcopy(after);foreign[sibling]["Id"]="e"*64
    with pytest.raises(PermissionError,match="CONTAINER_ID_CHANGED"):
        n.verify_inventory(plan,sorted(foreign),foreign,vars(p),POLICY)
    changed=deepcopy(after);changed[sibling]["Config"]["Env"]=["OTHER=1"]
    with pytest.raises(PermissionError,match="METADATA_CHANGED"):
        n.verify_inventory(plan,sorted(changed),changed,vars(p),POLICY)

def test_reference_scan_rejects_new_dependencies_and_only_skips_current_record(tmp_path,fixture):
    _,plan=fixture;d=plan["retirements"][0]["target"]
    own=tmp_path/"active";own.mkdir()
    (own/"approval.json").write_text(json.dumps({"target":d["id"]}))
    assert n.scan_references(vars(p),[d],roots=(tmp_path,))=={d["id"]}
    assert n.scan_references(vars(p),[d],roots=(tmp_path,),current_record=own)==set()
    (tmp_path/"foreign.json").write_text(json.dumps({"rollback_id":d["id"]}))
    assert n.scan_references(vars(p),[d],roots=(tmp_path,),current_record=own)=={d["id"]}

def test_historical_exemption_never_exempts_active_rollback_id(tmp_path,fixture,monkeypatch):
    _,plan=fixture;d=plan["retirements"][0]["target"]
    audit=tmp_path/"audit";private=audit/"private";private.mkdir(parents=True)
    monkeypatch.setattr(n,"AUDIT",audit)
    x={"scope":{"rollback_container_capacity_before":{"existing_names":[d["name"]]}}}
    path=private/"plan.json";path.write_text(json.dumps(x))
    assert n.scan_references(vars(p),[d],roots=(private,),historical_audit_accepted=True)==set()
    assert n.scan_references(vars(p),[d],roots=(private,),historical_audit_accepted=False)=={d["id"]}
    x["rollback"]={"container_id":d["id"]};path.write_text(json.dumps(x))
    assert n.scan_references(vars(p),[d],roots=(private,),historical_audit_accepted=True)=={d["id"]}

def test_stopped_inventory_detects_duplicate_or_missing_rows():
    command=Mock(side_effect=[b"jason-runtime-rollback-20261110T120000Z\n",b"[]"])
    with pytest.raises(PermissionError,match="EXACT_INVENTORY"):
        n.all_stopped(command,["jason-runtime-rollback-"])
    command=Mock(return_value=b"jason-runtime-rollback-20261110T120000Z\njason-runtime-rollback-20261110T120000Z\n")
    with pytest.raises(PermissionError,match="STOPPED_INVENTORY"):
        n.all_stopped(command,["jason-runtime-rollback-"])

# The archive filesystem path is tested as root ONLY in a disposable fixture
# with no production mounts, no Docker socket and no network. The Docker export
# command itself is mocked; a valid synthetic tar is streamed to the actual
# private file and read back using the production verification code.
@pytest.mark.skipif(os.environ.get("JASON_DISPOSABLE_NATIVE_FIXTURE")!="1" or os.geteuid()!=0,
                    reason="requires isolated root filesystem fixture")
def test_real_private_archive_and_faults(tmp_path,fixture,monkeypatch):
    rows,plan=fixture;ret=plan["retirements"][0]
    def sync(d):
        fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def write(path,raw,mode):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        with os.fdopen(fd,"wb") as f:
            f.write(raw);f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
        sync(path.parent)
    native={"sync_dir":sync,"write":write}
    def export(args,stdout,**kwargs):
        assert args[-3:]==[n.DOCKER,"export",ret["target"]["id"]]
        with tarfile.open(fileobj=stdout,mode="w|") as t:
            raw=b"synthetic archive fixture"
            m=tarfile.TarInfo("fixture.txt");m.size=len(raw);t.addfile(m,io.BytesIO(raw))
        return SimpleNamespace(returncode=0)
    mock=Mock(side_effect=export);monkeypatch.setattr(n.subprocess,"run",mock)
    directory=tmp_path/"approved-target";scope="c"*64;maximum=POLICY["maximum_archive_bytes_per_container"]
    a=n.archive_exact(native,vars(p),directory,scope,ret,rows[ret["target"]["name"]],maximum)
    assert a["rootfs"]["members"]==1 and mock.call_count==1
    assert n.archive_exact(native,vars(p),directory,scope,ret,rows[ret["target"]["name"]],maximum)==a
    assert mock.call_count==1
    assert (directory/"rootfs.tar").stat().st_mode&0o777==0o400
    with pytest.raises(PermissionError):
        n.archive_proof(native,vars(p),directory,"d"*64,ret,maximum)
    path=directory/"container-inspect.json";path.chmod(0o600);path.write_bytes(b"{}");path.chmod(0o400)
    with pytest.raises(PermissionError):
        n.archive_proof(native,vars(p),directory,scope,ret,maximum)
    # Failed or malformed export cannot produce an archive approval receipt.
    monkeypatch.setattr(n.subprocess,"run",Mock(return_value=SimpleNamespace(returncode=1)))
    other=tmp_path/"failed"
    with pytest.raises(PermissionError,match="EXPORT_FAILED"):
        n.archive_exact(native,vars(p),other,scope,ret,rows[ret["target"]["name"]],maximum)
    assert not (other/"archive.json").exists()
    assert not (other/"rootfs.tar").exists()

def test_no_native_operation_without_root_and_isolation(monkeypatch):
    monkeypatch.setattr(n.os,"geteuid",lambda:1000)
    with pytest.raises(PermissionError,match="ROOT_ISOLATED_REQUIRED"):
        n.run_action(SimpleNamespace(),{}, {}, {}, {}, None,None,None)


@pytest.mark.parametrize("fault", ["approval", "archive", "references", "health", "identity", "source", None])
def test_removal_is_strictly_after_exact_approval_archive_and_fresh_identity(fixture,monkeypatch,tmp_path,fault):
    rows,plan=fixture
    plan["prefixes"]=["jason-runtime-rollback-"]
    retirement=plan["retirements"][0];d=retirement["target"]
    record=tmp_path/"record";record.mkdir()
    scope={"action":n.ACTION,"plan":plan}
    sha=n.digest(scope)
    approval={"scope":scope,"scope_sha256":sha,"approved_at":NOW.isoformat(),
              "owner_oid":"bee80bdc-ffb0-4c50-b453-c09d4d411f5f"}
    if fault=="approval":approval["owner_oid"]="wrong"
    monkeypatch.setattr(n,"read",lambda *a,**k:n.canonical(approval))
    events=[]
    def archive(*args):
        events.append("archive")
        if fault=="archive":raise PermissionError("bad archive")
        return {"scope_sha256":sha}
    monkeypatch.setattr(n,"archive_proof",archive)
    monkeypatch.setattr(n,"audit_accepted",lambda:True)
    def references(*a,**kw):
        events.append("refs")
        return {d["id"]} if fault=="references" else set()
    monkeypatch.setattr(n,"scan_references",references)
    active=deepcopy(rows)
    def inv(*args):
        events.append("inventory")
        if fault=="identity" and events.count("inventory")>=2:
            active[d["name"]]["Config"]["Env"]=["CHANGED=1"]
        return sorted(active),active
    monkeypatch.setattr(n,"all_stopped",inv)
    def current():
        events.append("source")
        if fault=="source":raise PermissionError("source advanced")
    def health():
        events.append("health");return fault!="health"
    def command(args):
        if args[1:3]==["image","inspect"]:
            events.append("image");return d["image"].encode()
        if args[1]=="rm":
            assert args==[n.DOCKER,"rm",d["id"]]
            assert events==["archive","inventory","source","health","refs","image","inventory"]
            events.append("remove");del active[d["name"]]
            return b""
        if args[1:3]==["ps","-a"]:
            events.append("readback")
            return "\n".join(x["Id"]+"|"+name for name,x in active.items()).encode()
        raise AssertionError("unexpected command")
    monkeypatch.setattr(n,"immutable_record",lambda *a,**k:events.append("receipt"))
    invoke=lambda:n.retire_archived_exact({},command,vars(p),POLICY,record,tmp_path/"archive",
                                         sha,plan,retirement,current,health)
    if fault is not None:
        with pytest.raises(PermissionError):invoke()
        assert "remove" not in events
        assert "receipt" not in events
    else:
        invoke()
        assert events[-3:]==["remove","readback","receipt"]
        assert d["name"] not in active
        # Exact continuation after interruption verifies archive/absence,
        # without issuing a second removal.
        events.clear();invoke()
        assert events==["archive","inventory","readback","receipt"]


def test_completed_active_offer_is_bound_without_removing_history(tmp_path):
    from types import SimpleNamespace
    from tools import rollback_retention_native as native

    prior = "release-" + "a" * 16
    next_release = "release-" + "b" * 16
    manifest = {"release_id": prior, "scope_sha256": "a" * 64}
    offer = {"manifest": manifest}
    location = tmp_path / "transactions"
    location.mkdir()
    journal_path = location / (prior + ".json")
    journal_path.write_text("{}")
    journal = {"release_id": prior, "scope_sha256": "a" * 64,
               "manifest_sha256": native.digest(manifest), "outcome": "production_components_verified"}
    host = SimpleNamespace(active_staged_offer=lambda: offer, PRIVATE=tmp_path, root_json=lambda _: journal)
    before = native.completed_active_offer(host, next_release)
    assert before["outcome"] == "production_components_verified"
    assert before["offer_sha256"] == native.digest(offer)
    assert journal_path.is_file()
    with pytest.raises(PermissionError, match="ACTIVE_OFFER_EXISTS"):
        native.completed_active_offer(host, prior)
    journal["outcome"] = "rollback_unverified"
    with pytest.raises(PermissionError, match="ACTIVE_OFFER_UNRESOLVED"):
        native.completed_active_offer(host, next_release)
    journal["outcome"] = "rollback_verified"
    journal["scope_sha256"] = "b" * 64
    with pytest.raises(PermissionError, match="ACTIVE_OFFER_UNRESOLVED"):
        native.completed_active_offer(host, next_release)

RESERVATION = json.loads((Path(__file__).resolve().parents[2]/"config/operations/rollback-capacity-reservation-v1.json").read_bytes())

def test_reservation_prefers_existing_capacity_and_verified_duplicate_archival():
    rows=[row(1),row(2,"12")]; names=sorted(r["Name"][1:] for r in rows); mapping={r["Name"][1:]:r for r in rows}
    for limit in (2,3):
        with pytest.raises(PermissionError,match="USE_EXISTING_CAPACITY_OR_ARCHIVAL"):
            n.reservation_plan(vars(p),RESERVATION,POLICY,{"max_stopped_rollback_containers":limit},names,mapping,1,set())
    rows[1]["Image"]="sha256:"+"c"*64
    assert n.reservation_plan(vars(p),RESERVATION,POLICY,{"max_stopped_rollback_containers":2},names,mapping,1,set())=={"max_stopped_rollback_containers":3}

def test_reservation_inventory_digest_covers_configuration_without_exposing_values():
    r=row(1); name=r["Name"][1:]; rows={name:r}; first=n.inventory_digest(vars(p),[name],rows)
    r["Config"]["Env"]=["FIXTURE=changed"]
    second=n.inventory_digest(vars(p),[name],rows)
    assert first!=second and len(first)==len(second)==64

@pytest.mark.parametrize("fault",["none","scope","owner","source","inventory","drift","resume-before","resume-after"])
def test_reservation_reuses_exact_native_approval_and_atomic_policy_rollback(tmp_path,monkeypatch,capsys,fault):
    from contextlib import nullcontext
    monkeypatch.setattr(n,"now",lambda:NOW)
    ledger=tmp_path/"reservation"; policy_path=tmp_path/"desired.json"
    monkeypatch.setattr(n,"RESERVATION_LEDGER",ledger); monkeypatch.setattr(n,"DESIRED",policy_path)
    # These fixtures model root custody; root permission and atomic compare-and-replace
    # are covered by the existing native file/recovery fixtures. No Docker or network.
    monkeypatch.setattr(n,"private_directory",lambda path,native,create=False: path.mkdir(exist_ok=True) if create else None)
    monkeypatch.setattr(n,"read",lambda path,**kw:path.read_bytes())
    def write(path,raw,mode):
        assert not path.exists(); path.write_bytes(raw)
    monkeypatch.setattr(n,"reservation_space",lambda *a:None)
    monkeypatch.setattr(n,"scan_references",lambda *a,**kw:set())
    monkeypatch.setattr(n,"completed_active_offer",lambda *a:{"outcome":"production_components_verified"})
    desired={"schema_version":"1.0","rollback_container_prefixes":["jason-runtime-rollback-"],"max_stopped_rollback_containers":2,"unrelated":{"preserved":True}}
    before=n.canonical(desired); policy_path.write_bytes(before)
    rows=[row(1),row(2,"12")]; rows[1]["Image"]="sha256:"+"c"*64
    inv={r["Name"][1:]:r for r in rows}; names=sorted(inv)
    monkeypatch.setattr(n,"all_stopped",lambda *a:(names,inv))
    def state(*a):
        raw=policy_path.read_bytes();return json.loads(raw),{"desired_policy_sha256":n.digest(raw),"components":{"fixture":"same"}}
    monkeypatch.setattr(n,"state",state)
    m={"release_id":"release-"+"a"*16,"rollback_sha":"b"*40,"scope_sha256":"c"*64,"targets":[{},{}]}
    calls=[]
    def gate():calls.append("native_gate"); assert json.loads(policy_path.read_bytes())["max_stopped_rollback_containers"]==4
    host=SimpleNamespace(release_lock=lambda m:nullcontext(),ensure_breaker_closed_and_workers_quiescent=gate)
    args=SimpleNamespace(candidate="d"*40,release_id=m["release_id"],apply=False,resume=False,scope_sha=None)
    code={n.RESERVATION_CONFIG:n.canonical(RESERVATION)}; hashes={k:n.digest(v) for k,v in code.items()}
    def command(a):
        if "ls-remote" in a:return (args.candidate+" refs/heads/main\n").encode()
        assert "production_drift_guard.py" in a[-3]
        return n.canonical({"status":"drift_detected" if fault=="drift" else "pass","problems":[]})
    def owner(scope):
        calls.append("owner")
        if fault=="inventory": rows[0]["Config"]["Env"]=["CHANGED=1"]
        return "wrong" if fault=="owner" else "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
    def replace(old,new):
        assert policy_path.read_bytes()==old; calls.append("replace");policy_path.write_bytes(new)
    def run():
        return n.run_reservation(args,{"write":write,"owner":owner},
            {"read":lambda path,*a:path.read_bytes(),"command":command,"USER":[]},code,vars(p),None,
            lambda:({} if fault=="source" and args.apply else code),lambda:None,host,m,"e"*40,None,
            POLICY,hashes,replace,lambda *a:None)
    run(); offer=json.loads(capsys.readouterr().out); scope=offer["scope"]; args.scope_sha=offer["scope_sha256"]
    assert not ledger.exists() and policy_path.read_bytes()==before and not calls
    assert scope["plan"]["after_limit"]==4 and not scope["container_image_volume_removal_allowed"]
    args.apply=True
    if fault=="scope":args.scope_sha="f"*64
    record=ledger/args.candidate/args.release_id
    if fault.startswith("resume"):
        record.mkdir(parents=True); (record/"before-policy.json").write_bytes(before)
        (record/"approval.json").write_bytes(n.canonical({"scope":scope,"scope_sha256":args.scope_sha,"owner_oid":"bee80bdc-ffb0-4c50-b453-c09d4d411f5f","approved_at":NOW.isoformat()}))
        args.apply=False;args.resume=True
        if fault=="resume-after":policy_path.write_bytes((json.dumps({**desired,"max_stopped_rollback_containers":4},sort_keys=True,indent=2)+"\n").encode())
    if fault in ("scope","owner","source","inventory","drift"):
        with pytest.raises(PermissionError):run()
        assert policy_path.read_bytes()==before
        if fault=="drift":assert json.loads((record/"result.json").read_text())["status"]=="rollback_capacity_reservation_rolled_back"
        else:assert "replace" not in calls
    else:
        run(); result=json.loads(capsys.readouterr().out)
        assert result["status"]=="rollback_capacity_reservation_verified" and result["removed"]==0
        assert json.loads(policy_path.read_bytes())=={**desired,"max_stopped_rollback_containers":4}
        assert json.loads((record/"result.json").read_text())==result
        assert calls.count("owner")==int(fault=="none") and calls.count("replace")==int(fault!="resume-after")
        args.resume=True; args.apply=False
        with pytest.raises(PermissionError,match="ALREADY_RESOLVED"):run()

@pytest.mark.parametrize("limit,targets,duplicate,expected",[(3,1,False,"capacity_available"),(2,1,True,"duplicate_archival_available"),(2,2,False,"reservation_review_required"),(29,2,False,"capacity_available")])
def test_capacity_assessment_distinguishes_safe_options(limit,targets,duplicate,expected):
    rows=[row(1),row(2,"12")]
    if not duplicate:rows[1]["Image"]="sha256:"+"c"*64
    inv={r["Name"][1:]:r for r in rows}
    result=n.capacity_report(vars(p),POLICY,RESERVATION,{"max_stopped_rollback_containers":limit},sorted(inv),inv,targets,set())
    assert result["status"]==expected and result["available_slots"]==limit-2
    assert ("proposed_limit" in result)==(expected=="reservation_review_required")

def test_capacity_assessment_reports_ceiling_without_granting_more_slots():
    rows=[row(1),row(2,"12")];rows[1]["Image"]="sha256:"+"c"*64
    inv={r["Name"][1:]:r for r in rows}
    result=n.capacity_report(vars(p),POLICY,{**RESERVATION,"maximum_stopped_rollback_containers":2},{"max_stopped_rollback_containers":2},sorted(inv),inv,2,set())
    assert result["status"]=="capacity_policy_review_required" and "proposed_limit" not in result
