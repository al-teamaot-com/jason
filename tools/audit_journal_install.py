#!/usr/bin/env python3
"""One exact independently authenticated journal adoption and release queue.

Source engineering only until reviewed protected Main CI and live Root preflight
pass. No arbitrary command, provider operation or approval database write.
"""
from __future__ import annotations
import argparse,importlib,importlib.util,json,os,re,shutil,stat,subprocess,sys,tempfile
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
REPO=Path(__file__).resolve().parents[1]
PRIMITIVES_SHA="31af4fcfa40e6e976c10dc2bef8709f32e542358f89929b232dc18b8295f027a"
SAFE=("GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null","GIT_OPTIONAL_LOCKS=0",
 "GIT_NO_REPLACE_OBJECTS=1","GIT_GRAFT_FILE=/dev/null","GIT_CONFIG_COUNT=2",
 "GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
 "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null")
USER=("/usr/sbin/runuser","-u","al","--")
EXTRA=("tools/audit_journal_install.py","tools/audit_journal_install_transaction.py",
 "tools/audit_journal_root_inventory.py","tools/audit_journal_signed_owner_bridge.py",
 "implementation/kernel/signed_owner_release.py","tools/pmv4_e_ci_refresh.py",
 "tools/documentation_publisher_install.py","tools/pmv4_e_operational_closure.py","tools/pmv4_e_dispatch_install.py",
 "tools/audit_journal_pre_cutover_repair.py","tools/audit_journal_fresh_owner_recovery.py",
 "tools/audit_journal_ticket_core_rescue.py","tools/audit_journal_legacy_admission_rescue.py",
 "tools/audit_journal_objective_recovery.py","tools/audit_journal_rollback_slot_reservation.py")
OVERRIDES=("93-jason-audit-data-recovery.conf","94-audit-data-compatible-release.conf")
SYSTEMD=Path("/etc/systemd/system")
RECORD=Path("/var/lib/jason-owner-release/audit-journal-install")
CONTEXT_REPAIRS=Path("/var/lib/jason-owner-release/audit-journal-service-context-repairs")

def need(ok,code):
 if not ok:raise PermissionError("JOURNAL_INSTALL_"+code)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(raw):return sha256(raw).hexdigest()
def command_failure(argv,result):
 # Never emit raw arguments, stdout/stderr, credentials or private JSON.
 exe=Path(argv[0]).name
 if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}",exe) is None:exe="unlisted"
 operations={"show","disable","reset-failed","start","enable","daemon-reload","exec",
  "rev-parse","status","ls-remote","show-ref","diff","log","merge-base"}
 operation=next((v for v in argv[1:] if v in operations),"other")
 unit=next((v for v in argv[1:] if re.fullmatch(r"jason-[a-z0-9_.@-]{1,120}\.(service|timer|path)",v)),"none")
 reason="unit_not_loaded" if "not loaded" in (result.stderr or "") else "command_exit"
 return "JOURNAL_INSTALL_COMMAND_FAILED:exe="+exe+":operation="+operation+":unit="+unit+":exit="+str(result.returncode)+":reason="+reason

def denial_text(exc):
 reason=str(exc)
 if reason.startswith("JOURNAL_INSTALL_COMMAND_FAILED:"):return reason[:400]
 return reason.split(":")[0][:160]

def command(argv,timeout=60):
 result=subprocess.run(list(argv),cwd="/",capture_output=True,text=True,timeout=timeout,check=False)
 if result.returncode:raise PermissionError(command_failure(list(argv),result))
 return result.stdout.strip()
def git(*args):
 return command([*USER,"/usr/bin/env",*SAFE,"/usr/bin/git","-C",str(REPO),*args])
def read(path,maximum=2000000):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,"rb") as stream:
  m=os.fstat(stream.fileno())
  need(stat.S_ISREG(m.st_mode) and m.st_nlink==1 and 0<m.st_size<=maximum,"REGULAR_FILE_REQUIRED")
  raw=stream.read(maximum+1);need(len(raw)==m.st_size,"FILE_CHANGED");return raw
def context_record_read(candidate):
 root=CONTEXT_REPAIRS/candidate
 for p in (CONTEXT_REPAIRS,root):
  m=p.lstat();need(not p.is_symlink() and stat.S_ISDIR(m.st_mode) and m.st_uid==m.st_gid==0
   and stat.S_IMODE(m.st_mode)==0o700,"CONTEXT_RECORD_CUSTODY")
 path=root/"authorization.json";m=path.lstat()
 need(not path.is_symlink() and m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o400,"CONTEXT_AUTHORIZATION_CUSTODY")
 row=json.loads(read(path,16000000))
 need(row["candidate_sha"]==candidate and row["scope"]["policy"]["candidate_sha"]==candidate
  and row["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
  and row["independently_verified_entra_owner"] is True and row["scope"]["action"]=="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
  and digest(canonical(row["scope"]))==row["scope_sha256"],"CONTEXT_EXACT_OWNER_SCOPE")
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(row["claimed_at"])).total_seconds()
 need(0<=age<=28800,"CONTEXT_EXECUTION_WINDOW")
 return row

