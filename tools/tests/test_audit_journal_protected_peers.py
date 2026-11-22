"""Bounded production-only peer health for one-use audit restoration.

An unhealthy *exactly isolated* preproduction shadow is recorded, never
mistaken for a healthy core, and never allowed to authorize unrelated releases.
"""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from tools import audit_journal_release_scope as scope

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
