"""Interruption tests use a fake Engine; they never contact Docker or providers."""
import copy
import pytest
from tools.audit_journal_container_release import DockerEngine,planned_configuration,configuration_matches
from tools.tests.test_audit_journal_release_plan import before,CANDIDATE

ROLE="jason-runtime"
BACKUP=ROLE+"-rollback-audit-before-"+CANDIDATE[:12]

class EngineFixture(DockerEngine):
 def __init__(self,crash):
  source=before();source["State"]={"Running":True}
  self.rows={ROLE:source};self.crash=crash;self.created=0
 def lookup(self,name,required=False):
  row=self.rows.get(name) or next((v for v in self.rows.values() if v["Id"]==name),None)
  if required:assert row is not None
  return copy.deepcopy(row)
 def call(self,method,path,body=None,**kwargs):
  if "/stop?" in path:
   self.rows[ROLE]["State"]["Running"]=False;step="stop";result={}
  elif "/rename?" in path:
   self.rows[BACKUP]=self.rows.pop(ROLE);step="rename";result={}
  elif path.startswith("/containers/create?"):
   self.created+=1
   config={k:copy.deepcopy(v) for k,v in body.items() if k not in ("HostConfig","NetworkingConfig")}
   self.rows[ROLE]={"Id":"d"*64,"Image":body["Image"],"Config":config,
    "HostConfig":copy.deepcopy(body["HostConfig"]),"State":{"Running":False},
    "NetworkSettings":{"Networks":copy.deepcopy(body["NetworkingConfig"]["EndpointsConfig"])},
    "Mounts":[{"Destination":v["Target"],"Type":v["Type"],"Source":v["Source"],
               "RW":not v.get("ReadOnly",False)} for v in body["HostConfig"]["Mounts"]]}
   step="create";result={"Id":"d"*64}
  elif path.endswith("/start"):
   self.rows[ROLE]["State"]["Running"]=True;step="start";result={}
  else:raise AssertionError(path)
  if self.crash==step:
   self.crash=None;raise RuntimeError("lost-response-"+step)
  return result

@pytest.mark.parametrize("crash",["stop","rename","create","start"])
def test_lost_response_recovers_from_native_facts_without_duplicate_replacement(monkeypatch,crash):
 monkeypatch.setattr("tools.audit_journal_container_release.os.geteuid",lambda:0)
 engine=EngineFixture(crash);body=planned_configuration(before(),CANDIDATE)
 with pytest.raises(RuntimeError,match="lost-response"):
  engine.replace(ROLE,body,expected_id="b"*64,backup_name=BACKUP)
 result=engine.replace(ROLE,body,expected_id="b"*64,backup_name=BACKUP)
 assert result["after_id"]=="d"*64 and engine.created==1
 assert engine.rows[ROLE]["State"]["Running"] is True
 assert engine.rows[BACKUP]["State"]["Running"] is False

def test_unknown_container_is_never_replaced_or_accepted(monkeypatch):
 monkeypatch.setattr("tools.audit_journal_container_release.os.geteuid",lambda:0)
 engine=EngineFixture(None);engine.rows[ROLE]["Id"]="e"*64
 with pytest.raises(PermissionError,match="BEFORE_IMAGE"):
  engine.replace(ROLE,planned_configuration(before(),CANDIDATE),expected_id="b"*64,backup_name=BACKUP)
 assert engine.created==0 and engine.rows[ROLE]["State"]["Running"]

def test_configuration_readback_rejects_resource_or_mount_permission_change():
 source=before();body=planned_configuration(source,CANDIDATE)
 engine=EngineFixture(None);engine.call("POST","/containers/create?fixture",body)
 current=engine.rows[ROLE]
 assert configuration_matches(current,body)
 current["HostConfig"]["ReadonlyRootfs"]=False
 assert not configuration_matches(current,body)
 current["HostConfig"]["ReadonlyRootfs"]=True;current["Mounts"][-1]["RW"]=True
 assert not configuration_matches(current,body)


@pytest.mark.parametrize("crash",["create","start"])
def test_original_recreation_lost_response_does_not_consume_an_extra_replacement(monkeypatch,crash):
 from tools.audit_journal_container_release import exact_original_configuration
 monkeypatch.setattr("tools.audit_journal_container_release.os.geteuid",lambda:0)
 engine=EngineFixture(crash);engine.rows[BACKUP]=engine.rows.pop(ROLE)
 engine.rows[BACKUP]["State"]["Running"]=False
 body=exact_original_configuration(before())
 with pytest.raises(RuntimeError,match="lost-response"):
  engine.restore_missing(ROLE,body,original_id="b"*64,original_backup=BACKUP)
 result=engine.restore_missing(ROLE,body,original_id="b"*64,original_backup=BACKUP)
 assert result["after_id"]=="d"*64 and engine.created==1
 assert engine.rows[ROLE]["State"]["Running"] and configuration_matches(engine.rows[ROLE],body)