def source(candidate,name):
 path=REPO/name;m=path.lstat()
 if REPO==CONTEXT_REPAIRS/candidate/"source":
  need(not path.is_symlink() and m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o444,"CONTEXT_SOURCE_CUSTODY")
  raw=read(path);proof=context_record_read(candidate)
  need(proof["source_sha256"].get(name)==digest(raw),"CONTEXT_EXACT_SOURCE")
  return raw
 if REPO==RECORD/"source":
  need(m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o444 and not path.is_symlink(),"RESUME_SOURCE_CUSTODY")
  raw=read(path);proof=record_read()
  need(proof["candidate_sha"]==candidate and proof["source_sha256"].get(name)==digest(raw),"RESUME_EXACT_SOURCE")
  return raw
 need(not path.is_symlink() and m.st_uid==1000 and not m.st_mode&0o022,"SOURCE_CUSTODY:"+name)
 raw=read(path)
 result=subprocess.run([*USER,"/usr/bin/env",*SAFE,"/usr/bin/git","-C",str(REPO),
                        "show",candidate+":"+name],capture_output=True,timeout=20,check=True)
 need(raw==result.stdout,"EXACT_SOURCE_REQUIRED:"+name);return raw
def verified_namespace(raw,name,path):
 ns={"__name__":name,"__file__":str(path)};exec(compile(raw,str(path),"exec"),ns);return ns
def primitives(candidate):
 raw=source(candidate,"tools/documentation_publisher_install.py")
 need(digest(raw)==PRIMITIVES_SHA,"PINNED_PRIMITIVES_CHANGED")
 return verified_namespace(raw,"journal_reviewed_primitives",REPO/"tools/documentation_publisher_install.py")["primitives"]()

def staged_modules(candidate):
 # Verified bytes are copied to a new Root-only temporary directory. Production
 # Root imports never search a mutable engineering checkout.
 scope_raw=source(candidate,"tools/audit_journal_release_scope.py")
 scope=verified_namespace(scope_raw,"journal_scope",REPO/"tools/audit_journal_release_scope.py")
 paths=(*scope["SOURCES"],*scope["NATIVE"],*EXTRA,
        *("infrastructure/jason-audit-journal/"+v for v in (*scope["UNITS"],*OVERRIDES)))
 payload={name:source(candidate,name) for name in paths}
 temporary=tempfile.TemporaryDirectory(prefix="jason-audit-reviewed-",dir="/run")
 stage=Path(temporary.name);stage.chmod(0o700)
 for name,raw in payload.items():
  path=stage/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
  path.write_bytes(raw);path.chmod(0o444)
 sys.path.insert(0,str(stage));sys.path.insert(0,str(stage/"implementation"))
 modules={name:importlib.import_module("tools."+name) for name in (
  "audit_journal_release_scope","audit_journal_container_release","audit_journal_root_inventory","pmv4_e_ci_refresh",
  "audit_journal_install_transaction","audit_journal_signed_owner_bridge","audit_journal_pre_cutover_repair",
  "audit_journal_fresh_owner_recovery","audit_journal_ticket_core_rescue",
  "audit_journal_legacy_admission_rescue","audit_journal_objective_recovery")}
 return temporary,payload,modules

def ci(helper,candidate):
 ns=helper.load_pinned_attestor(helper.SOURCE,production=True)
 helper.paginate_required_checks(ns);proof=ns["verify_ci"](candidate)
 need(proof.get("required_ci_passed") is True and proof.get("protected_main")==candidate
      and proof.get("protected_main_ancestor") is True,"PROTECTED_MAIN_CI")
 rows=ns["gh_api"]("repos/al-teamaot-com/jason/actions/workflows/audit-journal-migration-preparation.yml/runs"
  "?head_sha="+candidate+"&event=push&per_page=100",
  "{total:.total_count,rows:[.workflow_runs[]|{name,sha:.head_sha,branch:.head_branch,event,status,conclusion,at:.updated_at}]}")
 good=[r for r in rows.get("rows",[]) if r.get("sha")==candidate and r.get("branch")=="main"
       and r.get("event")=="push" and r.get("status")=="completed" and r.get("conclusion")=="success"]
 need(rows.get("total")==len(rows.get("rows",[])) and len(good)==1,"EXACT_MIGRATION_ACCEPTANCE_CI")
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(good[0]["at"].replace("Z","+00:00"))).total_seconds()
 need(0<=age<=7*86400,"MIGRATION_CI_STALE")
 return proof

def capacity(s):
 active=s.ACTIVE.lstat()
 need(not s.ACTIVE.is_symlink() and stat.S_ISREG(active.st_mode) and active.st_uid==active.st_gid==1000
      and stat.S_IMODE(active.st_mode)==0o600 and active.st_nlink==1 and active.st_size<=68719476736,
      "CANONICAL_DATASET")
 need(os.path.ismount(s.ARCHIVE) and s.ARCHIVE.stat().st_dev!=active.st_dev,"SEPARATE_ARCHIVE_MOUNT_REQUIRED")
 need(shutil.disk_usage(s.ARCHIVE).free>active.st_size*3+4563402752,"ARCHIVE_RECONSTRUCTION_RESTORE_RESERVE")
 need(shutil.disk_usage(s.ACTIVE.parent).free>4563402752,"LOCAL_ACTIVE_WAL_RESERVE")
 return {"device":active.st_dev,"inode":active.st_ino}

