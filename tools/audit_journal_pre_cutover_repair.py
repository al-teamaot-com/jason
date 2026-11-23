"""One exact Owner-authenticated repair of the known failed pre-cutover adoption.

Preserves the original immutable bootstrap/approval and all failed private records.
No failed grant is replayed; a fresh exact repair/adoption grant owns the next claim.
"""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import json,os,re,stat,tempfile,subprocess,sys,fcntl
from contextlib import contextmanager
from tools.audit_journal_install_transaction import raw_file,atomic,InstallTransaction,sync

OLD="f0f71c46e054f46f6cba1f945a404f148f441501"
OLD_SCOPE="6b792b74869d31f2072929d8ace08236161284b5875d3c2fb7a9dff6d3c56c80"
ROOT=Path("/var/lib/jason-owner-release/audit-journal-service-context-repairs")
PRIVATE_NAMES=frozenset(("adoption.json","producer-before.json","desired-before.json",
 "desired-rollback.json","protected-ci-before.json","release-plan.json","release-journal.json","last-handoff.json"))

def need(ok,code):
 if not ok:raise PermissionError("JOURNAL_CONTEXT_REPAIR_"+code)
def canon(row):return json.dumps(row,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(raw):return sha256(raw).hexdigest()
def ledger(candidate):
 need(isinstance(candidate,str) and re.fullmatch(r"[0-9a-f]{40}",candidate),"EXACT_CANDIDATE")
 return ROOT/candidate

def authorization(candidate):
 root=ledger(candidate)
 for p in (ROOT,root):
  m=p.lstat();need(not p.is_symlink() and stat.S_ISDIR(m.st_mode) and m.st_uid==m.st_gid==0
   and stat.S_IMODE(m.st_mode)==0o700,"PRIVATE_LEDGER_CUSTODY")
 row=json.loads(raw_file(root/"authorization.json",0o400))
 need(row["candidate_sha"]==candidate and row["scope"]["policy"]["candidate_sha"]==candidate and row["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
  and row["independently_verified_entra_owner"] is True and row["scope"]["action"]=="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
  and digest(canon(row["scope"]))==row["scope_sha256"],"EXACT_OWNER_AUTHORIZATION")
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(row["claimed_at"])).total_seconds()
 need(0<=age<=28800,"EXECUTION_WINDOW")
 return row

def props(I,unit):
 return dict(line.split("=",1) for line in I.command(["/usr/bin/systemctl","show",unit,
  "--property=ActiveState,SubState,MainPID,UnitFileState"]).splitlines() if "=" in line)

@contextmanager
def maintenance_lock(s):
 fd=os.open(s.PRIVATE/"maintenance.lock",os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  m=os.fstat(fd)
  need(stat.S_ISREG(m.st_mode) and m.st_uid==m.st_gid==0 and m.st_nlink==1
   and stat.S_IMODE(m.st_mode)==0o600 and m.st_size==0,"EXACT_MAINTENANCE_LOCK")
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  yield
 finally:os.close(fd)


def validate_pre_cutover(journal,catalog):
 need(journal.get("steps")=={} and journal.get("scope_sha256")==OLD_SCOPE
  and "recovery_started_at" in journal and "outcome" not in journal,"NO_CUTOVER_OR_REPLACEMENT")
 need(catalog["mode"]=="legacy" and catalog["generation"]==0 and catalog["epoch"] is None
  and catalog["segments"]==[],"UNCHANGED_LEGACY_CATALOG")


def validate_known_drift(drift,control):
 expected={("required_system_unit_not_active","jason-audit-journal-maintenance.timer","inactive"),
  ("failed_system_unit","jason-audit-journal-release.service","failed")}
 need({(r["kind"],r["unit"],r["state"]) for r in drift["problems"]}==expected and len(drift["problems"])==2
  and drift["status"]=="drift_detected","ONLY_KNOWN_INCOMPLETE_INSTALL_DRIFT")
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))).total_seconds()
 need(0<=age<=180 and control["circuit_breaker"]["state"]=="open"
  and control["circuit_breaker"]["reason"]=="continuous_production_drift_detected","KNOWN_GUARDED_BREAKER")
 return expected


