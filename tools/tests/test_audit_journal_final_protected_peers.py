"""Final actual-consumer verification must preserve exact admission peer gates."""
from contextlib import nullcontext
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import audit_journal_release_scope as scope
from tools import audit_journal_release_executor as release
from tools.audit_journal_container_release import ROLES
from orchestrator.segmented_journal import JournalUnavailable
from test_audit_journal_protected_peers import peers,oom_stopped


def prepared(tmp_path,monkeypatch,*,stopped=True):
 monkeypatch.setattr(scope,"OWNER_EXACT_ROOT_POLICY",tmp_path/"absent")
 rows=peers()
 if stopped:oom_stopped(rows)
 seen=[]
 def read(argv,**kwargs):
  seen.append(argv)
  assert argv[0]=="/usr/bin/docker"
  if argv[1:4]==["inspect","--type","container"]:
   return SimpleNamespace(returncode=0,stdout=json.dumps(rows))
  if argv[1:4]==["exec","--user","1000:1000"]:
   assert argv[4] in ROLES and "all(s.get" in argv[8]
   return SimpleNamespace(returncode=0,stdout="2")
  if argv[1:3]==["inspect","--format"]:
   row=next(r for r in rows if r["Name"]=="/"+argv[-1])
   return SimpleNamespace(returncode=0,stdout=json.dumps({
    "id":row["Id"],"image":row["Image"],"state":row["State"]}))
  raise AssertionError("unexpected mutation or command: "+str(argv))
 monkeypatch.setattr(scope.subprocess,"run",read)
 before=scope.protected_peer_inventory();seen.clear()
 executor=object.__new__(release.ExactRelease)
 profile=SimpleNamespace(active=tmp_path/"active.sqlite3",gate=lambda:nullcontext(),
  catalog=lambda:{"segments":[{"id":"history"}]},artifact=lambda row:tmp_path/"history.sqlite3")
 executor.c=SimpleNamespace(p=profile)
 executor.plan={"scope":{"protected_peer_before":deepcopy(before)}}
 def sql(operation,args,**kwargs):
  assert operation=="reader_probes" and len(args["paths"])==2
  return {"per_source_probe_counts":[1,1],"event_ids":["real-current","real-historical"]}
 executor.sql=sql;statuses=[];executor.status=lambda phase,**kw:statuses.append((phase,kw))
 return executor,rows,seen,statuses


@pytest.mark.parametrize("stopped",[True,False])
def test_final_acceptance_uses_exact_admission_shadow_contract(tmp_path,monkeypatch,stopped):
 executor,rows,seen,statuses=prepared(tmp_path,monkeypatch,stopped=stopped)
 before=deepcopy(rows);executor.verify_consumers()
 assert rows==before
 assert statuses==[("actual_consumer_history_and_protected_health_verified",{"consumers":3})]
 assert sum(argv[1]=="exec" for argv in seen)==3
 assert all(argv[1] in ("inspect","exec") for argv in seen)
 if stopped:
  shadow=next(r for r in rows if r["Name"]=="/jason-pmv4-shadow-gateway")
  assert shadow["State"]["Running"] is False and shadow["State"]["Health"]["Status"]=="unhealthy"


@pytest.mark.parametrize("role",list(ROLES))
def test_expected_new_producer_ids_accepted_with_unchanged_images(tmp_path,monkeypatch,role):
 executor,rows,_,_=prepared(tmp_path,monkeypatch)
 next(r for r in rows if r["Name"]=="/"+role)["Id"]="a"*64
 executor.verify_consumers()


@pytest.mark.parametrize("role",["jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core","jason-teams-gateway","openbao"])
@pytest.mark.parametrize("fault",["stopped","unhealthy","image"])
def test_production_peer_gates_remain_hard_after_cutover(tmp_path,monkeypatch,role,fault):
 executor,rows,_,statuses=prepared(tmp_path,monkeypatch)
 row=next(r for r in rows if r["Name"]=="/"+role)
 if fault=="stopped":row["State"]["Running"]=False
 elif fault=="unhealthy":row["State"]["Health"]={"Status":"unhealthy"}
 else:row["Image"]="sha256:"+"f"*64
 with pytest.raises((PermissionError,JournalUnavailable)):executor.verify_consumers()
 assert statuses==[]


@pytest.mark.parametrize("role",["jason-pmv4-shadow-gateway","jason-teams-gateway","openbao"])
@pytest.mark.parametrize("field",["Id","StartedAt"])
def test_unrelated_peer_identity_or_restart_denied(tmp_path,monkeypatch,role,field):
 executor,rows,_,_=prepared(tmp_path,monkeypatch)
 row=next(r for r in rows if r["Name"]=="/"+role)
 if field=="Id":row["Id"]="b"*64
 else:row["State"][field]="2026-11-23T00:00:00Z"
 with pytest.raises((PermissionError,JournalUnavailable),match="UNRELATED_PROTECTED_PEER_CHANGED"):
  executor.verify_consumers()


@pytest.mark.parametrize("fault",["network","host_bind","provider","not_oom","restart"])
def test_stopped_shadow_cannot_escape_exact_fenced_contract(tmp_path,monkeypatch,fault):
 executor,rows,_,_=prepared(tmp_path,monkeypatch)
 row=next(r for r in rows if r["Name"]=="/jason-pmv4-shadow-gateway")
 if fault=="network":row["HostConfig"]["NetworkMode"]="bridge"
 elif fault=="host_bind":row["Mounts"].append({"Type":"bind","Destination":"/var/lib/jason"})
 elif fault=="provider":row["Config"]["Labels"]["com.aot.jason.provider-mutation"]="enabled"
 elif fault=="not_oom":row["State"]["OOMKilled"]=False
 else:row["RestartCount"]=1
 with pytest.raises((PermissionError,JournalUnavailable)):executor.verify_consumers()


def test_missing_scope_peer_denied(tmp_path,monkeypatch):
 executor,_,_,_=prepared(tmp_path,monkeypatch)
 del executor.plan["scope"]["protected_peer_before"]["openbao"]
 with pytest.raises((PermissionError,JournalUnavailable),match="FIXED_PROTECTED_PEER"):
  executor.verify_consumers()