def native_gate(s,c):
 need(Path("/opt/jason/current").resolve().name==s.ROLLBACK,"LIVE_BASELINE")
 for path,expected in s.PROTECTED.items():need(digest(read(Path(path)))==expected,"PROTECTED_BASELINE")
 c["verify_units"](retired_files_absent=True);peers=s.protected_peer_inventory()
 control=json.loads(read(s.STATE/"production-control-state.json"))
 drift=json.loads(read(s.STATE/"production-drift.json"))
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))).total_seconds()
 need(control.get("circuit_breaker",{}).get("state")=="closed" and drift.get("status")=="pass"
      and drift.get("problems")==[] and 0<=age<=180,"LIVE_NATIVE_BREAKER_DRIFT")
 for path in (RECORD,s.BASE,s.POLICY,s.PRIVATE.parent,s.CONTROL,s.PROFILE.parent,
              s.ARCHIVE/"governed-audit",s.ARCHIVE/"authority-health-scratch",
              s.ACTIVE.parent/"journal-work"):
  need(not os.path.lexists(path),"NEW_TARGET_ALREADY_PRESENT:"+path.name)
 return peers

def schema_and_sample(s):
 from orchestrator.event_store import _SCHEMA
 # This helper runs as the ordinary writer. Only schema/aggregate sizes leave it.
 code=("import sqlite3,json,hashlib,sys;"
       "a=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True,timeout=2);"
       "a.execute('PRAGMA query_only=ON');b=sqlite3.connect(':memory:');b.executescript(sys.argv[2]);"
       "q=\"SELECT name,sql FROM sqlite_master WHERE tbl_name='orchestration_events' ORDER BY name\";"
       "h=lambda d:hashlib.sha256(json.dumps(d.execute(q).fetchall(),sort_keys=True,separators=(',',':')).encode()).hexdigest();"
       "rows=a.execute('SELECT length(cast(payload as blob)),length(cast(event_id as blob)),"
       "length(cast(execution_id as blob)),length(cast(correlation_id as blob)),length(cast(organization_id as blob)),"
       "length(cast(principal_id as blob)),length(cast(capability_name as blob)),length(cast(stage as blob)),"
       "length(cast(event_type as blob)),length(cast(schema_version as blob)),length(cast(occurred_at as blob)) "
       "FROM orchestration_events ORDER BY rowid DESC LIMIT 2000').fetchall();"
       "print(json.dumps({'actual':h(a),'expected':h(b),'sample_events':len(rows),"
       "'maximum_event_bytes':max((sum(r) for r in rows),default=0),"
       "'maximum_metadata_bytes':max((max(r[1:]) for r in rows),default=0)}));a.close();b.close()")
 result=json.loads(command([*USER,"/usr/bin/python3","-I","-B","-c",code,str(s.ACTIVE),_SCHEMA],timeout=30))
 need(result["actual"]==result["expected"],"EXACT_ORIGINAL_EVENT_SCHEMA")
 profile=s.public_profile("a"*40)
 need(result["sample_events"]>0 and result["maximum_event_bytes"]<=profile["maximum_event_bytes"]
      and result["maximum_metadata_bytes"]<=512,"RECENT_EVENT_ENVELOPE_INCOMPATIBLE")
 return result["actual"]

def recovery_capacity(s,before):
 # Match the native drift policy's declared-prefix population. A stopped
 # preproduction peer or unrelated historical container is not a rollback slot.
 desired=s.desired_after(before)
 names=command(["/usr/bin/docker","ps","-a","--filter","status=exited","--format","{{.Names}}"]).splitlines()
 need(len(names)==len(set(names)) and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",n) for n in names),
      "STOPPED_CONTAINER_INVENTORY")
 stopped=sorted(n for n in names if any(n.startswith(prefix) for prefix in desired["rollback_container_prefixes"]))
 need(len(stopped)<=s.ROLLBACK_LIMIT_BEFORE,"STOPPED_CONTAINER_BASELINE_CAPACITY")
 need(len(stopped)+s.ROLLBACK_CONTAINER_RESERVE<=desired["max_stopped_rollback_containers"],
      "STOPPED_CONTAINER_RECOVERY_CAPACITY")
 return desired,{"existing_count":len(stopped),"existing_names":stopped,
  "limit_before":s.ROLLBACK_LIMIT_BEFORE,"limit_after":desired["max_stopped_rollback_containers"],
  "reserved_slots":s.ROLLBACK_CONTAINER_RESERVE,"cleanup_allowed":False}

