"""Provider-free exact retirement/recovery fault injection; no real host writes."""
from copy import deepcopy
from pathlib import Path
import json

import pytest

from tools import deploy_live_container as policy
from tools import audit_journal_container_release as contract
from tools import no_paid_ai_first_transition as first

OLD="a"*64
NEW="b"*64
IMG="sha256:"+"c"*64


def before(role):
    mounts=[{"Type":"bind","Source":"/private/paid","Target":p,"ReadOnly":True}
            for p in sorted(policy.CREDENTIAL_MOUNTS)] + [
        {"Type":"bind","Source":"/canonical/state","Target":"/var/lib/jason","ReadOnly":False}]
    return {"Name":"/"+role,"Id":OLD,"Image":IMG,
            "Config":{"User":"1000:1000","Image":"old-tag","Env":[
                "JASON_SOURCE_REVISION="+"d"*40,
                *[k+"=true" for k in policy.FLAGS],
                *[k+"=old-paid-model" for k in policy.PAID_MODEL_SELECTORS],
                "JASON_OTHER_PROVIDER_PROFILE=preserved"],
                "Cmd":["python","-m","jason_runtime.ticket_worker_service"],"Volumes":None,
                "Labels":{"com.teamaot.jason.source_revision":"d"*40}},
            "HostConfig":{"Privileged":False,"AutoRemove":False,"ReadonlyRootfs":True,
                "CapDrop":["ALL"],"SecurityOpt":["no-new-privileges:true"],
                "RestartPolicy":{"Name":"unless-stopped","MaximumRetryCount":0},
                "Memory":2147483648,"NanoCpus":1000000000,"PidsLimit":256,
                "Mounts":mounts,"Binds":None,"VolumesFrom":None},
            "Mounts":[{"Type":m["Type"],"Source":m["Source"],"Destination":m["Target"],"RW":not m["ReadOnly"]}
                      for m in mounts],
            "NetworkSettings":{"Networks":{"jason-core":{"IPAMConfig":None,"Aliases":[],"GwPriority":0}}},
            "State":{"Running":True,"StartedAt":"2026-11-26T21:00:00Z"}}


class Engine:
    def __init__(self, old, fail=None):
        self.objects={old["Id"]:deepcopy(old)}
        self.calls=[];self.fail=fail
    def lookup(self, ref, required=False):
        rows=[v for k,v in self.objects.items() if k==ref or v["Name"]=="/"+ref]
        if required: assert len(rows)==1
        return deepcopy(rows[0]) if rows else None
    def call(self,method,path,body=None,**kw):
        self.calls.append((method,path))
        op=path.split("?")[0].rsplit("/",1)[-1]
        if "/containers/create?" in path:
            role=path.split("name=")[1]
            assert not self.lookup(role)
            assert body["Image"]==IMG
            h=deepcopy(body["HostConfig"])
            self.objects[NEW]={"Id":NEW,"Name":"/"+role,"Image":IMG,
                "Config":{k:deepcopy(v) for k,v in body.items() if k not in ("HostConfig","NetworkingConfig")},
                "HostConfig":h,
                "Mounts":[{"Type":m["Type"],"Source":m["Source"],"Destination":m["Target"],"RW":not m.get("ReadOnly",False)} for m in h["Mounts"]],
                "NetworkSettings":{"Networks":deepcopy(body["NetworkingConfig"]["EndpointsConfig"])},
                "State":{"Running":False}}
            result={"Id":NEW}
        else:
            id=path.split("/")[2].split("?")[0];obj=self.objects[id]
            if method=="DELETE":
                assert not obj["State"]["Running"] and "v=false&force=false" in path
                del self.objects[id]
            elif op=="update": obj["HostConfig"]["RestartPolicy"]=deepcopy(body["RestartPolicy"])
            elif op=="rename": obj["Name"]="/"+path.split("name=")[1]
            elif op=="stop": obj["State"]["Running"]=False
            elif op=="start":
                assert id!=OLD
                policy.validate_no_paid_container(obj)
                obj["State"]["Running"]=True
            else: raise AssertionError(path)
            result={}
        if self.fail==op:
            self.fail=None
            raise OSError("synthetic lost response after native action")
        return result


