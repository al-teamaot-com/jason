"""Source-only exact journal release executor; not an installation command.

This module is a draft in the engineering worktree. The writing operation does
not execute it. Production entry additionally requires the fixed installed path,
isolated Root interpreter, immutable verified bundle, independently verified
Owner adoption, and Root-only exact release plan.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json,os,subprocess,sys,time
from pathlib import Path
from tools.audit_journal_release_scope import ACTION,PRIVATE,POLICY,BASE,OWNER,ROLLBACK,PROTECTED,STATE,digest
from tools.audit_journal_container_release import DockerEngine,ROLES,planned_configuration,exact_original_configuration,configuration_matches
from orchestrator.segmented_journal import read_control,need
ENTRY=BASE/"trusted/tools/audit_journal_release_executor.py"

class ExactRelease:
 def __init__(self,controller):
  need(os.geteuid()==0 and sys.flags.isolated==1 and Path(__file__).resolve()==ENTRY,
       "JOURNAL_INSTALLED_EXACT_RELEASE_EXECUTOR_REQUIRED")
  self.c=controller;self.engine=DockerEngine()
  self.plan=read_control(PRIVATE/"release-plan.json",0,0o400)
  self.policy=read_control(POLICY,0,0o600)
  self.path=PRIVATE/"release-journal.json"
  self.journal=read_control(self.path,0,0o400) if self.path.exists() else {"steps":{}}
  need(self.plan["action"]==ACTION and self.plan["owner_oid"]==OWNER
       and self.plan["independently_verified_entra_owner"] is True
       and self.plan["scope_sha256"]==digest(self.plan["scope"])
       and self.plan["candidate_sha"]==self.policy["candidate_sha"],"JOURNAL_EXACT_RELEASE_PLAN_BINDING")
  self.before=read_control(PRIVATE/"producer-before.json",0,0o400)
  need(digest(self.before)==self.plan["producer_before_sha256"],"JOURNAL_BEFORE_SPEC_BINDING")

 def save(self):self.c._json(self.path,self.journal,0o400)
 def status(self,phase,**extra):
  value={"schema_version":"1.0","candidate_sha":self.plan["candidate_sha"],"phase":phase,
   "scope_sha256":self.plan["scope_sha256"],"observed_at":datetime.now(timezone.utc).isoformat(),**extra}
  self.c._json(self.c.p.control/"release-status.json",value)
  print(json.dumps(value,sort_keys=True),flush=True)
 def protected(self):
  for name,expected in PROTECTED.items():
   fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW)
   with os.fdopen(fd,"rb") as stream:
    need(sha256(stream.read()).hexdigest()==expected,"JOURNAL_PROTECTED_BASELINE_CHANGED")
 def claim(self):
  if "started_at" not in self.journal:
   issued=datetime.fromisoformat(self.plan["approved_at"]);claimed=datetime.fromisoformat(self.plan["claimed_at"])
   need(0<=(claimed-issued).total_seconds()<=600,"JOURNAL_OWNER_PLAN_NOT_CLAIMED_WHILE_FRESH")
   self.journal.update(started_at=claimed.isoformat(),scope_sha256=self.plan["scope_sha256"])
   self.save()
  need(self.journal["scope_sha256"]==self.plan["scope_sha256"],"JOURNAL_RELEASE_CLAIM_CHANGED")
  need(0<=(datetime.now(timezone.utc)-datetime.fromisoformat(self.journal["started_at"])).total_seconds()<=28800,
       "JOURNAL_EXACT_RELEASE_EXECUTION_BUDGET")
  elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(self.journal["started_at"])).total_seconds()
  self.c._objective_deadline=time.monotonic()+28800-elapsed
  self.protected()
 def sql(self,operation,args,seconds=10800):return self.c._sql(operation,args,seconds=seconds)
 def barrier(self,enabled,legacy=False):
  self.sql("barrier",{"path":str(self.c.p.active),"enabled":enabled,"block_invoking":legacy},seconds=10)

 def drain(self,segmented):
  self.status("draining_admitted_work");deadline=time.monotonic()+300
  while time.monotonic()<deadline:
   if segmented:
    state=self.sql("state",{"path":str(self.c.p.active)},seconds=10)
    if state["pending_outcomes"]:
     self.sql("reconcile_outcomes",{"profile":self.c.profile_arguments(),"maximum":100},seconds=30)
    elif not state["reservations"]:return
   else:
    result=self.sql("live_claim_count",{"cutoff":self.plan["oldest_producer_started_at"]},seconds=10)
    if result["consumed_since_cutoff"]==0:return
   time.sleep(1)
  raise RuntimeError("JOURNAL_ADMITTED_WORK_DRAIN_NOT_COMPLETE")

 def matches(self,current,body):return current is not None and configuration_matches(current,body)

 def replace(self,original=False):
  candidate=self.plan["candidate_sha"]
  for role in ("jason-pmv4-ticket-core","jason-runtime","jason-mcp-pilot"):
   before=self.before[role]
   body=exact_original_configuration(before) if original else planned_configuration(before,candidate)
   current=self.engine.lookup(role)
   if self.matches(current,body) and current["State"]["Running"]:continue
   key=("restore:" if original else "install:")+role
   step=self.journal["steps"].get(key)
   if step is None:
    if original and current is None:
     installed=self.journal["steps"].get("install:"+role)
     need(installed is not None,"JOURNAL_MISSING_PRODUCER_HAS_NO_RECORDED_INSTALL")
     saved=self.engine.lookup(installed["backup"],required=True)
     need(saved["Id"]==before["Id"] and not saved["State"]["Running"],
          "JOURNAL_EXACT_ORIGINAL_BEFORE_CONTAINER_REQUIRED")
     result=self.engine.call("POST","/containers/create?name="+role,body)
     need(len(result.get("Id",""))==64,"JOURNAL_ORIGINAL_RECREATION_ID")
     self.engine.call("POST","/containers/"+result["Id"]+"/start")
     restored=self.engine.inspect(role)
     need(self.matches(restored,body) and restored["State"]["Running"],"JOURNAL_RECREATED_ORIGINAL_NOT_VERIFIED")
     self.journal["steps"][key]={"after_id":restored["Id"],"verified":True};self.save()
     continue
    need(current is not None,"JOURNAL_UNRECORDED_PRODUCER_ABSENT")
    if not original:need(current["Id"]==before["Id"],"JOURNAL_PRODUCER_CHANGED_BEFORE_REPLACEMENT")
    phase="failed" if original else "before"
    step={"before_id":current["Id"],"backup":role+"-rollback-audit-"+phase+"-"+candidate[:12],
          "configuration_sha256":digest(body)}
    self.journal["steps"][key]=step;self.save()
   self.status("restoring_consumers" if original else "installing_dormant_consumers",role=role)
   result=self.engine.replace(role,body,expected_id=step["before_id"],backup_name=step["backup"])
   step.update(result,verified=False);self.save()
   deadline=time.monotonic()+120
   while time.monotonic()<deadline:
    observed=self.engine.inspect(role)
    if observed["State"]["Running"] and self.matches(observed,body):break
    time.sleep(1)
   else:raise RuntimeError("JOURNAL_CONSUMER_CONFIGURATION_NOT_VERIFIED")
   step["verified"]=True;self.save()

 def verify_modules(self):
  code=("import hashlib,json,pathlib,orchestrator.event_store as e,orchestrator.segmented_journal as s,"
        "orchestrator.journal_outcomes as o;print(json.dumps({pathlib.Path(m.__file__).name:"
        "hashlib.sha256(pathlib.Path(m.__file__).read_bytes()).hexdigest() for m in (e,s,o)}))")
  wanted={Path(k).name:v for k,v in self.policy["trusted_source_sha256"].items()
          if Path(k).name in ("event_store.py","segmented_journal.py","journal_outcomes.py")}
  for role in ROLES:
   result=subprocess.run(["/usr/bin/docker","exec","--user","1000:1000",role,"python","-B","-c",code],
                        capture_output=True,text=True,timeout=30,check=False)
   need(result.returncode==0 and json.loads(result.stdout)==wanted,"JOURNAL_LOADED_CONSUMER_SOURCE_MISMATCH")

 def scheduled_cycle(self):
  with self.c.p.gate():epoch=self.c.p.catalog()["epoch"]
  request=self.c.private/"first-scheduled-rollover.json"
  if not request.exists():self.c._json(request,{"before_epoch":epoch,"completed":False},0o400)
  start=datetime.now(timezone.utc)
  subprocess.run(["/usr/bin/systemctl","enable","--now","jason-audit-journal-maintenance.timer"],
                 capture_output=True,timeout=30,check=True)
  deadline=time.monotonic()+600
  while time.monotonic()<deadline:
   try:
    row=read_control(self.c.p.control/"maintenance-status.json",0)
    if datetime.fromisoformat(row["observed_at"])>=start:
     need(row["status"]=="pass" and row["maintenance"]["initial_scheduled_rollover_verified"] is True
          and (row["native_health"]["status"]=="existing_native_full_fast_drift_and_revalidation_verified"
               or read_control(request,0,0o400).get("native_verified") is True),
          "JOURNAL_SCHEDULED_ROLLOVER_NOT_SUCCESSFUL")
     return
   except (OSError,ValueError,KeyError):pass
   time.sleep(1)
  raise RuntimeError("JOURNAL_REAL_SCHEDULED_CYCLE_NOT_VERIFIED")

 def verify_consumers(self):
  paths=[str(self.c.p.active)]
  with self.c.p.gate():
   paths.extend(str(self.c.p.artifact(r)) for r in self.c.p.catalog()["segments"][:1])
  probes=self.sql("reader_probes",{"paths":paths},seconds=30)
  need(probes["event_ids"] and len(probes["per_source_probe_counts"])==2
       and all(probes["per_source_probe_counts"]),"JOURNAL_REAL_CURRENT_AND_HISTORICAL_EVENTS_REQUIRED")
  code=("import json,sys;from orchestrator.event_store import SQLiteOrchestrationEventStore;"
        "s=SQLiteOrchestrationEventStore(sys.argv[1]);ids=json.loads(sys.argv[2]);"
        "assert all(s.get(v).event_id==v for v in ids);s.close();print(len(ids))")
  for role in ROLES:
   result=subprocess.run(["/usr/bin/docker","exec","--user","1000:1000",role,"python","-B","-c",
      code,str(self.c.p.active),json.dumps(probes["event_ids"])],capture_output=True,text=True,timeout=60,check=False)
   need(result.returncode==0 and result.stdout.strip()==str(len(probes["event_ids"])),
        "JOURNAL_ACTUAL_CONSUMER_HISTORY_READ_FAILED")
  for role,before in self.plan["scope"]["protected_peer_before"].items():
   need(role in (*ROLES,"jason-pmv4-shadow-gateway","jason-teams-gateway","openbao"),
        "JOURNAL_FIXED_PROTECTED_PEER")
   fmt='{"id":"{{.Id}}","image":"{{.Image}}","state":{{json .State}}}'
   result=subprocess.run(["/usr/bin/docker","inspect","--format",fmt,role],
                         capture_output=True,text=True,timeout=15,check=True)
   value=json.loads(result.stdout);state=value["state"]
   need(value["image"]==before["image"] and state["Running"]
        and state.get("Health",{}).get("Status","none") in ("none","healthy"),"JOURNAL_PROTECTED_PEER_NOT_HEALTHY")
   if role not in ROLES:
    need(value["id"]==before["id"] and state["StartedAt"]==before["started_at"],
         "JOURNAL_UNRELATED_PROTECTED_PEER_CHANGED")
  self.status("actual_consumer_history_and_protected_health_verified",consumers=3)

 def native(self):
  self.status("verifying_native_operation")
  for unit in ("jason-openclaw-authority-full-integrity.service","jason-openclaw-authority-health.service",
               "jason-production-drift-watchdog.service"):
   result=subprocess.run(["/usr/bin/systemctl","start",unit],capture_output=True,timeout=5500,check=False)
   need(result.returncode==0,"JOURNAL_NATIVE_SERVICE_DID_NOT_PASS")
  code=("import sys;from pathlib import Path;sys.path.insert(0,'/home/al/.local/lib/jason');"
        "import release_manager_host_runner as r;r.request_root_control_transition(Path("
        +repr(str(STATE))+"),action='revalidate',revision="+repr(ROLLBACK)+")")
  result=subprocess.run(["/usr/sbin/runuser","-u","al","--","/usr/bin/python3","-B","-c",code],
                       capture_output=True,timeout=100,check=False)
  need(result.returncode==0,"JOURNAL_GOVERNED_NATIVE_REVALIDATION_DID_NOT_PASS")

 def complete(self):
  if self.journal.get("outcome") in ("accepted","rolled_back"):return
  if "recovery_started_at" in self.journal:
   self.begin_recovery();self.protected();self.rollback()
   self.journal["outcome"]="rolled_back";self.save()
   self.status("rolled_back",all_history_retained=True);return
  self.claim()
  try:
   self.c.recover()
   self.c.cleanup_abandoned_work()
   if self.c.p.catalog()["mode"]=="legacy" and not (PRIVATE/"initial-cutover-complete.json").exists():
    self.barrier(True,legacy=True);self.drain(False);self.replace();self.verify_modules()
    self.status("publishing_small_active_journal");self.c.transition(initial=True)
   else:self.c.recover()
   while self.c.status()["pending"]:
    self.status("fully_verifying_and_archiving_closed_history");self.c.seal_one()
   self.status("verifying_legacy_reconstruction_and_cold_restore")
   if not (PRIVATE/"recovery-recipe.json").exists():
    self.c.prepare_rollback();self.c.recovery().accept_recipe();self.c.recovery().discard_prepared()
   self.c.recovery().extend_recipe()
   for row in self.c.p.catalog()["segments"]:
    if (self.c.p.pending/row["proof"]["source_before_image"]).exists():
     self.status("reclaiming_verified_redundant_local_copy");self.c.reclaim(row["id"])
   self.scheduled_cycle();self.verify_modules();self.verify_consumers();self.protected()
   self.journal["outcome"]="accepted";self.save()
   self.status("accepted",whole_objective_verified=True,off_host_backup_claimed=False)
  except Exception as exc:
   self.status("recovering_exact_approved_rollback",reason_code=type(exc).__name__)
   self.begin_recovery();self.rollback()
   self.journal.update(outcome="rolled_back",failure_type=type(exc).__name__);self.save()
   self.status("rolled_back",whole_objective_verified=False,all_history_retained=True)
   raise

 def begin_recovery(self):
  stamp=self.journal.setdefault("recovery_started_at",datetime.now(timezone.utc).isoformat());self.save()
  elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(stamp)).total_seconds()
  need(0<=elapsed<=28800,"JOURNAL_EXACT_RECOVERY_EXECUTION_BUDGET")
  self.c._objective_deadline=time.monotonic()+28800-elapsed

 def rollback(self):
  subprocess.run(["/usr/bin/systemctl","disable","--now","jason-audit-journal-maintenance.timer"],
                 capture_output=True,timeout=30,check=False)
  self.c.recover()
  self.c.cleanup_abandoned_work()
  if self.c.p.catalog()["mode"]!="legacy":
   self.barrier(True);self.drain(True)
   self.status("reconstructing_all_events_for_exact_legacy_rollback")
   self.c.prepare_rollback();self.c.finish_rollback()
  self.replace(original=True);self.barrier(False)
  rollback=read_control(PRIVATE/"desired-rollback.json",0,0o400)
  need(digest(rollback)==self.plan["scope"]["rollback_desired_state_sha256"],
       "JOURNAL_ROLLBACK_DESIRED_SCOPE_BINDING")
  from tools.audit_journal_release_scope import DESIRED
  self.c._json(DESIRED,rollback,0o600)
  self.native();self.protected()

def complete(controller):ExactRelease(controller).complete()


def rollback_release(controller):
 executor=ExactRelease(controller)
 if executor.journal.get("outcome")=="rolled_back":return
 # A rollback may start only within the exact original execution window.
 if "recovery_started_at" not in executor.journal:executor.claim()
 executor.begin_recovery();executor.protected();executor.rollback()
 executor.journal["outcome"]="rolled_back";executor.save()
 executor.status("rolled_back",all_history_retained=True)
