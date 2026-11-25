"""Exactly two legacy audit barrier trigger removals after failed journal rollback.

Root-only / one-use / independently verified licensed Entra Owner. This action
does not reconcile the failed journal or replay migration authority. SQLite
operations run as its original UID1000 owner with a single explicit SQL
transaction; do not use a Root SQLite connection.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,os,stat,subprocess

ACTION="RESTORE-EXACT-LEGACY-AUDIT-ADMISSION-AFTER-FAILED-MIGRATION"
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
OLD="20b32548402d160f9c6a5ee33a0a17592eb9fa68"
OLD_SCOPE="ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3"
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
RESCUE="62e2eb2e2edabd08ea0795bc9d0ba4762f10eaa6"
RESCUE_SCOPE="7290ced4ccda74f5cd8fce19f4a7ac61721338eabf1d29db70c84f12e9188099"
ROOT=Path("/var/lib/jason-owner-release/audit-journal-legacy-admission-rescue")
PRIOR_RESCUE=Path("/var/lib/jason-owner-release/audit-journal-ticket-core-rescue")/RESCUE
PRIVATE=Path("/var/lib/jason-audit-journal/private")
CONTROL=Path("/var/lib/jason-audit-journal/control")
POLICY=Path("/etc/jason-owner-release/audit-journal-v1.json")
ACTIVE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive")
STATE=Path("/var/lib/jason/openclaw/release-manager")
CANDIDATE_ROLE="jason-pmv4-ticket-core"
PINNED_ID="795c5c2876bb676e797813383d50dd540d5a52b44e04ebb31b95e576ea72f1e5"
EXPECTED_TRIGGER_SHA={
    "audit_journal_maintenance_admission":"c29b47ffd6a24eeccfc967d6192d0ecf217af570b1ce566e7a2f60b4b53169ac",
    "audit_journal_maintenance_invoking":"e5ff3d44da5e6ac6098ee9adbb3a64cc477850ffbd7744106c2b4783077139fc",
}
SQL_PROGRAM=r"""
import hashlib,json,os,sqlite3,sys
assert os.geteuid()==1000 and os.getegid()==1000 and len(sys.argv)==3
mode,path=sys.argv[1:]
assert mode in ('read','clear')
names={
 'audit_journal_maintenance_admission':'c29b47ffd6a24eeccfc967d6192d0ecf217af570b1ce566e7a2f60b4b53169ac',
 'audit_journal_maintenance_invoking':'e5ff3d44da5e6ac6098ee9adbb3a64cc477850ffbd7744106c2b4783077139fc',
}
c=sqlite3.connect('file:'+path+'?mode='+('ro' if mode=='read' else 'rw'),uri=True,
                  timeout=8,isolation_level=None)
try:
 def observed():
  rows=c.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'audit_journal_maintenance_%'").fetchall()
  return {name:(table,hashlib.sha256(sql.encode()).hexdigest()) for name,table,sql in rows}
 before=observed()
 if mode=='clear':
  assert before=={n:('orchestration_events',sha) for n,sha in names.items()},'Unexpected trigger'
  c.execute('BEGIN IMMEDIATE')
  try:
   assert observed()==before,'Concurrent trigger modification'
   c.execute('DROP TRIGGER audit_journal_maintenance_admission')
   c.execute('DROP TRIGGER audit_journal_maintenance_invoking')
   assert observed()=={},'Triggers not cleared'
   c.execute('COMMIT')
  except Exception:
   c.execute('ROLLBACK');raise
 after=observed()
 print(json.dumps({'operation':mode,'before':before,'after':after,
    'only_exact_two_ddl_drops':mode=='clear',
    'writer_uid':os.geteuid()},sort_keys=True,separators=(',',':')),flush=True)