def preflight(I,s,engine,inventory,candidate,payload,c):
 need(Path("/proc/self/ns/mnt").stat().st_ino==Path("/proc/1/ns/mnt").stat().st_ino,"HOST_NAMESPACE")
 need(not os.path.lexists(ledger(candidate)),"ONE_USE_LEDGER_PRESENT")
 I.installation_parent_custody(c);dataset=I.capacity(s);schema=I.schema_and_sample(s)
 old=I.record_read();need(old["candidate_sha"]==OLD and old["scope_sha256"]==OLD_SCOPE,"EXACT_FAILED_PARENT")
 need(old["scope"]["source_dataset_identity"]==dataset,"ORIGINAL_DATASET_IDENTITY")
 for path,wanted in s.PROTECTED.items():need(digest(I.read(Path(path)))==wanted,"PROTECTED_BASELINE")
 need(Path("/opt/jason/current").resolve().name==s.ROLLBACK,"LIVE_BASELINE")
 c["verify_units"](retired_files_absent=True);peers=s.protected_peer_inventory()
 before=json.loads(raw_file(s.PRIVATE/"producer-before.json",0o400))
 need(digest(canon(before))==old["producer_before_sha256"],"ORIGINAL_PRODUCER_RECORD")
 client=engine.DockerEngine()
 for role in engine.ROLES:
  live=client.inspect(role)
  need(live["Id"]==before[role]["Id"] and live["Image"]==before[role]["Image"]
   and live["State"]["Running"] and s.digest(engine.exact_original_configuration(live))==
   s.digest(engine.exact_original_configuration(before[role])),"UNMODIFIED_PRODUCER")
  probe="import hashlib,orchestrator.event_store as e;print(hashlib.sha256(open(e.__file__,'rb').read()).hexdigest())"
  need(I.command(["/usr/bin/docker","exec","--user","1000:1000",role,"python","-B","-c",probe])==s.BASE_STORE,"ORIGINAL_PRODUCER_SOURCE")
 for role,v in old["scope"]["protected_peer_before"].items():
  need(peers[role]==v,"UNMODIFIED_PROTECTED_PEERS")
 handles=inventory.handles(s.ACTIVE);need(handles["complete"],"COMPLETE_PROCESS_INVENTORY")
 for row in handles["open_handles"]:
  text=(Path("/proc")/str(row["pid"])/"cgroup").read_text()
  need(row["uid"]==1000 and any(v["Id"] in text for v in before.values()),"BOUND_DATASET_READER")
 old_policy_raw=raw_file(s.POLICY,0o600);old_policy=json.loads(old_policy_raw)
 adoption=json.loads(raw_file(s.PRIVATE/"adoption.json",0o400))
 need(old_policy["candidate_sha"]==OLD and old_policy["schema_version"]=="1.0" and old_policy["enabled"] is True
  and old_policy["maintenance_operations"]==["rotate","seal","scrub","recover"]
  and old_policy["trusted_source_sha256"]==old["scope"]["source_sha256"]
  and adoption["action"]==s.ACTION and adoption["owner_oid"]==s.OWNER
  and adoption["independently_verified_entra_owner"] is True and adoption["maintenance_policy_adopted"] is True
  and adoption["scope_sha256"]==OLD_SCOPE and adoption["policy_sha256"]==digest(old_policy_raw),"ORIGINAL_ADOPTION")
 for name,wanted in old_policy["trusted_source_sha256"].items():
  need(digest(raw_file(s.BASE/"trusted"/name,0o444))==wanted,"ORIGINAL_TRUSTED_SOURCE")
 for name,installed in s.NATIVE.items():
  need(digest(raw_file(s.BASE/"native-health"/installed,0o444))==old["scope"]["native_health_sha256"][name]
   ==digest(payload[name]),"NATIVE_HEALTH_UNCHANGED")
 for name in (*s.UNITS,*I.OVERRIDES):
  key="infrastructure/jason-audit-journal/"+name
  need(digest(payload[key])==old["scope"]["unit_source_sha256"][name],"UNIT_HARDENING_UNCHANGED")
 for unit,name in (("docker.service","93-jason-audit-data-recovery.conf"),
  ("jason-pmv4-component-reconcile.service","94-audit-data-compatible-release.conf"),
  ("jason-release-host-reconcile.service","94-audit-data-compatible-release.conf")):
  need(digest(raw_file(I.SYSTEMD/(unit+".d")/name,0o644))==old["scope"]["unit_source_sha256"][name],"INSTALLED_COMPATIBILITY_DROPIN")
 need(digest(raw_file(s.PROFILE,0o444))==old_policy["profile_sha256"]
  and raw_file(s.CONTROL/"profile.json",0o444)==raw_file(s.PROFILE,0o444),"ORIGINAL_PROFILE")
 for name in s.UNITS:
  need(digest(raw_file(I.SYSTEMD/name,0o644))==old["scope"]["unit_source_sha256"][name],"INSTALLED_UNIT_SOURCE")
 for unit,raw in I.health_dropins(s).items():
  need(raw_file(I.SYSTEMD/(unit+".d")/"94-audit-journal.conf",0o644)==raw,"NATIVE_HEALTH_DROPIN")
 need({p.name for p in s.PRIVATE.iterdir()}==PRIVATE_NAMES|{"maintenance.lock"},"NO_UNREVIEWED_PRIVATE_WORK")
 with maintenance_lock(s):private={n:raw_file(s.PRIVATE/n,0o400) for n in PRIVATE_NAMES}
 plan=json.loads(private["release-plan.json"])
 need(plan["candidate_sha"]==OLD and plan["scope_sha256"]==OLD_SCOPE and digest(canon(plan["scope"]))==OLD_SCOPE
  and plan["owner_oid"]==s.OWNER and plan["independently_verified_entra_owner"] is True
  and plan["producer_before_sha256"]==old["producer_before_sha256"],"ORIGINAL_EXECUTION_PLAN")
 journal=json.loads(private["release-journal.json"])

 need(not (s.PRIVATE/"initial-cutover-claimed.json").exists() and not (s.PRIVATE/"transaction.json").exists(),"NO_INITIAL_CLAIM")
 catalog_raw=raw_file(s.CONTROL/"catalog.json",0o444);catalog=json.loads(catalog_raw)
 validate_pre_cutover(journal,catalog)
 for p in (s.PRIVATE.parent/"pending",s.ACTIVE.parent/"journal-work",s.ARCHIVE/"governed-audit/work",
  s.ARCHIVE/"governed-audit/orchestration",s.ARCHIVE/"governed-audit/rollback"):
  need(not any(p.iterdir()),"NO_MIGRATION_WORK_OR_ARCHIVES")
 code="import sqlite3,json,sys;d=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True,timeout=2);d.execute('PRAGMA query_only=ON');print(json.dumps(d.execute(sys.argv[2]).fetchall()));d.close()"
 query="SELECT type,name FROM sqlite_master WHERE type='trigger' OR name LIKE 'audit_journal_%'"
 # The real preflight read is performed by the fixed writer UID, never Root.
 result=subprocess.run(["/usr/bin/python3","-I","-B","-c",code,str(s.ACTIVE),query],
  user=1000,group=1000,extra_groups=(),capture_output=True,text=True,timeout=30,check=True,
  env={"PATH":"/usr/bin:/bin","HOME":"/home/al","USER":"al","LOGNAME":"al","LANG":"C.UTF-8"}).stdout
 need(json.loads(result)==[],"NO_DATA_BARRIER_OR_JOURNAL_METADATA")
 release=props(I,"jason-audit-journal-release.service");timer=props(I,"jason-audit-journal-maintenance.timer")
 need(release["ActiveState"]=="failed" and release["MainPID"]=="0" and release["UnitFileState"]=="enabled"
  and timer["ActiveState"]=="inactive","EXACT_FAILED_WORKER_STATE")
 drift=json.loads(raw_file(s.STATE/"production-drift.json",0o600));control=json.loads(raw_file(s.STATE/"production-control-state.json",0o600))
 expected=validate_known_drift(drift,control)
 health={}
 for name,limit in (("operational-health.json",600),("operational-full-health.json",30*3600)):
  p=s.STATE.parent/name;m=p.lstat();row=json.loads(I.read(p))
  need(m.st_uid==m.st_gid==1000 and stat.S_IMODE(m.st_mode)==0o600 and row["status"]=="pass"
   and row["failures"]==[] and row.get("snapshot_source_exit_code")==0
   and 0<=datetime.now(timezone.utc).timestamp()-m.st_mtime<=limit,"GENUINE_RECENT_HEALTH")
  health[name]=row
 full=health["operational-full-health.json"]
 need(all(v["integrity"]=="ok" for v in full["files"].values())
  and full["backup_restore_proof"]["counts_match"] is True,"FULL_DATABASE_AND_RESTORE_PROOF")
 original=private["desired-before.json"];need(digest(original)==s.DESIRED_BEFORE,"ORIGINAL_DESIRED_POLICY")
 desired,retention=I.recovery_capacity(s,json.loads(original))
 current=raw_file(s.DESIRED,0o600)
 need(digest(current)==old["scope"]["desired_state_after_sha256"] and json.loads(current)==desired,"EXACT_INSTALLED_DESIRED_STATE")
 archive=s.ARCHIVE.lstat();need((archive.st_uid,archive.st_gid,stat.S_IMODE(archive.st_mode))==(0,0,0o755),"ADOPTED_ARCHIVE_CUSTODY")
 facts={"dataset_identity":dataset,"archive_root_metadata":{"uid":0,"gid":0,"mode":"0o755"},
  "producer_before":{role:{"id":v["Id"],"image":v["Image"],"configuration_sha256":s.digest(engine.exact_original_configuration(v))} for role,v in before.items()},
  "producer_after":{role:s.digest(engine.planned_configuration(v,candidate)) for role,v in before.items()},
  "desired_after_sha256":digest(current)}
 scope=s.reviewed_scope(candidate,{n:digest(payload[n]) for n in s.SOURCES},
  {n:digest(payload[n]) for n in s.NATIVE},
  {n:digest(payload["infrastructure/jason-audit-journal/"+n]) for n in (*s.UNITS,*I.OVERRIDES)},facts)
 scope.update(source_schema_sha256=schema,installer_sha256=digest(payload["tools/audit_journal_install.py"]),
  bootstrap_source_sha256={n:digest(payload[n]) for n in I.EXTRA},bootstrap_resume_record=str(ledger(candidate)),
  bootstrap_retry_limit=1,protected_peer_before=peers,initial_scheduled_acceptance_rollover=True,
  rollback_desired_state_sha256=digest(canon(s.desired_rollback(json.loads(original)))),
  health_native_dropin_sha256={n:digest(v) for n,v in I.health_dropins(s).items()},
  desired_state_before_sha256=digest(current),desired_state_initial_sha256=digest(canon(s.desired_initial(json.loads(original)))),
  rollback_container_limit_before=27,
  rollback_container_capacity_before={**retention,"limit_before":27},
  pre_cutover_context_repair={"previous_candidate_sha":OLD,"previous_scope_sha256":OLD_SCOPE,
   "private_before_sha256":{n:digest(raw) for n,raw in private.items()},"policy_before_sha256":digest(old_policy_raw),
   "catalog_before_sha256":digest(catalog_raw),"old_bootstrap_and_approval_unchanged":True,
   "previous_failed_execution_preserved":True,"fresh_exact_owner_grant_required":True,
   "initial_data_claim_absent":True,"unit_hardening_unchanged":True,"breaker_remains_guarded":True,
   "existing_six_recovery_slots_reused":True,"native_revalidation_required_before_queue":True,
   "initial_timer_declared_but_not_ready":True,"known_drift":sorted([list(r) for r in expected])})
 scope["installation_targets"]=[*scope["installation_targets"],str(ROOT),str(ledger(candidate))]
 return scope,before,private,old_policy_raw,current