def row_for(old, body):
    return {"original_id":old["Id"],"image_id":old["Image"],
            "baseline_sha256":first.digest(policy.release_evidence(old)),
            "original_config_sha256":first.digest(old["Config"]),
            "configuration_sha256":first.digest(body),
            "rollback_configuration_sha256":first.digest(body)}


@pytest.mark.parametrize("role",first.ORDER)
def test_same_image_projection_and_forward_recovery(role):
    old=before(role);body=first.body_for(old,policy,contract)
    env=dict(x.split("=",1) for x in body["Env"])
    assert all(env[k]=="false" for k in policy.FLAGS)
    assert all(env[k]=="" for k in policy.PAID_MODEL_SELECTORS)
    assert body["Image"]==old["Image"]
    assert body["Cmd"]==old["Config"]["Cmd"]
    assert body["Labels"]==old["Config"]["Labels"]
    assert {k:v for k,v in body["HostConfig"].items() if k!="Mounts"}=={
        k:v for k,v in old["HostConfig"].items() if k!="Mounts"}
    assert len(body["HostConfig"]["Mounts"])==1
    assert env["JASON_OTHER_PROVIDER_PROFILE"]=="preserved"
    e=Engine(old); phases=[]
    actual=first.run_transition(e,policy,contract,role,row_for(old,body),body,
                                lambda r,p:phases.append(p),lambda r,b,c:None)
    assert actual==NEW and e.lookup(OLD) is None
    assert first.compliant(e.lookup(role),body,policy,contract)
    assert phases[-1]=="healthy_compliant"
    assert e.lookup(role)["HostConfig"]["RestartPolicy"]["Name"]=="unless-stopped"
    assert all(OLD not in p for m,p in e.calls if "/start" in p)
    assert e.calls[0][1].endswith("/update")
    assert "/rename?" in e.calls[1][1]
    assert "/stop?" in e.calls[2][1]
    # Reentry is no-op; only the compliant replacement can be running.
    calls=len(e.calls)
    assert first.transition(e,policy,contract,role,OLD,body,lambda *a:None)==NEW
    assert len(e.calls)==calls


@pytest.mark.parametrize("lost",("update","rename","stop",OLD,"create","start"))
def test_lost_response_at_every_native_boundary(lost):
    role=first.ORDER[0];old=before(role);body=first.body_for(old,policy,contract)
    e=Engine(old,fail=lost)
    first.run_transition(e,policy,contract,role,row_for(old,body),body,
                         lambda *a:None,lambda *a:None)
    assert e.lookup(OLD) is None and e.lookup(role)["State"]["Running"]
    assert all(OLD not in p for _,p in e.calls if "/start" in p)


@pytest.mark.parametrize("phase",("update","rename","stop"))
def test_process_interruption_retirement_is_scope_bound(phase):
    role=first.ORDER[-1];old=before(role);body=first.body_for(old,policy,contract);row=row_for(old,body)
    e=Engine(old,fail=phase)
    with pytest.raises(OSError):
        first.transition(e,policy,contract,role,OLD,body,lambda *a:None)
    retired=e.lookup(OLD,required=True)
    first.predecessor_evidence(retired,role,row,body,policy,recovery=True)
    assert retired["HostConfig"]["RestartPolicy"]["Name"]=="no"
    if phase in ("rename","stop"):
        assert e.lookup(role) is None
    first.transition(e,policy,contract,role,OLD,body,lambda *a:None)
    assert e.lookup(OLD) is None
    assert first.compliant(e.lookup(role),body,policy,contract)


