"""Bounded production-only peer health for one-use audit restoration.

An unhealthy *exactly isolated* preproduction shadow is recorded, never
mistaken for a healthy core, and never allowed to authorize unrelated releases.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from tools import audit_journal_release_scope as scope


@pytest.fixture(autouse=True)
def independent_test_peer_policy(tmp_path,monkeypatch):
    """Synthetic original peer fixtures never read a live Root-only policy.

    Once Jason's approved Root watcher is installed, its mode0600 trust file
    exists on production. Hosted CI has no such file. Keep deterministic
    synthetic peer cases isolated without relaxing actual Root checks.
    The dedicated provenance tests exercise the real conditional gate.
    """
    monkeypatch.setattr(scope,"OWNER_EXACT_ROOT_POLICY",
                        tmp_path/"no-real-host-Root-policy-fixture.json")

def peers():
    rows=[]
    for n,image in scope.EXPECTED_PEER_IMAGES.items():
        status=("unhealthy" if n=="jason-pmv4-shadow-gateway"
                else "none" if n in ("jason-mcp-pilot","jason-teams-gateway","openbao")
                else "healthy")
        row={"Name":"/"+n,"Id":(n.replace("-","")+"x"*64)[:64],
             "Image":image,"State":{"Running":True,
                 "StartedAt":"2026-11-20T00:00:00Z",
                 "Health":{"Status":status} if status!="none" else {}},
             "HostConfig":{},"Config":{"Labels":{}},"Mounts":[]}
        if n in ("jason-runtime","jason-mcp-pilot"):
            row["Config"]["Labels"]["com.teamaot.jason.source_revision"]=scope.ROLLBACK
        if n=="jason-pmv4-shadow-gateway":
            row["HostConfig"]={
              "NetworkMode":"none","ReadonlyRootfs":True,
              "Memory":4294967296,"NanoCpus":1000000000,"PidsLimit":256,
              "Privileged":False,"RestartPolicy":{"Name":"no"},
              "CapDrop":["ALL"],"SecurityOpt":["no-new-privileges:true"],
              "PortBindings":{},"Devices":[]}
            row["Config"]["User"]="1000:1000"
            row["Config"]["Labels"].update({
              "com.aot.jason.component":"pmv4-shadow",
              "com.aot.jason.lifecycle":"preproduction-only",
              "com.aot.jason.provider-mutation":"disabled",
              "com.aot.jason.production-core":"excluded",
              "com.aot.jason.source_revision":"75f2b4c0c48a15bd17d700b9f039fe56623e3f52"})
            row["Mounts"]=[{"Type":"volume","Destination":"/home/node/.openclaw"}]
        rows.append(row)
    return rows

def project(monkeypatch,rows):
    seen=[]
    def read(argv,**kwargs):
        seen.append(list(argv))
        assert kwargs["timeout"]==28
        assert kwargs["check"] is False
        return SimpleNamespace(returncode=0,stdout=json.dumps(rows))
    monkeypatch.setattr(scope.subprocess,"run",read)
    return seen

def test_shadow_unhealthy_admitted_only_under_exact_fenced_isolation(monkeypatch):
    data=peers()
    seen=project(monkeypatch,data)
    result=scope.protected_peer_inventory()
    assert set(result)==set(scope.EXPECTED_PEER_IMAGES)
    assert result["jason-pmv4-shadow-gateway"]["health"]=="unhealthy"
    assert result["jason-pmv4-shadow-gateway"]["preproduction_only"] is True
    assert all(result[x]["health"] in ("healthy","none") for x in result
               if x!="jason-pmv4-shadow-gateway")
    assert "jason-pmv4-shadow-gateway" in seen[0]
    assert seen[0][:4]==["/usr/bin/docker","inspect","--type","container"]

@pytest.mark.parametrize("name,key,value",[
 ("jason-runtime","health","unhealthy"),
 ("jason-pmv4-ticket-core","health","none"),
 ("jason-mcp-pilot","health","unhealthy"),
 ("jason-pmv4-shadow-gateway","network","bridge"),
 ("jason-pmv4-shadow-gateway","memory",8589934592),
 ("jason-pmv4-shadow-gateway","privileged",True),
 ("jason-pmv4-shadow-gateway","readonly",False),
 ("jason-pmv4-shadow-gateway","capabilities",[]),
 ("jason-pmv4-shadow-gateway","label","production-candidate"),
 ("jason-pmv4-shadow-gateway","source","ffffffffffffffffffffffffffffffffffffffff"),
 ("jason-pmv4-shadow-gateway","health","none"),
 ("jason-pmv4-shadow-gateway","mount","bind"),
 ("jason-teams-gateway","running",False),
 ("openbao","image","sha256:unreviewed"),
])
def test_required_production_peers_and_shadow_security_fail_closed(
        monkeypatch,name,key,value):
    data=peers()
    row=next(r for r in data if r["Name"].lstrip("/")==name)
    if key=="health":
        row["State"]["Health"]={"Status":value} if value!="none" else {}
    elif key=="network":row["HostConfig"]["NetworkMode"]=value
    elif key=="memory":row["HostConfig"]["Memory"]=value
    elif key=="privileged":row["HostConfig"]["Privileged"]=value
    elif key=="readonly":row["HostConfig"]["ReadonlyRootfs"]=value
    elif key=="capabilities":row["HostConfig"]["CapDrop"]=value
    elif key=="label":row["Config"]["Labels"]["com.aot.jason.lifecycle"]=value
    elif key=="source":row["Config"]["Labels"]["com.aot.jason.source_revision"]=value
    elif key=="mount":row["Mounts"][0]["Type"]=value
    elif key=="running":row["State"]["Running"]=value
    elif key=="image":row["Image"]=value
    project(monkeypatch,data)
    with pytest.raises(PermissionError):
        scope.protected_peer_inventory()

def test_foreign_or_missing_container_rejected(monkeypatch):
    data=peers()
    project(monkeypatch,data[:-1])
    with pytest.raises(PermissionError,match="INCOMPLETE"):
        scope.protected_peer_inventory()

def test_swapped_container_ids_and_identical_names_rejected(monkeypatch):
    data=peers()
    data[0]["Name"]=data[1]["Name"]
    project(monkeypatch,data)
    with pytest.raises(PermissionError,match="NAME_UNTRUSTED|IDENTITY_UNTRUSTED"):
        scope.protected_peer_inventory()

def test_invalid_docker_status_rejected_without_any_mutation(monkeypatch):
    def error(argv,**kwargs):
        assert argv[0]=="/usr/bin/docker"
        return SimpleNamespace(returncode=1,stdout="")
    monkeypatch.setattr(scope.subprocess,"run",error)
    with pytest.raises(PermissionError,match="INVENTORY_UNAVAILABLE"):
        scope.protected_peer_inventory()


def oom_stopped(rows):
    shadow=next(x for x in rows if x["Name"]=="/jason-pmv4-shadow-gateway")
    shadow["State"].update({
        "Running":False,"Status":"exited","OOMKilled":True,
        "ExitCode":137,"Pid":0})
    shadow["RestartCount"]=0
    return shadow


def test_exact_oom_stopped_isolated_shadow_is_observed_not_restarted(monkeypatch):
    rows=peers()
    shadow=oom_stopped(rows)
    seen=project(monkeypatch,rows)
    result=scope.protected_peer_inventory()
    evidence=result["jason-pmv4-shadow-gateway"]
    assert evidence["running"] is False
    assert evidence["observed_state"]=="exact_oom_stopped"
    assert evidence["oom_killed"] is True
    assert evidence["exit_code"]==137
    assert evidence["health"]=="unhealthy"
    assert evidence["preproduction_only"] is True
    assert all(result[n]["health"] in ("healthy","none")
               for n in result if n!="jason-pmv4-shadow-gateway")
    assert len(seen)==1 and seen[0][1]=="inspect"
    assert not any("start" in part or "update" in part or "run" in part
                   for argv in seen for part in argv[1:4])


@pytest.mark.parametrize("mutation",[
    lambda r:r["State"].update(OOMKilled=False),
    lambda r:r["State"].update(ExitCode=0),
    lambda r:r["State"].update(ExitCode=143),
    lambda r:r["State"].update(Status="created"),
    lambda r:r["State"].update(Pid=1000),
    lambda r:r.update(RestartCount=1),
    lambda r:r["State"].update(Health={"Status":"none"}),
    lambda r:r["HostConfig"].update(NetworkMode="bridge"),
    lambda r:r["HostConfig"].update(ReadonlyRootfs=False),
    lambda r:r["HostConfig"].update(CapDrop=[]),
    lambda r:r["HostConfig"].update(Memory=8589934592),
    lambda r:r["HostConfig"].update(Privileged=True),
    lambda r:r["Config"]["Labels"].update(
        {"com.aot.jason.provider-mutation":"enabled"}),
    lambda r:r["Config"]["Labels"].update(
        {"com.aot.jason.production-core":"true"}),
    lambda r:r["Mounts"].append(
        {"Type":"bind","Destination":"/var/lib/jason/governed-ticket-shared"}),
    lambda r:r.update(Image="sha256:changed"),
])
def test_stopped_shadow_must_be_exact_original_oom_isolation(
        monkeypatch,mutation):
    rows=peers();shadow=oom_stopped(rows)
    mutation(shadow)
    project(monkeypatch,rows)
    with pytest.raises(PermissionError):
        scope.protected_peer_inventory()


@pytest.mark.parametrize("n",[
    "jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core",
    "jason-teams-gateway","openbao"])
def test_no_production_container_can_use_shadow_oom_exception(monkeypatch,n):
    rows=peers()
    row=next(x for x in rows if x["Name"]=="/"+n)
    row["State"].update({
        "Running":False,"Status":"exited","OOMKilled":True,
        "ExitCode":137,"Pid":0})
    row["RestartCount"]=0
    project(monkeypatch,rows)
    with pytest.raises(PermissionError,match="AUDIT_PEER_RUNNING_STATE_UNTRUSTED"):
        scope.protected_peer_inventory()