def installation_parent_custody(c):
 # Root code, policy and new private state stay under Root-owned parents.
 for parent in (Path("/usr/local/lib/jason"),Path("/etc/jason-owner-release"),
                Path("/etc/systemd/system"),Path("/var/lib"),Path("/srv"),Path("/srv/jason")):
  c["directory"](parent,0)
 # Existing live data belongs to the service account; never chown it to
 # satisfy an installation check. Preserve exact UID, GID and access mode.
 c["directory"](Path("/var/lib/jason"),1000,0o750)

def inspect(s,engine,inventory,candidate,payload,c):
 need(Path("/proc/self/ns/mnt").stat().st_ino==Path("/proc/1/ns/mnt").stat().st_ino,"HOST_MOUNT_NAMESPACE")
 installation_parent_custody(c)
 dataset=capacity(s);peers=native_gate(s,c);schema=schema_and_sample(s)
 for unit in s.UNITS:
  need(not os.path.lexists(SYSTEMD/unit),"NEW_UNIT_ALREADY_PRESENT:"+unit)
 for unit,name in (("docker.service","93-jason-audit-data-recovery.conf"),
  ("jason-pmv4-component-reconcile.service","94-audit-data-compatible-release.conf"),
  ("jason-release-host-reconcile.service","94-audit-data-compatible-release.conf"),
  ("jason-openclaw-authority-health.service","94-audit-journal.conf"),
  ("jason-openclaw-authority-full-integrity.service","94-audit-journal.conf")):
  need(not os.path.lexists(SYSTEMD/(unit+".d")/name),"NEW_OVERRIDE_ALREADY_PRESENT")

 # Keep complete specs private in memory/Root before-image; never print Env.
 client=engine.DockerEngine();before={role:client.inspect(role) for role in engine.ROLES}
 exact_producer_images=s.current_base_images(candidate,observed_mcp_image=before["jason-mcp-pilot"]["Image"])
 for role,row in before.items():
  need(row["Image"]==exact_producer_images[role] and row["State"]["Running"],"EXACT_BASE_CONSUMER:"+role)
  probe="import hashlib,orchestrator.event_store as e;print(hashlib.sha256(open(e.__file__,'rb').read()).hexdigest())"
  need(command(["/usr/bin/docker","exec","--user","1000:1000",role,"python","-B","-c",probe])==s.BASE_STORE,
       "ORIGINAL_EVENT_STORE_SOURCE:"+role)
 handles=inventory.handles(s.ACTIVE);need(handles["complete"],"COMPLETE_ROOT_PROCESS_INVENTORY")
 ids=set(row["Id"] for row in before.values())
 for row in handles["open_handles"]:
  cgroup=Path("/proc")/str(row["pid"])/"cgroup"
  text=cgroup.read_text()
  need(row["uid"]==1000 and any(identifier in text for identifier in ids),"UNBOUND_CANONICAL_READER")
 # Bind both the before-policy and the fixed six-slot delta to Owner scope.
 original=read(s.DESIRED);need(digest(original)==s.DESIRED_BEFORE,"DESIRED_POLICY_BASELINE")
 desired,retention=recovery_capacity(s,json.loads(original))
 archive=s.ARCHIVE.lstat()
 facts={"dataset_identity":dataset,
  "archive_root_metadata":{"uid":archive.st_uid,"gid":archive.st_gid,"mode":oct(stat.S_IMODE(archive.st_mode))},
  "producer_before":{role:{"id":v["Id"],"image":v["Image"],"configuration_sha256":
   s.digest(engine.exact_original_configuration(v))} for role,v in before.items()},
  "producer_after":{role:s.digest(engine.planned_configuration(v,candidate)) for role,v in before.items()},
  "desired_after_sha256":digest(canonical(desired))}
 code={name:digest(payload[name]) for name in s.SOURCES}
 health={name:digest(payload[name]) for name in s.NATIVE}
 units={name:digest(payload["infrastructure/jason-audit-journal/"+name]) for name in (*s.UNITS,*OVERRIDES)}
 scope=s.reviewed_scope(candidate,code,health,units,facts)
 scope["source_schema_sha256"]=schema
 scope["rollback_container_capacity_before"]=retention
 scope["installer_sha256"]=digest(payload["tools/audit_journal_install.py"])
 scope["bootstrap_source_sha256"]={name:digest(payload[name]) for name in EXTRA}
 scope["bootstrap_resume_record"]=str(RECORD)
 scope["bootstrap_retry_limit"]=1
 scope["protected_peer_before"]=peers
 scope["initial_scheduled_acceptance_rollover"]=True
 scope["rollback_desired_state_sha256"]=digest(canonical(s.desired_rollback(json.loads(original))))
 scope["desired_state_initial_sha256"]=digest(canonical(s.desired_initial(json.loads(original))))
 scope["health_native_dropin_sha256"]={name:digest(raw) for name,raw in health_dropins(s).items()}
 return scope,before,original,desired