def claim(I,candidate,payload,scope,before,private,policy_raw,desired,actor,ci_proof):
 need(actor=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f","VERIFIED_OWNER")
 parent=I.RECORD.parent;m=parent.lstat()
 need(not parent.is_symlink() and m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o700,"OWNER_ROOT_PARENT")
 if not ROOT.exists():ROOT.mkdir(mode=0o700);sync(ROOT.parent)
 m=ROOT.lstat();need(not ROOT.is_symlink() and m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o700,"REPAIR_PARENT")
 need(not os.path.lexists(ledger(candidate)),"ONE_USE_CLAIM")
 stage=Path(tempfile.mkdtemp(prefix=".claim-",dir=ROOT));stage.chmod(0o700)
 for name,raw in payload.items():
  p=stage/"source"/name;p.parent.mkdir(mode=0o755,parents=True,exist_ok=True);atomic(p,raw,0o444)
 for name,raw in private.items():
  p=stage/"before-private"/name;p.parent.mkdir(mode=0o700,exist_ok=True);atomic(p,raw,0o400)
 atomic(stage/"policy-before.json",policy_raw,0o400)
 atomic(stage/"desired-current.json",desired,0o400)
 atomic(stage/"producer-before.json",canon(before),0o400)
 atomic(stage/"ci.json",canon(ci_proof),0o400)
 stamp=datetime.now(timezone.utc).isoformat()
 row={"schema_version":"1.0","candidate_sha":candidate,"action":scope["action"],
  "scope":scope,"scope_sha256":digest(canon(scope)),"owner_oid":actor,
  "independently_verified_entra_owner":True,"approved_at":stamp,"claimed_at":stamp,
  "source_sha256":{n:digest(raw) for n,raw in payload.items()},"producer_before_sha256":digest(canon(before))}
 atomic(stage/"authorization.json",canon(row),0o400)
 sync(stage);os.rename(stage,ledger(candidate));sync(ROOT)
 return row


def replace_bound(tx,path,raw,before_sha,mode):
 current=raw_file(path,mode);old=digest(current);after=digest(raw)
 entries=[r for r in tx.state["entries"] if r["kind"]=="replace" and r["path"]==str(path)]
 if entries:
  need(digest(bytes.fromhex(entries[0]["before_hex"]))==before_sha,"ORIGINAL_REPLACEMENT_BINDING")
  need(old in (before_sha,after),"REPLACEMENT_OUTSIDE_BEFORE_AFTER")
 else:need(old==before_sha,"UNRECORDED_TARGET_CHANGED")
 tx.replace(path,raw,mode)


def revalidate_before_queue(I,s,scope):
 for unit in ("jason-openclaw-authority-health.service","jason-production-drift-watchdog.service"):
  I.command(["/usr/bin/systemctl","start",unit],timeout=100)
 code=("import sys;from pathlib import Path;sys.path.insert(0,'/home/al/.local/lib/jason');"
  "import release_manager_host_runner as r;r.request_root_control_transition(Path("
  +repr(str(s.STATE))+"),action='revalidate',revision="+repr(s.ROLLBACK)+")")
 result=subprocess.run(["/usr/bin/python3","-I","-B","-c",code],user=1000,group=1000,extra_groups=(),
  env={"PATH":"/usr/bin:/bin","HOME":"/home/al","USER":"al","LOGNAME":"al","LANG":"C.UTF-8"},
  capture_output=True,text=True,timeout=110,check=False)
 need(result.returncode==0,"GUARDED_NATIVE_REVALIDATION")
 control=json.loads(raw_file(s.STATE/"production-control-state.json",0o600));drift=json.loads(raw_file(s.STATE/"production-drift.json",0o600))
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))).total_seconds()
 need(control["circuit_breaker"]["state"]=="closed" and drift["status"]=="pass" and drift["problems"]==[]
  and 0<=age<=180,"GENUINE_NATIVE_ADMISSION")
 need(digest(raw_file(s.DESIRED,0o600))==scope["desired_state_initial_sha256"],"BOUND_INITIAL_POLICY")
 print("NATIVE_HEALTH_DRIFT_AND_GUARDED_BREAKER_REVALIDATION=PASS",flush=True)


