"""Owner-authenticated, *single container start* during exact audit rollback.

Restores only the already-created original-configuration ticket-core container
after Docker 29 normalizes OomKillDisable None -> False. This does not restart
the journal release, modify its protected files, mark its rollback complete,
delete/rename containers, or attempt any new journal cutover.
"""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,stat,time

ACTION="RESTORE-EXACT-PMV4-TICKET-CORE-AFTER-AUDIT-ROLLBACK"
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
OLD_CANDIDATE="20b32548402d160f9c6a5ee33a0a17592eb9fa68"
RECENT_SCOPE="ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3"
ROLLBACK_SHA="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ROLE="jason-pmv4-ticket-core"
BACKUP_BEFORE=ROLE+"-rollback-audit-before-"+OLD_CANDIDATE[:12]
BACKUP_FAILED=ROLE+"-rollback-audit-failed-"+OLD_CANDIDATE[:12]
ROOT=Path("/var/lib/jason-owner-release/audit-journal-ticket-core-rescue")
PRIVATE=Path("/var/lib/jason-audit-journal/private")
CONTROL=Path("/var/lib/jason-audit-journal/control")
STATE=Path("/var/lib/jason/openclaw/release-manager")
POLICY=Path("/etc/jason-owner-release/audit-journal-v1.json")
ACTIVE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive")
MAX_DB=68719476736
LAST_FRESH_SOURCE="dd7c2df61360b4d85d0bd26753ec67782f3c02d2"
LAST_FRESH_GRANT=Path("/var/lib/jason-owner-release/audit-journal-fresh-owner-recovery")/LAST_FRESH_SOURCE/"authorization.json"

def need(ok,label):
    if not ok:raise PermissionError("AUDIT_TICKET_CORE_RESCUE_"+label)

def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def digest(v):
    return hashlib.sha256(v if isinstance(v,bytes) else canon(v)).hexdigest()

def record(path,mode,tx):
    return json.loads(tx.raw_file(path,mode))

def service_status(I,name):
    raw=I.command(["/usr/bin/systemctl","show",name,
                  "-p","ActiveState","-p","SubState","-p","MainPID",
                  "-p","Result","-p","UnitFileState"])
    return dict(line.split("=",1) for line in raw.splitlines() if "=" in line)

def verify_rollback_steps(journal,before):
    need(isinstance(journal.get("started_at"),str) and
         isinstance(journal.get("recovery_started_at"),str) and
         "outcome" not in journal and journal.get("scope_sha256")==RECENT_SCOPE,
         "EXACT_INFLIGHT_RECOVERY_RECORD_REQUIRED")
    steps=journal.get("steps")
    need(isinstance(steps,dict) and set(steps)=={
        "install:"+ROLE,"restore:"+ROLE
    },"ONLY_TICKET_CORE_PARTIAL_REPLACEMENT_ALLOWED")
    first=steps["install:"+ROLE]
    restore=steps["restore:"+ROLE]
    need(first.get("before_id")==before["Id"] and first.get("backup")==BACKUP_BEFORE
         and first.get("verified") is not True and
         first.get("after_id") is None and
         restore.get("backup")==BACKUP_FAILED
         and restore.get("verified") is not True
         and restore.get("after_id") is None,
         "ORIGINAL_ROLLBACK_STEP_CHANGED")
    return restore["before_id"]

def compare_exact_original(impl,current,before):
    expected=impl.exact_original_configuration(before)
    need(expected["HostConfig"].get("OomKillDisable") is None and
         current["HostConfig"].get("OomKillDisable") is False,
         "DIAGNOSED_DOCKER_NORMALIZATION_NOT_PRESENT")
    need(impl.configuration_matches(current,expected),
         "UNKNOWN_CONTAINER_CONFIGURATION")
    # Permit no other normalization; check semantic engine re-readback of each
    # image, secret config, mount/port/security/network attribute in memory.
    return expected