def health_dropins(s):
 common=("Environment=JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE="+str(s.PROFILE)+"\n"
  "Environment=PYTHONPATH="+str(s.BASE/"trusted/implementation")+"\n"
  "ReadOnlyPaths="+str(s.BASE)+"\n")
 base=s.BASE/"native-health"
 # Read-only SQLite WAL readers need writable -shm mapping support. Allow
 # the exact optional -shm auxiliary only. The journal, WAL data file,
 # parent directory and unrelated governed databases all remain read-only.
 wal_aux="-"+str(s.ACTIVE)+"-shm"
 return {
 "jason-openclaw-authority-health.service":("[Service]\n"+common+"ExecStart=\nExecStart=/usr/bin/python3 "+
 str(base/"openclaw_authority_fast_health.py")+" --output /var/lib/jason/openclaw/operational-health.json "
 "--full-evidence /var/lib/jason/openclaw/operational-full-health.json\n"
 "ReadWritePaths="+wal_aux+"\n").encode(),
 "jason-openclaw-authority-full-integrity.service":("[Service]\n"+common+"ExecStart=\nExecStart=/usr/bin/python3 "+
 str(base/"openclaw_authority_live_audit_full_snapshot.py")+" --output /var/lib/jason/openclaw/operational-full-health.json\n"
 "ReadWritePaths=\nReadWritePaths=/var/lib/jason/openclaw /srv/jason/archive/authority-health-scratch "+wal_aux+"\n").encode()}