def apply(I,s,candidate,engine):
 row=authorization(candidate);root=ledger(candidate);scope=row["scope"]
 tx=InstallTransaction(root/"transaction.json",row["scope_sha256"])
 if tx.queued:
  I.command(["/usr/bin/systemctl","--no-block","start","jason-audit-journal-release.service"])
  print("AUDIT_JOURNAL_EXISTING_CONTEXT_REPAIR=RESUMED",flush=True);return
 with maintenance_lock(s):return apply_locked(I,s,candidate,engine,row,tx)


def apply_locked(I,s,candidate,engine,row,tx):
 root=ledger(candidate);scope=row["scope"]
 for path,wanted in s.PROTECTED.items():need(digest(I.read(Path(path)))==wanted,"PROTECTED_BASELINE")
 meta=s.ACTIVE.lstat()
 need(not s.ACTIVE.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_uid==meta.st_gid==1000
  and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==0o600
  and {"device":meta.st_dev,"inode":meta.st_ino}==scope["source_dataset_identity"],"UNCHANGED_RESUME_DATASET")
 need(digest(raw_file(s.CONTROL/"catalog.json",0o444))==scope["pre_cutover_context_repair"]["catalog_before_sha256"],"UNCHANGED_RESUME_CATALOG")
 peers=s.protected_peer_inventory();need(peers==scope["protected_peer_before"],"UNCHANGED_RESUME_PEERS")
 client=engine.DockerEngine()
 for role,before in json.loads(raw_file(root/"producer-before.json",0o400)).items():
  live=client.inspect(role)
  need(live["Id"]==before["Id"] and live["Image"]==before["Image"] and live["State"]["Running"]
   and s.digest(engine.exact_original_configuration(live))==s.digest(engine.exact_original_configuration(before)),"UNCHANGED_RESUME_PRODUCER")
 unit=props(I,"jason-audit-journal-release.service")
 need(unit["MainPID"]=="0" and unit["ActiveState"] in ("failed","inactive"),"NO_RUNNING_WORKER")
 need(not (s.PRIVATE/"initial-cutover-claimed.json").exists(),"NO_INITIAL_DATA_CLAIM")
 # Retain the guarded breaker. Disable only the failed new release's boot path
 # while replacing its exact trusted before-images; no Docker or peer stop.
 I.command(["/usr/bin/systemctl","disable","jason-audit-journal-release.service"])
 private={n:raw_file(root/"before-private"/n,0o400) for n in PRIVATE_NAMES}
 old_policy=json.loads(raw_file(root/"policy-before.json",0o400))
 before=json.loads(raw_file(root/"producer-before.json",0o400))
 need(digest(canon(before))==row["producer_before_sha256"],"BEFORE_SPEC_BINDING")
 try:
  for name,wanted in scope["source_sha256"].items():
   raw=raw_file(root/"source"/name,0o444);need(digest(raw)==wanted,"FROZEN_SOURCE")
   replace_bound(tx,s.BASE/"trusted"/name,raw,old_policy["trusted_source_sha256"][name],0o444)
  profile=s.public_profile(candidate);profile_raw=canon(profile)
  for p in (s.PROFILE,s.CONTROL/"profile.json"):
   replace_bound(tx,p,profile_raw,old_policy["profile_sha256"],0o444)
  policy={**old_policy,"candidate_sha":candidate,"trusted_source_sha256":scope["source_sha256"],
   "public_profile":profile,"profile_sha256":digest(profile_raw)}
  replace_bound(tx,s.POLICY,canon(policy),digest(raw_file(root/"policy-before.json",0o400)),0o600)
  adoption={"action":s.ACTION,"owner_oid":row["owner_oid"],"independently_verified_entra_owner":True,
   "approved_at":row["approved_at"],"scope_sha256":row["scope_sha256"],"policy_sha256":digest(canon(policy)),
   "maintenance_policy_adopted":True,"predecessor_scope_sha256":OLD_SCOPE}
  plan={**adoption,"candidate_sha":candidate,"scope":scope,"claimed_at":row["claimed_at"],
   "oldest_producer_started_at":min(v["State"]["StartedAt"] for v in before.values()),
   "producer_before_sha256":row["producer_before_sha256"]}
  updates={"adoption.json":adoption,"release-plan.json":plan,
   "release-journal.json":{"steps":{},"supersedes_failed_scope_sha256":OLD_SCOPE},
   "protected-ci-before.json":json.loads(raw_file(root/"ci.json",0o400))}
  for name,value in updates.items():replace_bound(tx,s.PRIVATE/name,canon(value),digest(private[name]),0o400)
  initial=canon(s.desired_initial(json.loads(private["desired-before.json"])))
  final=canon(s.desired_after(json.loads(private["desired-before.json"])))
  need(digest(initial)==scope["desired_state_initial_sha256"] and digest(final)==scope["desired_state_after_sha256"],"DECLARED_POLICY_STAGES")
  replace_bound(tx,s.DESIRED,initial,digest(raw_file(root/"desired-current.json",0o400)),0o600)
  tx.write(s.PRIVATE/"desired-final.json",final,0o400)
  I.command(["/usr/bin/systemctl","reset-failed","jason-audit-journal-release.service"])
  revalidate_before_queue(I,s,scope)
  # The new Owner claim is durable before enabling any execution/boot path.
  tx.queued=True
  I.command(["/usr/bin/systemctl","enable","jason-audit-journal-release.service"])
  I.command(["/usr/bin/systemctl","--no-block","start","jason-audit-journal-release.service"])
  print("AUDIT_JOURNAL_EXACT_CONTEXT_REPAIR=QUEUED",flush=True)
  print("ROOT_PROGRESS=/var/lib/jason-audit-journal/control/release-status.json",flush=True)
  print("ORIGINAL_APPROVAL_AND_FAILED_EXECUTION_PRESERVED=true",flush=True)
  print("PRODUCTION_ACCEPTANCE_NOT_YET_CONFIRMED=true",flush=True)
 except Exception:
  if not tx.queued:tx.rollback()
  raise