def preflight(I,s,modules,c,candidate,payload,*,production=True):
    need(os.geteuid()==0 or not production,"ROOT_ONLY")
    need(len(candidate)==40 and all(v in "0123456789abcdef" for v in candidate),
         "REVIEWED_SOURCE_ID")
    need(ROLE in modules["audit_journal_container_release"].ROLES,
         "SINGLE_APPROVED_ROLE")
    if production:
        I.installation_parent_custody(c)
        need(Path("/opt/jason/current").resolve().name==ROLLBACK_SHA,
             "UNRELATED_PRODUCTION_RELEASE")
        need(not (ROOT/candidate).exists(),"ALREADY_USED_RESCUE_SOURCE")
    tx=modules["audit_journal_install_transaction"]
    plan=record(PRIVATE/"release-plan.json",0o400,tx)
    journal=record(PRIVATE/"release-journal.json",0o400,tx)
    before=record(PRIVATE/"producer-before.json",0o400,tx)
    adoption=record(PRIVATE/"adoption.json",0o400,tx)
    policy=record(POLICY,0o600,tx)
    catalog=record(CONTROL/"catalog.json",0o444,tx)
    latest_grant=record(LAST_FRESH_GRANT,0o400,tx)
    need(plan.get("candidate_sha")==OLD_CANDIDATE and
         plan.get("scope_sha256")==RECENT_SCOPE and
         plan.get("owner_oid")==OWNER and
         plan.get("independently_verified_entra_owner") is True and
         digest(plan["scope"])==RECENT_SCOPE and
         plan["scope"]["policy"]=={
             "candidate_sha":OLD_CANDIDATE,"rollback_sha":ROLLBACK_SHA},
         "EXACT_OWNER_BOUND_RELEASE_PLAN")
    need(adoption.get("owner_oid")==OWNER and
         adoption.get("scope_sha256")==RECENT_SCOPE and
         adoption.get("independently_verified_entra_owner") is True and
         policy.get("candidate_sha")==OLD_CANDIDATE and
         policy.get("enabled") is True and
         plan["scope"]["source_sha256"]==policy.get("trusted_source_sha256"),
         "CURRENT_OWNER_AND_TRUSTED_SOURCE")
    need(latest_grant.get("action")==
             "FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL" and
         latest_grant.get("candidate_sha")==LAST_FRESH_SOURCE and
         latest_grant.get("installed_candidate_sha")==OLD_CANDIDATE and
         latest_grant.get("scope_sha256")==RECENT_SCOPE and
         latest_grant.get("owner_oid")==OWNER and
         latest_grant.get("independently_verified_entra_owner") is True and
         latest_grant.get("one_use") is True and
         latest_grant.get("old_approval_reused") is False and
         latest_grant.get("new_execution_claim") is True,
         "PREVIOUS_INDEPENDENT_OWNER_GRANT_MISSING")
    need(catalog.get("mode")=="legacy" and catalog.get("generation")==0 and
         catalog.get("epoch") is None and catalog.get("segments")==[],
         "UNMIGRATED_LEGACY_REQUIRED")
    need(set(before)==set(modules["audit_journal_container_release"].ROLES) and
         digest(before)==plan.get("producer_before_sha256"),
         "RECORDED_BEFORE_SPEC_CHANGED")
    role_before=before[ROLE]
    need(role_before.get("Name")=="/"+ROLE and
         role_before.get("State",{}).get("Running") is True,
         "ORIGINAL_TICKET_CORE_NOT_RECORDED_RUNNING")
    previous_dormant_id=verify_rollback_steps(journal,role_before)
    release=service_status(I,"jason-audit-journal-release.service")
    timer=service_status(I,"jason-audit-journal-maintenance.timer")
    need(release.get("ActiveState")=="failed" and
         release.get("MainPID")=="0" and
         timer.get("ActiveState")=="inactive" and
         timer.get("UnitFileState")=="disabled",
         "RELEASE_MUST_BE_QUIESCED")
    if production:
        for name,expected in s.PROTECTED.items():
            need(digest(I.read(Path(name)))==expected,
                 "PROTECTED_PRODUCTION_BASELINE_CHANGED")
        ds=ACTIVE.lstat()
        need(stat.S_ISREG(ds.st_mode) and not ACTIVE.is_symlink() and
             (ds.st_dev,ds.st_ino)==(66306,10261846) and
             ds.st_uid==ds.st_gid==1000 and
             stat.S_IMODE(ds.st_mode)==0o600 and
             0<ds.st_size<=MAX_DB and
             ARCHIVE.stat().st_dev!=ds.st_dev,
             "CANONICAL_LEGACY_DATABASE_CHANGED")
        need(not any((ARCHIVE/"governed-audit/orchestration").iterdir()) and
             not any((CONTROL.parent/"pending").iterdir()),
             "MIGRATION_ALREADY_PUBLISHED")
        control=record(STATE/"production-control-state.json",0o600,tx)
        need(control.get("circuit_breaker",{}).get("state")=="open",
             "OPEN_PRODUCTION_BREAKER_REQUIRED")
    impl=modules["audit_journal_container_release"]
    engine=impl.DockerEngine()
    current=engine.inspect(ROLE)
    old=engine.lookup(BACKUP_BEFORE,required=True)
    dormant=engine.lookup(BACKUP_FAILED,required=True)
    need(current["State"]["Status"]=="created" and
         old["State"]["Running"] is False and
         dormant["State"]["Status"]=="created",
         "EXACT_STOPPED_REPLACEMENT_SET")
    need(old["Id"]==role_before["Id"] and
         old["Image"]==role_before["Image"] and
         old["Config"]==role_before["Config"] and
         old["HostConfig"]==role_before["HostConfig"],
         "ORIGINAL_BEFORE_IMAGE_CHANGED")
    need(dormant["Id"]==previous_dormant_id and
         impl.configuration_matches(dormant,
            impl.planned_configuration(role_before,OLD_CANDIDATE)),
         "DORMANT_PLANNED_IMAGE_CHANGED")
    original_spec=compare_exact_original(impl,current,role_before)
    need(current["Image"]==role_before["Image"],
         "CURRENT_ORIGINAL_IMAGE_CHANGED")
    for role in ("jason-runtime","jason-mcp-pilot"):
        live=engine.inspect(role)
        need(live["Id"]==before[role]["Id"] and live["State"]["Running"] is True and
             impl.configuration_matches(live,impl.exact_original_configuration(before[role])),
             "PROTECTED_UNRELATED_CONSUMER_CHANGED")
    scope={
        "schema_version":"1.0",
        "action":ACTION,
        "policy":{"candidate_sha":candidate,"rollback_sha":ROLLBACK_SHA},
        "owner_oid_expected":OWNER,
        "existing_failed_release_candidate":OLD_CANDIDATE,
        "existing_failed_scope_sha256":RECENT_SCOPE,
        "prior_plan_sha256":digest(plan),
        "prior_journal_sha256":digest(journal),
        "prior_adoption_sha256":digest(adoption),
        "immediately_prior_licensed_owner_grant_sha256":digest(latest_grant),
        "legacy_catalog_sha256":digest(catalog),
        "protected_original_role_id":role_before["Id"],
        "ticket_core_current_created_id":current["Id"],
        "ticket_core_original_before_backup_id":old["Id"],
        "ticket_core_dormant_failed_backup_id":dormant["Id"],
        "current_created_configuration_sha256":digest(current["Config"]),
        "current_created_host_configuration_sha256":digest(current["HostConfig"]),
        "approved_original_configuration_sha256":digest(original_spec),
        "source_bytes_sha256":digest(payload["tools/audit_journal_ticket_core_rescue.py"]),
        "reviewed_matcher_sha256":digest(payload["tools/audit_journal_container_release.py"]),
        "immutable_prior_approval_reused":False,
        "one_exact_docker_action":"POST /containers/"+current["Id"]+"/start",
        "installation_targets":[
            "docker://containers/"+current["Id"]+"/start",
            str(ROOT/candidate/"authorization.json"),
            str(ROOT/candidate/"result.json"),
        ],
        "scope_excludes_docker_create_rename_remove":True,
        "scope_excludes_all_database_changes":True,
        "scope_excludes_systemd_service_restart":True,
        "scope_excludes_production_breaker_reset":True,
        "standing_authority":False,
        "global_freeze_unchanged":True,
    }
    return scope,{"current":current,"before":before,"original":original_spec,
                  "prior_scope_sha256":RECENT_SCOPE}

