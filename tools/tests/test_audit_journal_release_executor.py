"""Executor recovery uses durable step receipts and real engine reconciliation.

Only synthetic container dictionaries are used; no Docker socket is contacted.
"""
import copy
from types import SimpleNamespace
import pytest
from tools.audit_journal_release_executor import ExactRelease
from orchestrator.segmented_journal import JournalUnavailable
from tools.audit_journal_container_release import ROLES,planned_configuration,exact_original_configuration
from tools.tests.test_audit_journal_release_plan import before,CANDIDATE
from tools.tests.test_audit_journal_release_recovery import EngineFixture,ROLE,BACKUP

@pytest.mark.parametrize("original,crash",[(False,s) for s in ("stop","rename","create","start")]
                         +[(True,s) for s in ("create","start")])
def test_driver_persists_claim_before_mutation_and_recovers_lost_response(monkeypatch,original,crash):
 monkeypatch.setattr("tools.audit_journal_container_release.os.geteuid",lambda:0)
 executor=ExactRelease.__new__(ExactRelease)
 executor.plan={"candidate_sha":CANDIDATE}
 executor.before={role:before(role) for role in ROLES}
 executor.journal={"steps":{"install:"+ROLE:{"backup":BACKUP}} if original else {}}
 persisted={}
 def save():
  persisted.clear();persisted.update(copy.deepcopy(executor.journal))
 executor.save=save;executor.status=lambda *args,**kwargs:None
 class Engine(EngineFixture):
  def lookup(self,name,required=False):
   if name in ROLES and name!=ROLE:
    source=before(name)
    body=exact_original_configuration(source) if original else planned_configuration(source,CANDIDATE)
    return {"Id":"e"*64,"Image":body["Image"],
     "Config":{k:copy.deepcopy(v) for k,v in body.items() if k not in ("HostConfig","NetworkingConfig")},
     "HostConfig":copy.deepcopy(body["HostConfig"]),"State":{"Running":True},
     "NetworkSettings":{"Networks":copy.deepcopy(body["NetworkingConfig"]["EndpointsConfig"])},
     "Mounts":[{"Destination":v["Target"],"Type":v["Type"],"Source":v["Source"],
                "RW":not v.get("ReadOnly",False)} for v in body["HostConfig"]["Mounts"]]}
   return super().lookup(name,required)
  def inspect(self,name):return self.lookup(name,required=True)
  def call(self,*args,**kwargs):
   key=("restore:" if original else "install:")+ROLE
   assert key in persisted["steps"],"write-ahead claim must precede every native mutation"
   if original:assert persisted["steps"][key]["restore_missing"] is True
   try:return super().call(*args,**kwargs)
   except RuntimeError as exc:raise OSError("transport response lost") from exc
 engine=Engine(crash);executor.engine=engine
 if original:
  engine.rows[BACKUP]=engine.rows.pop(ROLE);engine.rows[BACKUP]["State"]["Running"]=False
 executor.replace(original=original)
 key=("restore:" if original else "install:")+ROLE
 assert persisted["steps"][key]["verified"] is True
 assert persisted["steps"][key]["after_id"]==engine.rows[ROLE]["Id"]=="d"*64
 assert engine.created==1 and engine.rows[ROLE]["State"]["Running"]
 executor.replace(original=original)
 assert engine.created==1

def test_recorded_replacement_identity_change_fails_closed():
 executor=ExactRelease.__new__(ExactRelease)
 executor.plan={"candidate_sha":CANDIDATE}
 executor.before={role:before(role) for role in ROLES}
 role="jason-pmv4-ticket-core"
 executor.journal={"steps":{"install:"+role:{"after_id":"d"*64}}}
 executor.matches=lambda current,body:True
 executor.engine=SimpleNamespace(lookup=lambda name:{"Id":"e"*64,"State":{"Running":True}})
 with pytest.raises(JournalUnavailable,match="RECORDED_REPLACEMENT_CHANGED"):executor.replace()