def execute(I,candidate,payload,modules,c,auth,ci_proof,*,resume=False):
 s=modules["audit_journal_release_scope"]
 if resume:
  row=authorization(candidate)
  need(I.REPO==ledger(candidate)/"source" and I.digest(I.read(Path(I.__file__)))==
   row["source_sha256"]["tools/audit_journal_install.py"],"FROZEN_RESUME_ENTRY")
  need(not (ledger(candidate)/"retry.json").exists(),"ONE_BOUNDED_RETRY")
  atomic(ledger(candidate)/"retry.json",canon({"scope_sha256":row["scope_sha256"],
   "observed_at":datetime.now(timezone.utc).isoformat()}),0o400)
  return apply(I,s,candidate,modules["audit_journal_container_release"])
 scope,before,private,policy,desired=preflight(I,s,modules["audit_journal_container_release"],
  modules["audit_journal_root_inventory"],candidate,payload,c)
 print("AUDIT_JOURNAL_EXACT_PRECUTOVER_REPAIR_PREFLIGHT=PASS",flush=True)
 print("PREVIOUS_APPROVAL_AND_FAILURE_REMAIN_IMMUTABLE=true",flush=True)
 print("REPAIR_SCOPE_SHA256="+digest(canon(scope)),flush=True)
 actor=auth["owner"](scope);need(actor==s.OWNER,"EXACT_OWNER")
 again,again_before,again_private,again_policy,again_desired=preflight(I,s,modules["audit_journal_container_release"],
  modules["audit_journal_root_inventory"],candidate,payload,c)
 need(again==scope and again_private==private and again_policy==policy and again_desired==desired,
  "LIVE_REVIEWED_SCOPE_CHANGED")
 claim(I,candidate,payload,scope,before,private,policy,desired,actor,ci_proof)
 return apply(I,s,candidate,modules["audit_journal_container_release"])