def root_dir(path):
    m=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(m.st_mode) and
         m.st_uid==m.st_gid==0 and
         not (m.st_mode&0o022),"ROOT_EVIDENCE_DIRECTORY_CUSTODY")

def execute(I,s,modules,c,auth,candidate,payload):
    need(os.geteuid()==0 and candidate!="","ROOT_EXACT_CANDIDATE")
    with auth["locks"]():
        scope,_=preflight(I,s,modules,c,candidate,payload)
        print("TICKET_CORE_EXACT_READONLY_PREFLIGHT=PASS",flush=True)
        print("EXACT_OWNER_ACTION="+ACTION,flush=True)
        print("REVIEWED_SOURCE_SHA="+candidate,flush=True)
        print("OWNER_SCOPE_SHA256="+digest(scope),flush=True)
        actor=auth["owner"](scope)
        need(actor==OWNER,"INDEPENDENT_LICENSED_OWNER_REQUIRED")
        again,_=preflight(I,s,modules,c,candidate,payload)
        need(again==scope,"STATE_CHANGED_DURING_OWNER_APPROVAL")
        # No empty one-use record may be rewritten or recreated.
        parent=ROOT.parent
        root_dir(parent)
        if not ROOT.exists():
            ROOT.mkdir(mode=0o700)
            os.chown(ROOT,0,0);ROOT.chmod(0o700)
        root_dir(ROOT)
        child=ROOT/candidate
        need(not child.exists(),"ONE_USE_RESCUE_ALREADY_CONSUMED")
        child.mkdir(mode=0o700);os.chown(child,0,0);child.chmod(0o700)
        modules["audit_journal_install_transaction"].sync(ROOT)
        tx=modules["audit_journal_install_transaction"]
        approval={
            "schema_version":"1.0","action":ACTION,
            "candidate_sha":candidate,"rollback_sha":ROLLBACK_SHA,
            "scope_sha256":digest(scope),"owner_oid":actor,
            "independently_verified_entra_owner":True,
            "approved_at":datetime.now(timezone.utc).isoformat(),
            "old_approval_reused":False,"one_use":True,
            "scope":scope,
        }
        tx.atomic(child/"authorization.json",canon(approval),0o400)
        # A fresh one-use authorization is now consumed: never silently
        # retry POST on ambiguous transport error or interrupted execution.
        impl=modules["audit_journal_container_release"]
        engine=impl.DockerEngine()
        current=engine.inspect(ROLE)
        need(current["Id"]==scope["ticket_core_current_created_id"] and
             current["State"]["Status"]=="created" and
             impl.configuration_matches(current,scope_original(scope,impl,engine,modules)),
             "DOCKER_STATE_CHANGED_AFTER_APPROVAL")
        try:
            engine.call("POST","/containers/"+current["Id"]+"/start",timeout=45)
        except Exception:
            # Unknown transport outcome. Read back once and record; no
            # replacement, reset, or automatic second write.
            now=engine.inspect(ROLE)
            if now["Id"]!=current["Id"] or not now["State"]["Running"]:
                tx.atomic(child/"result.json",canon({
                    "status":"needs_governed_human_reconciliation",
                    "action":ACTION,"scope_sha256":digest(scope),
                    "observed_at":datetime.now(timezone.utc).isoformat(),
                    "no_second_write_attempted":True,
                }),0o400)
                raise
        # Read-only postcondition can wait for the existing container's
        # healthcheck; it must never start a second container.
        deadline=time.monotonic()+90
        while True:
            live=engine.inspect(ROLE)
            good=(live["Id"]==current["Id"] and
                  live["State"]["Running"] is True and
                  impl.configuration_matches(live,scope_original(scope,impl,engine,modules)))
            health=live["State"].get("Health",{}).get("Status")
            if good and health in (None,"healthy"):
                break
            need(time.monotonic()<deadline,"RESTORED_CONTAINER_NOT_HEALTHY")
            time.sleep(2)
        result={
            "status":"ticket_core_running_verified",
            "schema_version":"1.0","action":ACTION,
            "scope_sha256":digest(scope),
            "restored_container_id":current["Id"],
            "status_health":health or "no_healthcheck",
            "observed_at":datetime.now(timezone.utc).isoformat(),
            "original_before_backup_preserved":True,
            "dormant_planned_backup_preserved":True,
            "direct_production_database_mutation":False,
            "audit_journal_release_not_restarted":True,
            "audit_journal_rollback_not_closed":True,
        }
        tx.atomic(child/"result.json",canon(result),0o400)
        print("EXACT_TICKET_CORE_SERVICE_RESTORED=PASS",flush=True)
        print("JOURNAL_MIGRATION_AND_ROLLBACK_STILL_PENDING=true",flush=True)

def scope_original(scope,impl,engine,modules):
    """Independently reconstitute exact trusted before-config after consent."""
    tx=modules["audit_journal_install_transaction"]
    before=record(PRIVATE/"producer-before.json",0o400,tx)[ROLE]
    need(before["Id"]==scope["protected_original_role_id"],
         "ORIGINAL_ROOT_BEFORE_ID_CHANGED")
    expected=impl.exact_original_configuration(before)
    need(digest(expected)==scope["approved_original_configuration_sha256"],
         "ORIGINAL_ROOT_CONFIG_CHANGED")
    return expected