@pytest.mark.parametrize("change",("flag","model","credential","extra_mount","wrong_image"))
def test_unsafe_or_unreviewed_successor_cannot_start(change):
    role=first.ORDER[0];old=before(role);body=first.body_for(old,policy,contract)
    e=Engine(old)
    if change=="flag":
        body["Env"]=[x.replace(policy.FLAGS[0]+"=false",policy.FLAGS[0]+"=true") for x in body["Env"]]
    elif change=="model":
        body["Env"]=[x.replace(policy.PAID_MODEL_SELECTORS[0]+"=",policy.PAID_MODEL_SELECTORS[0]+"=paid") for x in body["Env"]]
    elif change=="credential":
        body["Env"].append("OPENAI_API_KEY=synthetic")
    elif change=="extra_mount":
        body["HostConfig"]["Mounts"].append({"Type":"bind","Source":"/private/secret","Target":"/run/jason-secrets/openbao","ReadOnly":True})
    else: body["Image"]="sha256:"+"e"*64
    with pytest.raises(PermissionError):
        first.transition(e,policy,contract,role,OLD,body,lambda *a:None)
    assert not e.calls


def test_failed_health_never_restores_paid_predecessor():
    role=first.ORDER[0];old=before(role);body=first.body_for(old,policy,contract)
    e=Engine(old)
    def fail(*a): raise first.TransitionDenied("synthetic health failure")
    with pytest.raises(first.TransitionDenied,match="health"):
        first.run_transition(e,policy,contract,role,row_for(old,body),body,lambda *a:None,fail)
    assert e.lookup(OLD) is None and first.compliant(e.lookup(role),body,policy,contract)
    assert all(OLD not in p for _,p in e.calls if "/start" in p)


def test_foreign_container_and_extra_mount_rejected():
    role=first.ORDER[0];old=before(role);body=first.body_for(old,policy,contract)
    e=Engine(old);e.objects.clear()
    e.call("POST","/containers/create?name="+role,body)
    e.objects[NEW]["Mounts"].append({"Type":"bind","Source":"/foreign","Destination":"/foreign","RW":False})
    with pytest.raises(first.TransitionDenied,match="SUCCESSOR_CONFIGURATION"):
        first.transition(e,policy,contract,role,OLD,body,lambda *a:None)
    assert not any("/start" in p for _,p in e.calls)


def test_unsafe_old_scope_change_rejected_in_recovery():
    role=first.ORDER[0];old=before(role);body=first.body_for(old,policy,contract)
    row=row_for(old,body)
    old["HostConfig"]["Memory"]=0
    with pytest.raises(first.TransitionDenied,match="PREDECESSOR_SCOPE_CHANGED"):
        first.predecessor_evidence(old,role,row,body,policy,recovery=True)


def test_root_entrypoint_refuses_unprivileged_source(monkeypatch):
    monkeypatch.setattr(first.os,"geteuid",lambda:1000)
    with pytest.raises(first.TransitionDenied,match="ROOT_ISOLATED"):
        first.sources("a"*40)

def test_recovery_requires_only_exact_transition_drift(monkeypatch):
    old=before(first.ORDER[0]);body=first.body_for(old,policy,contract)
    row=row_for(old,body);e=Engine(old,fail="rename")
    with pytest.raises(OSError):
        first.transition(e,policy,contract,first.ORDER[0],OLD,body,lambda *a:None)
    lkg={"revision":first.LKG,"runtime_image_id":IMG,"mcp_image_id":IMG}
    control={"last_known_good":{"manifest":{**lkg,"complete":True,
               "runtime_revision":first.LKG,"mcp_revision":first.LKG,"host_revision":first.LKG}},
             "circuit_breaker":{"state":"open","reason":"continuous_production_drift_detected"}}
    drift={"status":"drift_detected","problems":[
        {"kind":"required_container_not_running","container":first.ORDER[0]},
        {"kind":"undeclared_running_container","container":first.retired_name(first.ORDER[0],OLD)}]}
    monkeypatch.setattr(first,"read_file",lambda p,*a,**k:first.canon(control if p.name=="production-control-state.json" else drift))
    monkeypatch.setattr(first,"live_drift",lambda:drift)
    scope={"lkg":lkg,"components":{first.ORDER[0]:row}}
    assert first.recovery_gate(scope,e)=="open"
    drift["problems"].append({"kind":"required_system_unit_not_active","unit":"unrelated"})
    with pytest.raises(first.TransitionDenied,match="UNRELATED_RECOVERY_DRIFT"):
        first.recovery_gate(scope,e)
    control["circuit_breaker"]["reason"]="different_incident"
    with pytest.raises(first.TransitionDenied,match="RECOVERY_BREAKER_NOT_TRANSITION_BOUND"):
        first.recovery_gate(scope,e)