def record_read():
 meta=RECORD.lstat();path=RECORD/"approval.json";m=path.lstat()
 need(not RECORD.is_symlink() and meta.st_uid==meta.st_gid==0 and stat.S_IMODE(meta.st_mode)==0o700
      and m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o400,"PRIVATE_APPROVED_RECORD")
 row=json.loads(read(path,16000000))
 need(row["action"]=="ADOPT-EXACT-DAILY-AUDIT-JOURNAL" and row["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
      and row["independently_verified_entra_owner"] is True
      and digest(canonical(row["scope"]))==row["scope_sha256"],"RECORDED_OWNER_SCOPE")
 return row

def save_record(payload,scope,before,original,desired,actor,ci_proof,*,signed_owner=None):
 parent=RECORD.parent;m=parent.lstat()
 need(not parent.is_symlink() and m.st_uid==m.st_gid==0 and not m.st_mode&0o022,"RECORD_PARENT_CUSTODY")
 need(not os.path.lexists(RECORD),"INITIAL_OWNER_CLAIM_ALREADY_EXISTS")
 from tools.audit_journal_install_transaction import atomic,sync
 stage=Path(tempfile.mkdtemp(prefix=".audit-journal-approved-",dir=parent));stage.chmod(0o700)
 stamp=datetime.now(timezone.utc).isoformat()
 row={"action":scope["action"],"owner_oid":actor,"independently_verified_entra_owner":True,
      "approved_at":stamp,"claimed_at":stamp,"candidate_sha":scope["policy"]["candidate_sha"],
      "scope":scope,"scope_sha256":digest(canonical(scope)),
      "source_sha256":{name:digest(raw) for name,raw in payload.items()},
      "producer_before_sha256":digest(canonical(before))}
 if signed_owner is not None:
  need(signed_owner.get("owner_oid")==actor and signed_owner.get("candidate_sha")==scope["policy"]["candidate_sha"]
       and signed_owner.get("scope_sha256")==digest(canonical(scope))
       and signed_owner.get("same_scope_recheck_passed") is True
       and signed_owner.get("new_global_unfreeze") is False,
       "ONE_USE_SIGNED_OWNER_ROOT_BINDING")
  row["signed_chatgpt_owner_approval"]={k:signed_owner[k] for k in (
   "approval_id","signed_owner_proof_sha256","root_stage_receipt_sha256",
   "owner_oid","scope_sha256","candidate_sha","verified_at")}
  row["global_production_freeze_left_active"]=True
 for name,raw in payload.items():
  path=stage/"source"/name;path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
  atomic(path,raw,0o444)
 for name,raw in (("approval.json",canonical(row)),("producer-before.json",canonical(before)),
                 ("desired-before.json",original),("desired-after.json",canonical(desired)),
                 ("protected-ci-before.json",canonical(ci_proof))):
  atomic(stage/name,raw,0o400)
 for folder in sorted((p for p in (stage/"source").rglob("*") if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
  folder.chmod(0o555);sync(folder)
 (stage/"source").chmod(0o555);sync(stage);os.rename(stage,RECORD);sync(parent)

def resume_bootstrap():
 need(os.geteuid()==0 and sys.flags.isolated==1
      and Path(__file__).resolve()==RECORD/"source/tools/audit_journal_install.py","FIXED_ROOT_RESUME_SOURCE")
 row=record_read()
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(row["claimed_at"])).total_seconds()
 need(0<=age<=28800,"EXACT_BOOTSTRAP_EXECUTION_WINDOW")
 need(digest(read(Path(__file__)))==row["scope"]["installer_sha256"],"RESUME_INSTALLER_BINDING")
 for name,expected in row["source_sha256"].items():
  path=REPO/name;m=path.lstat()
  need(not path.is_symlink() and m.st_uid==m.st_gid==0 and m.st_nlink==1
       and stat.S_IMODE(m.st_mode)==0o444 and digest(read(path))==expected,"RESUME_SOURCE_CLOSURE")
 temporary,payload,modules=staged_modules(row["candidate_sha"])
 try:
  c,auth=primitives(row["candidate_sha"]);s=modules["audit_journal_release_scope"]
  from tools.audit_journal_install_transaction import raw_file,atomic
  before=json.loads(raw_file(RECORD/"producer-before.json",0o400))
  need(digest(canonical(before))==row["producer_before_sha256"],"BEFORE_SPECS_CHANGED")
  original=raw_file(RECORD/"desired-before.json",0o400)
  desired=json.loads(raw_file(RECORD/"desired-after.json",0o400))
  evidence=json.loads(raw_file(RECORD/"protected-ci-before.json",0o400))
  with auth["locks"]():
   transaction=RECORD/"transaction.json"
   state=json.loads(raw_file(transaction,0o600)) if transaction.exists() else {}
   if state.get("outcome")=="queued":
    command(["/usr/bin/systemctl","daemon-reload"])
    command(["/usr/bin/systemctl","enable","jason-audit-journal-release.service"])
    command(["/usr/bin/systemctl","--no-block","start","jason-audit-journal-release.service"])
    print("AUDIT_JOURNAL_EXISTING_EXACT_RELEASE=RESUMED",flush=True);return
   retry=RECORD/"bootstrap-retry.json"
   need(not retry.exists(),"BOUNDED_BOOTSTRAP_RETRY_EXHAUSTED")
   atomic(retry,canonical({"scope_sha256":row["scope_sha256"],"observed_at":datetime.now(timezone.utc).isoformat()}),0o400)
   install(s,payload,row["scope"],before,original,desired,row["owner_oid"],evidence,c)
 finally:temporary.cleanup()

def main():
 parser=argparse.ArgumentParser();parser.add_argument("--candidate-sha")
 parser.add_argument("--preflight-only",action="store_true");parser.add_argument("--resume-bootstrap",action="store_true")
 parser.add_argument("--stage-signed-owner-offer",action="store_true")
 parser.add_argument("--adopt-signed-chatgpt-owner",action="store_true")
 parser.add_argument("--repair-before-cutover",action="store_true")
 parser.add_argument("--resume-context-repair",action="store_true")
 parser.add_argument("--fresh-owner-expired-recovery",action="store_true")
 parser.add_argument("--rescue-exact-ticket-core",action="store_true")
 parser.add_argument("--restore-exact-legacy-admission",action="store_true")
 parser.add_argument("--complete-bounded-audit-objective",action="store_true")
 parser.add_argument("--resume-bounded-audit-objective",action="store_true")
 args=parser.parse_args()
 need(sum(bool(flag) for flag in (
  args.preflight_only,args.resume_bootstrap,args.stage_signed_owner_offer,
  args.adopt_signed_chatgpt_owner,args.repair_before_cutover,args.resume_context_repair,
  args.fresh_owner_expired_recovery,args.rescue_exact_ticket_core,
  args.restore_exact_legacy_admission,args.complete_bounded_audit_objective,
  args.resume_bounded_audit_objective))<=1,
  "ONE_EXACT_INSTALLER_OPERATION")
 if args.resume_bootstrap:
  need(args.candidate_sha is None and not args.preflight_only,"EXACT_RESUME_ARGUMENTS");return resume_bootstrap()
 candidate=args.candidate_sha
 need(os.geteuid()==0 and sys.flags.isolated==1 and isinstance(candidate,str)
      and re.fullmatch("[0-9a-f]{40}",candidate),"ISOLATED_ROOT_EXACT_SOURCE")
 if args.resume_context_repair:
  need(REPO==CONTEXT_REPAIRS/candidate/"source","FROZEN_CONTEXT_RESUME_ENTRY")
  context_record_read(candidate)
 else:
  need(git("rev-parse","HEAD")==candidate and git("status","--porcelain","--untracked-files=all")=="","CLEAN_EXACT_CHECKOUT")
 c,auth=primitives(candidate);temporary,payload,modules=staged_modules(candidate)
 try:
  s=modules["audit_journal_release_scope"];engine=modules["audit_journal_container_release"]
  if args.resume_bounded_audit_objective:
   ci_proof=ci(modules["pmv4_e_ci_refresh"],candidate)
   need(ci_proof.get("required_ci_passed") is True,"BOUNDED_RESUME_PROTECTED_CI")
   return modules["audit_journal_objective_recovery"].resume_prequeue(
    SimpleNamespace(**globals()),s,modules,c,auth,candidate,payload)
  if args.complete_bounded_audit_objective:
   ci_proof=ci(modules["pmv4_e_ci_refresh"],candidate)
   need(ci_proof.get("required_ci_passed") is True,"BOUNDED_OBJECTIVE_PROTECTED_CI")
   return modules["audit_journal_objective_recovery"].execute_with_continuation(
    SimpleNamespace(**globals()),s,modules,c,auth,candidate,payload)
  if args.restore_exact_legacy_admission:
   ci_proof=ci(modules["pmv4_e_ci_refresh"],candidate)
   need(ci_proof.get("required_ci_passed") is True,"LEGACY_ADMISSION_RESCUE_PROTECTED_CI")
   return modules["audit_journal_legacy_admission_rescue"].execute(
    SimpleNamespace(**globals()),s,modules,c,auth,candidate,payload)
  if args.rescue_exact_ticket_core:
   ci_proof=ci(modules["pmv4_e_ci_refresh"],candidate)
   need(ci_proof.get("required_ci_passed") is True,"TICKET_CORE_RESCUE_PROTECTED_CI")
   return modules["audit_journal_ticket_core_rescue"].execute(
    SimpleNamespace(**globals()),s,modules,c,auth,candidate,payload)
  if args.fresh_owner_expired_recovery:
   ci_proof=ci(modules["pmv4_e_ci_refresh"],candidate)
   need(ci_proof.get("required_ci_passed") is True,"EXACT_RECOVERY_CI")
   return modules["audit_journal_fresh_owner_recovery"].execute(
    SimpleNamespace(**globals()),s,modules,c,auth,candidate,payload)
  with auth["locks"]():
   if args.resume_context_repair or args.repair_before_cutover:
    ci_proof={} if args.resume_context_repair else ci(modules["pmv4_e_ci_refresh"],candidate)
    return modules["audit_journal_pre_cutover_repair"].execute(SimpleNamespace(**globals()),candidate,
     payload,modules,c,auth,ci_proof,resume=args.resume_context_repair)
   ci_proof=ci(modules["pmv4_e_ci_refresh"],candidate)
   scope,before,original,desired=inspect(s,engine,modules["audit_journal_root_inventory"],candidate,payload,c)
   print("AUDIT_JOURNAL_COMPLETE_ROOT_PREFLIGHT=PASS",flush=True)
   print("REVIEWED_SCOPE_SHA256="+s.digest(scope),flush=True)
   if args.preflight_only:
    print("PRODUCTION_MUTATIONS=false;OWNER_APPROVAL_ISSUED=false",flush=True);return
   bridge=modules["audit_journal_signed_owner_bridge"]
   root_gate={"breaker":"closed","drift":"pass","peers_verified":True,
              "mount_verified":True,"dataset_identity":scope["source_dataset_identity"]}
   if args.stage_signed_owner_offer:
    offer=bridge.create_staged_offer(scope,candidate,root_gate)
    print("AUDIT_SIGNED_OWNER_ROOT_OFFER_STAGED=PASS",flush=True)
    print("OWNER_RELEASE_ID="+offer["release_id"],flush=True)
    print("OWNER_SCOPE_SHA256="+offer["scope_sha256"],flush=True)
    print("OWNER_MANIFEST_SHA256="+offer["manifest_sha256"],flush=True)
    print("GLOBAL_PRODUCTION_FREEZE_REMAINS_ACTIVE=true",flush=True)
    print("NO_DATABASE_OR_PROVIDER_MUTATIONS=true",flush=True)
    return
   signed_owner=None
   if args.adopt_signed_chatgpt_owner:
    signed_owner=bridge.verify_previously_signed_root_offer(
       scope,candidate,root_gate)
    actor=s.OWNER
   else:
    actor=auth["owner"](scope);need(actor==s.OWNER,"EXACT_LICENSED_OWNER")
   again,after,again_original,again_desired=inspect(s,engine,modules["audit_journal_root_inventory"],candidate,payload,c)
   need(again==scope and again_original==original and again_desired==desired,"LIVE_REVIEWED_SCOPE_CHANGED")
   save_record(payload,scope,before,original,desired,actor,ci_proof,
               signed_owner=signed_owner)
   if signed_owner is not None:
    bridge.consume_one_use(candidate,signed_owner)
   install(s,payload,scope,before,original,desired,actor,ci_proof,c)
 finally:temporary.cleanup()

def install(s,payload,scope,before,original,desired,actor,ci_proof,c):
 need(os.geteuid()==0 and sys.flags.isolated==1 and actor==s.OWNER,"VERIFIED_ROOT_OWNER_REQUIRED")
 from tools.audit_journal_install_transaction import InstallTransaction
 tx=InstallTransaction(RECORD/"transaction.json",s.digest(scope));stamp=record_read()["approved_at"]
 try:
  tx.metadata(s.ARCHIVE,0,0,0o755)  # exact top directory only
  for path,mode,gid in (
   (s.BASE,0o755,0),(s.BASE/"trusted",0o755,0),(s.BASE/"native-health",0o755,0),
   (s.PRIVATE.parent,0o755,0),(s.PRIVATE,0o700,0),(s.CONTROL,0o755,0),
   (s.PROFILE.parent,0o755,0),(s.PRIVATE.parent/"pending",0o750,1000),
   (s.ACTIVE.parent/"journal-work",0o711,0),(s.ARCHIVE/"governed-audit",0o750,1000),
   (s.ARCHIVE/"governed-audit/orchestration",0o750,1000),
   (s.ARCHIVE/"governed-audit/rollback",0o750,1000),(s.ARCHIVE/"governed-audit/work",0o711,0)):
   tx.directory(path,mode,gid=gid)
  tx.directory(s.ARCHIVE/"authority-health-scratch",0o700,1000,1000)
  for name in s.SOURCES:
   target=s.BASE/"trusted"/name;tx.directory(target.parent);tx.write(target,payload[name])
  for source_name,installed_name in s.NATIVE.items():tx.write(s.BASE/"native-health"/installed_name,payload[source_name])
  profile=s.public_profile(scope["policy"]["candidate_sha"]);raw_profile=canonical(profile)
  tx.write(s.PROFILE,raw_profile);tx.write(s.CONTROL/"profile.json",raw_profile)
  tx.write(s.CONTROL/"handoff.lock",b"Root-controlled audit handoff\n",0o644)
  tx.write(s.CONTROL/"catalog.json",canonical({"schema_version":"1.0","mode":"legacy","generation":0,
   "epoch":None,"opened_at":stamp,"segments":[]}))
  policy={"schema_version":"1.0","enabled":True,"candidate_sha":scope["policy"]["candidate_sha"],
   "maintenance_operations":["rotate","seal","scrub","recover"],"trusted_source_sha256":scope["source_sha256"],
   "profile_sha256":digest(raw_profile),"public_profile":profile,
   "work":str(s.ARCHIVE/"governed-audit/work"),"local_work":str(s.ACTIVE.parent/"journal-work"),
   "compatible_host_releases":[]}
  tx.write(s.POLICY,canonical(policy),0o600)
  adoption={"action":s.ACTION,"owner_oid":actor,"independently_verified_entra_owner":True,
   "approved_at":stamp,"scope_sha256":s.digest(scope),"policy_sha256":digest(canonical(policy)),
   "maintenance_policy_adopted":True}
  tx.write(s.PRIVATE/"adoption.json",canonical(adoption),0o400)
  plan={**adoption,"candidate_sha":policy["candidate_sha"],"scope":scope,
   "claimed_at":record_read()["claimed_at"],
   "oldest_producer_started_at":min(v["State"]["StartedAt"] for v in before.values()),
   "producer_before_sha256":digest(canonical(before))}
  tx.write(s.PRIVATE/"producer-before.json",canonical(before),0o400)
  tx.write(s.PRIVATE/"desired-before.json",original,0o400)
  tx.write(s.PRIVATE/"desired-rollback.json",canonical(s.desired_rollback(json.loads(original))),0o400)
  tx.write(s.PRIVATE/"desired-final.json",canonical(desired),0o400)
  tx.write(s.PRIVATE/"protected-ci-before.json",canonical(ci_proof),0o400)
  tx.write(s.PRIVATE/"release-plan.json",canonical(plan),0o400)
  for unit in s.UNITS:tx.write(SYSTEMD/unit,payload["infrastructure/jason-audit-journal/"+unit],0o644)
  mappings={"docker.service":("93-jason-audit-data-recovery.conf",),
   "jason-pmv4-component-reconcile.service":("94-audit-data-compatible-release.conf",),
   "jason-release-host-reconcile.service":("94-audit-data-compatible-release.conf",)}
  for unit,names in mappings.items():
   parent=SYSTEMD/(unit+".d");tx.directory(parent)
   for name in names:tx.write(parent/name,payload["infrastructure/jason-audit-journal/"+name],0o644)
  for unit,raw in health_dropins(s).items():
   parent=SYSTEMD/(unit+".d");tx.directory(parent);tx.write(parent/"94-audit-journal.conf",raw,0o644)
  tx.replace(s.DESIRED,canonical(s.desired_initial(json.loads(original))))
  # Source/file bytes are now immutable; no Root worker loads this worktree.
  for path in [Path(r["path"]) for r in tx.state["entries"] if r["kind"]=="file"]:
   directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
   try:os.fsync(directory)
   finally:os.close(directory)
  command(["/usr/bin/systemctl","daemon-reload"])
  # Enabling also creates a future activation path. Record possible execution
  # BEFORE enable/start, so a crash cannot authorize filesystem undo while a
  # boot-started worker may already be running.
  tx.queued=True
  command(["/usr/bin/systemctl","enable","jason-audit-journal-release.service"])
  command(["/usr/bin/systemctl","--no-block","start","jason-audit-journal-release.service"])
  print("AUDIT_JOURNAL_EXACT_ROOT_RELEASE=QUEUED",flush=True)
  print("ROOT_PROGRESS=/var/lib/jason-audit-journal/control/release-status.json",flush=True)
  print("PRODUCTION_ACCEPTANCE_NOT_YET_CONFIRMED=true",flush=True)
 except Exception:
  if not tx.queued:
   tx.rollback();command(["/usr/bin/systemctl","daemon-reload"])
  raise

if __name__=="__main__":
 try:main()
 except Exception as exc:raise SystemExit("DENIED:"+type(exc).__name__+":"+denial_text(exc))
