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