finally:c.close()
"""

def need(ok,reason):
    if not ok:raise PermissionError("JOURNAL_LEGACY_ADMISSION_RESCUE_"+reason)

def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def digest(v):
    return sha256(v if isinstance(v,bytes) else canonical(v)).hexdigest()

def record(tx,path,mode):
    return json.loads(tx.raw_file(path,mode))

def sql(mode):
    need(mode in ("read","clear"),"SQL_MODE")
    command=["/usr/bin/python3","-I","-B","-c",SQL_PROGRAM,mode,str(ACTIVE)]
    result=subprocess.run(
        command,stdin=subprocess.DEVNULL,capture_output=True,text=True,
        timeout=45,check=False,user=1000,group=1000,extra_groups=(),
        start_new_session=True,env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8",
                                    "HOME":"/home/al","USER":"al","LOGNAME":"al"})
    need(result.returncode==0,"SQL_OPERATION_EXIT_"+str(result.returncode))
    value=json.loads(result.stdout)
    need(value.get("writer_uid")==1000 and value.get("operation")==mode,
         "SQL_IDENTITY_OR_MODE")
    return value

def unit(I,name):
    out=I.command(["/usr/bin/systemctl","show",name,
                   "-p","ActiveState","-p","MainPID",
                   "-p","Result","-p","UnitFileState"])
    return dict(x.split("=",1) for x in out.splitlines() if "=" in x)

def preflight(I,s,modules,c,candidate,payload,*,production=True):
    need(os.geteuid()==0 or not production,"ROOT_ONLY")
    tx=modules["audit_journal_install_transaction"]
    impl=modules["audit_journal_container_release"]
    if production:
        I.installation_parent_custody(c)
        need(Path("/opt/jason/current").resolve().name==ROLLBACK,
             "UNRELATED_HOST_RELEASE")
        need(not (ROOT/candidate).exists(),"ALREADY_CLAIMED")
        for path,hash_value in s.PROTECTED.items():
            need(digest(I.read(Path(path)))==hash_value,
                 "PROTECTED_HOST_CHANGED")
    plan=record(tx,PRIVATE/"release-plan.json",0o400)
    journal=record(tx,PRIVATE/"release-journal.json",0o400)
    adoption=record(tx,PRIVATE/"adoption.json",0o400)
    original=record(tx,PRIVATE/"producer-before.json",0o400)
    policy=record(tx,POLICY,0o600)
    catalog=record(tx,CONTROL/"catalog.json",0o444)
    auth=record(tx,PRIOR_RESCUE/"authorization.json",0o400)
    rescue=record(tx,PRIOR_RESCUE/"result.json",0o400)
    need(plan.get("candidate_sha")==OLD and
         plan.get("scope_sha256")==OLD_SCOPE and
         plan.get("owner_oid")==OWNER and
         plan.get("independently_verified_entra_owner") is True and
         digest(plan["scope"])==OLD_SCOPE and
         plan["scope"]["policy"]=={"candidate_sha":OLD,"rollback_sha":ROLLBACK},
         "EXACT_FAILED_OWNER_RELEASE")
    need(journal.get("scope_sha256")==OLD_SCOPE and
         "recovery_started_at" in journal and
         "outcome" not in journal and
         set(journal.get("steps",{}))=={
             "install:"+CANDIDATE_ROLE,"restore:"+CANDIDATE_ROLE},
         "INCOMPLETE_KNOWN_ROLLBACK_REQUIRED")
    need(adoption.get("scope_sha256")==OLD_SCOPE and
         adoption.get("owner_oid")==OWNER and
         policy.get("candidate_sha")==OLD and policy.get("enabled") is True and
         plan["scope"]["source_sha256"]==policy.get("trusted_source_sha256") and
         digest(original)==plan.get("producer_before_sha256") and
         set(original)==set(impl.ROLES),
         "ORIGINAL_OWNER_ADOPTION_AND_SOURCE")
    need(catalog.get("mode")=="legacy" and catalog.get("generation")==0 and
         catalog.get("epoch") is None and catalog.get("segments")==[],
         "MIGRATED_OR_UNEXPECTED_CATALOG")
    need(auth.get("candidate_sha")==RESCUE and
         auth.get("action")=="RESTORE-EXACT-PMV4-TICKET-CORE-AFTER-AUDIT-ROLLBACK" and
         auth.get("scope_sha256")==RESCUE_SCOPE and
         auth.get("owner_oid")==OWNER and
         auth.get("independently_verified_entra_owner") is True and
         auth.get("one_use") is True and auth.get("old_approval_reused") is False and
         rescue.get("status")=="ticket_core_running_verified" and
         rescue.get("scope_sha256")==RESCUE_SCOPE and
         rescue.get("restored_container_id")==PINNED_ID,
         "PREVIOUS_TICKET_CORE_RECOVERY_NOT_VERIFIED")
    release=unit(I,"jason-audit-journal-release.service")
    timer=unit(I,"jason-audit-journal-maintenance.timer")
    need(release.get("ActiveState")=="failed" and release.get("MainPID")=="0" and
         timer.get("ActiveState")=="inactive" and
         timer.get("UnitFileState")=="disabled",
         "FAILED_RELEASE_NOT_QUIESCED")
    if production:
        m=ACTIVE.lstat()
        need(not ACTIVE.is_symlink() and stat.S_ISREG(m.st_mode) and
             (m.st_dev,m.st_ino)==(66306,10261846) and
             m.st_uid==m.st_gid==1000 and stat.S_IMODE(m.st_mode)==0o600 and
             0<m.st_size<68719476736 and
             ARCHIVE.stat().st_dev!=m.st_dev,
             "LEGACY_DATASET_CHANGED")
        need(not any((ARCHIVE/"governed-audit/orchestration").iterdir()) and
             not any((CONTROL.parent/"pending").iterdir()),
             "SEGMENTED_CUTOVER_ALREADY_STARTED")
        control=record(tx,STATE/"production-control-state.json",0o600)
        need(control.get("circuit_breaker",{}).get("state")=="open",
             "CURRENT_BREAKER_NOT_IN_APPROVED_HOLD")
    eng=impl.DockerEngine()
    core=eng.inspect(CANDIDATE_ROLE)
    need(core["Id"]==PINNED_ID and core["State"]["Running"] is True and
         core["State"].get("Health",{}).get("Status")=="healthy" and
         impl.configuration_matches(core,impl.exact_original_configuration(original[CANDIDATE_ROLE])),
         "RESTORED_TICKET_CORE_CONFIG_CHANGED")
    for role in ("jason-runtime","jason-mcp-pilot"):
        row=eng.inspect(role)
        need(row["Id"]==original[role]["Id"] and row["State"]["Running"] is True and
             impl.configuration_matches(row,impl.exact_original_configuration(original[role])),
             "OTHER_CORE_CHANGED")
    before=sql("read")
    required={n:["orchestration_events",hash_value] for n,hash_value in EXPECTED_TRIGGER_SHA.items()}
    need(before["before"]==required and before["after"]==required,
         "EXACT_MAINTENANCE_TRIGGER_EVIDENCE_CHANGED")
    scope={
        "schema_version":"1.0","action":ACTION,
        "policy":{"candidate_sha":candidate,"rollback_sha":ROLLBACK},
        "owner_oid_expected":OWNER,
        "prior_failed_release_scope":OLD_SCOPE,
        "prior_release_plan_sha256":digest(plan),
        "prior_incomplete_journal_sha256":digest(journal),
        "prior_ticket_core_rescue_authorization_sha256":digest(auth),
        "prior_ticket_core_rescue_result_sha256":digest(rescue),
        "source_sha256":digest(payload["tools/audit_journal_legacy_admission_rescue.py"]),
        "prior_archive_catalog_sha256":digest(catalog),
        "database_identity":{"device":66306,"inode":10261846},
        "exact_installed_legacy_trigger_sha256":EXPECTED_TRIGGER_SHA,
        "atomic_ddl_action":[
            "DROP TRIGGER audit_journal_maintenance_admission",
            "DROP TRIGGER audit_journal_maintenance_invoking",
        ],
        "one_use":True,"standing_authority":False,
        "all_business_provider_writes_excluded":True,
        "all_orchestration_event_row_mutations_excluded":True,
        "source_history_preserved":True,
        "failed_journal_receipt_unchanged":True,
        "release_service_restart_excluded":True,
        "native_breaker_reset_excluded":True,
        "rollback_or_journal_migration_not_claimed":True,
        "global_freeze_unchanged":True,
        "installation_targets":[
            "sqlite:///var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3#two-exact-maintenance-triggers",
            str(ROOT/candidate/"authorization.json"),str(ROOT/candidate/"result.json"),
        ],
    }
    return scope

def root_parent(path):
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(info.st_mode) and
         info.st_uid==info.st_gid==0 and not info.st_mode&0o022,
         "ROOT_RECORD_PARENT_CUSTODY")

def execute(I,s,modules,c,auth,candidate,payload):
    need(os.geteuid()==0,"ISOLATED_ROOT_REQUIRED")
    with auth["locks"]():
        scope=preflight(I,s,modules,c,candidate,payload)
        print("EXACT_LEGACY_ADMISSION_READONLY_PREFLIGHT=PASS",flush=True)
        print("EXACT_OWNER_ACTION="+ACTION,flush=True)
        print("OWNER_SCOPE_SHA256="+digest(scope),flush=True)
        actor=auth["owner"](scope)
        need(actor==OWNER,"EXACT_LICENSED_OWNER_REQUIRED")
        need(preflight(I,s,modules,c,candidate,payload)==scope,
             "PRECONDITIONS_CHANGED_AFTER_OWNER_AUTHENTICATION")
        root_parent(ROOT.parent)
        if not ROOT.exists():
            ROOT.mkdir(mode=0o700);os.chown(ROOT,0,0);ROOT.chmod(0o700)
        root_parent(ROOT)
        child=ROOT/candidate
        need(not child.exists(),"ONE_USE_ALREADY_CLAIMED")
        child.mkdir(mode=0o700);os.chown(child,0,0);child.chmod(0o700)
        tx=modules["audit_journal_install_transaction"]
        tx.sync(ROOT)
        record_value={
            "schema_version":"1.0","action":ACTION,
            "candidate_sha":candidate,"scope_sha256":digest(scope),
            "rollback_sha":ROLLBACK,"owner_oid":actor,
            "independently_verified_entra_owner":True,
            "one_use":True,"claimed_at":datetime.now(timezone.utc).isoformat(),
            "scope":scope,
        }
        tx.atomic(child/"authorization.json",canonical(record_value),0o400)
        # Never retry an ambiguous database transaction under this consumed
        # authority. Subsequent recovery requires a new exact action.
        try:
            changed=sql("clear")
        except Exception:
            tx.atomic(child/"result.json",canonical({
                "status":"requires_readonly_reconciliation",
                "observed_at":datetime.now(timezone.utc).isoformat(),
                "no_retry":True,"scope_sha256":digest(scope)}),0o400)
            raise
        need(changed["before"]=={
            n:["orchestration_events",h] for n,h in EXPECTED_TRIGGER_SHA.items()}
            and changed["after"]=={} and
            changed["only_exact_two_ddl_drops"] is True,
            "EXACT_ADMISSION_RESTORE_NOT_VERIFIED")
        verification=sql("read")
        need(verification["after"]=={} and verification["before"]=={},
             "RESCUE_READBACK_NOT_CLEAR")
        post={
            "schema_version":"1.0","action":ACTION,"status":"legacy_admission_restored",
            "source_sha256":candidate,"scope_sha256":digest(scope),
            "verified_at":datetime.now(timezone.utc).isoformat(),
            "removed_trigger_names":sorted(EXPECTED_TRIGGER_SHA),
            "live_legacy_data_preserved":True,
            "no_release_replay":True,"migration_and_full_rollback_pending":True,
            "native_breaker_still_governing":True,
        }
        tx.atomic(child/"result.json",canonical(post),0o400)
        print("EXACT_LEGACY_ADMISSION_RESTORED=PASS",flush=True)
        print("JOURNAL_MIGRATION_AND_ROLLBACK_STILL_PENDING=true",flush=True)