def test_native_in_memory_module_load_sets_relative_import_scope(monkeypatch):
    import sys,types
    parent=types.ModuleType("no_paid_fixture_package");parent.__path__=[]
    monkeypatch.setitem(sys.modules,parent.__name__,parent)
    monkeypatch.setitem(sys.modules,parent.__name__+".sibling",types.SimpleNamespace(value=42))
    name=parent.__name__+".consumer"
    try:
        m=first.module(name,b"from .sibling import value",Path("/reviewed/consumer.py"))
        assert m.value==42
    finally:
        sys.modules.pop(name,None)

@pytest.mark.parametrize("rc,status,problems,accepted",[
    (0,"pass",[],True),
    (2,"drift_detected",[{"kind":"required_container_not_running","container":"jason-runtime"}],True),
    (1,"pass",[],False),
    (2,"pass",[],False),
    (0,"drift_detected",[{"kind":"test"}],False),
    (2,"drift_detected",[],False),
])
def test_native_drift_actual_exit_contract(monkeypatch,rc,status,problems,accepted):
    from types import SimpleNamespace
    monkeypatch.setattr(first.subprocess,"run",lambda *a,**k:SimpleNamespace(
        returncode=rc,stdout=json.dumps({"status":status,"problems":problems})))
    if accepted:
        assert first.live_drift()=={"status":status,"problems":problems}
    else:
        with pytest.raises(first.TransitionDenied,match="NATIVE_DRIFT"):
            first.live_drift()

@pytest.mark.parametrize("name,actual_mode,request_mode,uid,gid,allowed",[
    ("auto-promotion-incident-hold",0o664,0o664,1000,1000,True),
    ("auto-promotion-incident-hold",0o664,None,1000,1000,False),
    ("auto-promotion-incident-hold",0o664,0o664,1000,1001,False),
    ("auto-promotion-incident-hold",0o666,0o664,1000,1000,False),
    ("unrelated-source.py",0o664,0o664,1000,1000,False),
    ("unrelated-source.py",0o644,None,1000,1000,True),
])
def test_exact_legacy_hold_custody_only(tmp_path,monkeypatch,name,actual_mode,request_mode,uid,gid,allowed):
    from types import SimpleNamespace
    import os
    monkeypatch.setattr(first,"MANAGER",tmp_path)
    target=tmp_path/name
    target.write_bytes(b"immutable hold fixture")
    target.chmod(actual_mode)
    actual_fstat=os.fstat
    def fixture_stat(fd):
        st=actual_fstat(fd)
        return SimpleNamespace(st_dev=st.st_dev,st_ino=st.st_ino,st_uid=uid,st_gid=gid,
                               st_nlink=st.st_nlink,st_mode=st.st_mode,st_size=st.st_size)
    monkeypatch.setattr(first.os,"fstat",fixture_stat)
    if allowed:
        assert first.read_file(target,1000,request_mode)==b"immutable hold fixture"
    else:
        with pytest.raises(first.TransitionDenied,match="FILE_CUSTODY"):
            first.read_file(target,1000,request_mode)

def test_pinned_hold_bytes_cannot_be_changed_even_with_correct_mode(monkeypatch):
    paths=first.CONTROL_PINS
    monkeypatch.setattr(first,"read_file",lambda *a,**k:b"changed hold")
    with pytest.raises(first.TransitionDenied,match="FREEZE_OR_HOLD_CHANGED"):
        first.fixed_controls()
