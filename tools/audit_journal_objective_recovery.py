"""Single Owner decision for the bounded outstanding daily audit objective.

Strictly reconcile a known, interrupted PRE-CUTOVER legacy release to a new
independently verified and test-covered complete migration claim. Root records
the one human objective grant; the sealed installed journal executor owns
cutover, archive, cold restore, verification and already-approved rollback.

No previously consumed exact grant is replayed. Unknown host state denies.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,os,stat,shutil,subprocess,time

from tools import audit_journal_install_transaction as txlib
from tools import audit_journal_rollback_slot_reservation as retention

ACTION="COMPLETE-REMAINING-BOUNDED-DAILY-AUDIT-JOURNAL-OBJECTIVE"
OLD="20b32548402d160f9c6a5ee33a0a17592eb9fa68"
OLD_SCOPE="ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3"
OLD_ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
OLD_OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
PREVIOUS_APPROVED_RECOVERY="dd7c2df61360b4d85d0bd26753ec67782f3c02d2"
RESCUED_CORE="62e2eb2e2edabd08ea0795bc9d0ba4762f10eaa6"
RESCUED_ADMISSION="2e0f6bf4c42fcc3ad4d738fbc1b026525c8c515e"
CORE_ID="795c5c2876bb676e797813383d50dd540d5a52b44e04ebb31b95e576ea72f1e5"
PREVIOUS_GRANT_ROOT=Path("/var/lib/jason-owner-release")
ROOT=PREVIOUS_GRANT_ROOT/"audit-journal-bounded-objective"
MATCHER="tools/audit_journal_container_release.py"
STEPS=(
    "reconcile_exact_interrupted_legacy_release",
    "archive_and_retire_one_exact_historical_rollback_only_if_native_slots_require",
    "refresh_reviewed_docker29_matcher_and_audit_bindings",
    "refresh_real_native_drift_before_queue_without_overriding_breaker",
    "queue_one_full_journal_migration_with_inbuilt_rollback",
    "verify_sealed_history_and_cold_restore",
    "verify_current_writes_daily_rollover_and_native_health",
    "reclaim_legacy_root_storage_after_independent_acceptance",
)
RECOVERY_BRANCHES=(
    "readback_ambiguous_docker_transport_once_without_duplicate_write",
    "restore_exact_precutover_original_consumers_and_clear_exact_barriers",
    "preserve_backup_and_required_history_on_any_failure",
    "rollback_only_within_fresh_claim_and_canonical_guardrails",
    "resume_unqueued_exact_root_install_once_after_transaction_rollback",
    "verify_exact_archived_retirement_and_native_slots_before_resuming",
)
ALLOW_UNIT_CHANGES=False
LIVE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
MAX=68719476736
RESERVE=4563402752
OLD_RESCUE_PROOFS={
    "prior_owner_recovery":(PREVIOUS_GRANT_ROOT/"audit-journal-fresh-owner-recovery"/PREVIOUS_APPROVED_RECOVERY/"authorization.json",
                            "FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL",
                            PREVIOUS_APPROVED_RECOVERY,OLD_SCOPE),
    "ticket_core_rescue":(PREVIOUS_GRANT_ROOT/"audit-journal-ticket-core-rescue"/RESCUED_CORE/"authorization.json",
                           "RESTORE-EXACT-PMV4-TICKET-CORE-AFTER-AUDIT-ROLLBACK",RESCUED_CORE,
                           "7290ced4ccda74f5cd8fce19f4a7ac61721338eabf1d29db70c84f12e9188099"),
    "legacy_admission_rescue":(PREVIOUS_GRANT_ROOT/"audit-journal-legacy-admission-rescue"/RESCUED_ADMISSION/"authorization.json",
                              "RESTORE-EXACT-LEGACY-AUDIT-ADMISSION-AFTER-FAILED-MIGRATION",
                              RESCUED_ADMISSION,
                              "094455d9e032e128f3755c0cfad92e2d4959c70e3a0c4abd0357c139b139d62b"),
}

def need(ok,reason):
    if not ok:raise PermissionError("AUDIT_BOUNDED_OBJECTIVE_"+reason)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def digest(value):
    return sha256(value if isinstance(value,bytes) else canonical(value)).hexdigest()

def read(tx,path,mode):
    return json.loads(tx.raw_file(path,mode))

def read_raw(tx,path,mode):
    return tx.raw_file(path,mode)

def systemd_show(I,name):
    raw=I.command(["/usr/bin/systemctl","show",name,
                   "-p","ActiveState","-p","MainPID","-p","Result","-p","UnitFileState"])
    return dict(line.split("=",1) for line in raw.splitlines() if "=" in line)

def approved_prior_receipts(tx):
    hashes={}
    for label,(path,action,candidate,scope_sha) in OLD_RESCUE_PROOFS.items():
        data=read_raw(tx,path,0o400)
        row=json.loads(data)
        need(row.get("action")==action and
             row.get("candidate_sha")==candidate and
             row.get("scope_sha256")==scope_sha and
             row.get("owner_oid")==OLD_OWNER and
             row.get("independently_verified_entra_owner") is True,
             "PRIOR_IDENTITY_OR_SCOPE_MISMATCH:"+label)
        hashes[label]=digest(data)
    for label,path,expected_status in (
        ("ticket_core_result",PREVIOUS_GRANT_ROOT/"audit-journal-ticket-core-rescue"/RESCUED_CORE/"result.json",
         "ticket_core_running_verified"),
        ("admission_result",PREVIOUS_GRANT_ROOT/"audit-journal-legacy-admission-rescue"/RESCUED_ADMISSION/"result.json",
         "legacy_admission_restored"),
    ):
        raw=read_raw(tx,path,0o400);value=json.loads(raw)
        need(value.get("status")==expected_status and value.get("schema_version")=="1.0",
             "PRIOR_VERIFIED_RECOVERY_MISSING:"+label)
        if label=="ticket_core_result":
            need(value.get("restored_container_id")==CORE_ID,"RESCUED_CORE_ID_CHANGED")
        hashes[label]=digest(raw)
    return hashes

def existing_release(s,I,tx,*,allow_inactive=False):
    policy=read(tx,s.POLICY,0o600)
    adoption=read(tx,s.PRIVATE/"adoption.json",0o400)
    plan=read(tx,s.PRIVATE/"release-plan.json",0o400)
    journal=read(tx,s.PRIVATE/"release-journal.json",0o400)
    previous=read(tx,s.PRIVATE/"producer-before.json",0o400)
    catalog=read(tx,s.CONTROL/"catalog.json",0o444)
    need(plan.get("action")==s.ACTION and plan.get("candidate_sha")==OLD
         and plan.get("scope_sha256")==OLD_SCOPE
         and plan.get("owner_oid")==OLD_OWNER
         and plan.get("independently_verified_entra_owner") is True
         and digest(plan.get("scope"))==OLD_SCOPE
         and plan["scope"]["policy"]=={"candidate_sha":OLD,"rollback_sha":OLD_ROLLBACK},
         "ORIGINAL_EXACT_OWNER_RELEASE_MISMATCH")
    need(adoption.get("owner_oid")==OLD_OWNER and
         adoption.get("scope_sha256")==OLD_SCOPE and
         adoption.get("independently_verified_entra_owner") is True and
         policy.get("enabled") is True and policy.get("candidate_sha")==OLD and
         policy.get("public_profile",{}).get("component_source_sha")==OLD and
         plan["scope"]["source_sha256"]==policy.get("trusted_source_sha256"),
         "OLD_INSTALLED_TRUST_DIVERGED")
    need(journal.get("scope_sha256")==OLD_SCOPE and
         "recovery_started_at" in journal and
         "outcome" not in journal and
         set(journal.get("steps",{}))=={
            "install:jason-pmv4-ticket-core",
            "restore:jason-pmv4-ticket-core",
         },"INTERRUPTED_PRECUTOVER_LEDGER_CHANGED")
    need(digest(previous)==plan.get("producer_before_sha256") and
         catalog.get("mode")=="legacy" and catalog.get("generation")==0 and
         catalog.get("epoch") is None and catalog.get("segments")==[],
         "PRIOR_BEFORE_IMAGE_OR_LEGACY_CATALOG_CHANGED")
    release=systemd_show(I,"jason-audit-journal-release.service")
    need(release.get("ActiveState") in (("failed","inactive") if allow_inactive else ("failed",))
         and release.get("MainPID")=="0"
         and systemd_show(I,"jason-audit-journal-maintenance.timer").get("ActiveState")=="inactive"
         and systemd_show(I,"jason-audit-journal-maintenance.timer").get("UnitFileState")=="disabled",
         "INTERRUPTED_RELEASE_NOT_QUIESCED")
    return {"policy":policy,"adoption":adoption,"plan":plan,
            "journal":journal,"previous":previous,"catalog":catalog}

def validate_reviewed_trust(s,payload,tx):
    changes=[]
    for name in s.SOURCES:
        installed=read_raw(tx,s.BASE/"trusted"/name,0o444)
        reviewed=payload[name]
        if installed!=reviewed:
            need(name==MATCHER,"UNREVIEWED_NATIVE_OR_SQL_SOURCE_DELTA:"+name)
            need(b'if key=="OomKillDisable" and wanted is None and observed is False:continue' in reviewed
                 and b'if key=="Mounts":continue' in reviewed
                 and b'if observed!=wanted:return False' in reviewed,
                 "EXACT_DOCKER_NORMALIZATION_MISSING")
            changes.append(name)
    need(changes==[MATCHER],"EXACT_ONE_TRUSTED_SOURCE_REPAIR_REQUIRED")
    for name,target in s.NATIVE.items():
        need(read_raw(tx,s.BASE/"native-health"/target,0o444)==payload[name],
             "UNEXPECTED_NATIVE_HEALTH_SOURCE:"+name)
    for unit in s.UNITS:
        location=Path("/etc/systemd/system")/unit
        need(read_raw(tx,location,0o644)==payload["infrastructure/jason-audit-journal/"+unit],
             "UNEXPECTED_INSTALLED_SYSTEMD_UNIT:"+unit)
    return changes

def verify_known_native_incident(control,drift,*,now=None,allow_clean=False):
    """Permit only the recorded incident, or a genuine clean resumed state."""
    now=now or datetime.now(timezone.utc)
    observed=datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))
    need(observed.tzinfo is not None and -10<=(now-observed).total_seconds()<=240,
         "NATIVE_DRIFT_EVIDENCE_EXPIRED")
    breaker=control.get("circuit_breaker",{})
    problems=drift.get("problems",[])
    incident=(breaker.get("state")=="open" and
              breaker.get("reason")=="continuous_production_drift_detected")
    if allow_clean and drift.get("status")=="pass" and problems==[]:
        need(incident or breaker.get("state")=="closed",
             "PROTECTED_BREAKER_NOT_IN_KNOWN_INCIDENT_HOLD")
        return {"known_incident":True,"problem_count":0}
    need(incident,"PROTECTED_BREAKER_NOT_IN_KNOWN_INCIDENT_HOLD")
    need(drift.get("status")=="drift_detected" and isinstance(problems,list)
         and 0<len(problems)<=3,"NATIVE_DRIFT_UNEXPECTED_STATUS")
    allowed={
        ("failed_system_unit","jason-audit-journal-release.service","failed"),
        ("failed_system_unit","jason-production-drift-watchdog.service","failed"),
        ("required_system_unit_not_active","jason-audit-journal-maintenance.timer","inactive"),
    }
    rows={(x.get("kind"),x.get("unit") or x.get("name"),x.get("state"))
          for x in problems if isinstance(x,dict)}
    need(len(rows)==len(problems) and rows<=allowed,"UNRELATED_PRODUCTION_NATIVE_DRIFT")
    need(allow_clean or
         ("failed_system_unit","jason-audit-journal-release.service","failed") in rows,
         "KNOWN_FAILED_RELEASE_NOT_IN_NATIVE_EVIDENCE")
    return {"known_incident":True,"problem_count":len(problems)}


def observe_native_readonly(s):
    """Run the already pinned native evaluator without --output or mutation."""
    result=subprocess.run(
        ["/usr/bin/python3",str(s.ROOT_DRIFT_EVALUATOR),"--config",str(s.DESIRED)],
        cwd="/",env={"PATH":"/usr/local/bin:/usr/bin:/bin","HOME":"/root",
                    "LANG":"C.UTF-8"},capture_output=True,text=True,timeout=70,check=False)
    need(result.returncode in (0,2),"NATIVE_READONLY_EVALUATION_UNAVAILABLE")
    row=json.loads(result.stdout)
    need(row.get("schema_version")=="1.0" and
         ((result.returncode==0 and row.get("status")=="pass" and row.get("problems")==[]) or
          (result.returncode==2 and row.get("status")=="drift_detected" and row.get("problems"))),
         "NATIVE_READONLY_RESULT_INVALID")
    return row


def verify_recovery_container_capacity(I,s,eng,previous,desired,*,approved=None,
                                       retirement_verified=False):
    """Historical scope is immutable evidence; count today's native policy."""
    prior=previous["plan"]
    need(prior.get("scope_sha256")==OLD_SCOPE and isinstance(prior.get("scope"),dict)
         and digest(prior["scope"])==OLD_SCOPE,"PREVIOUS_IMMUTABLE_OWNER_SCOPE_CHANGED")
    return retention.plan_capacity(I,s,eng,desired,approved=approved,
                                   retirement_verified=retirement_verified)


def independent_preflight(I,s,modules,c,candidate,payload,*,production=True,
                          existing_bounded_claim=False,approved_review=None):
    need(os.geteuid()==0 or not production,"ROOT_ONLY")
    if production:
        need(len(candidate)==40 and all(ch in "0123456789abcdef" for ch in candidate),
             "REVIEWED_COMMIT_SHA")
        I.installation_parent_custody(c)
        need(Path("/opt/jason/current").resolve().name==OLD_ROLLBACK,
             "UNEXPECTED_RELEASE_BASELINE")
        if existing_bounded_claim:
            need((ROOT/candidate).is_dir() and not (ROOT/candidate).is_symlink(),
                 "BOUNDED_CLAIM_MISSING_OR_CHANGED")
        else:
            need(not (ROOT/candidate).exists(),"ONE_USE_OBJECTIVE_ALREADY_CLAIMED")
        for file,expected in s.PROTECTED.items():
            need(digest(I.read(Path(file)))==expected,"PROTECTED_PRODUCTION_BASELINE_CHANGED")
    tx=modules["audit_journal_install_transaction"]
    eng=modules["audit_journal_container_release"]
    need(not existing_bounded_claim or isinstance(approved_review,dict),
         "APPROVED_RESUME_SCOPE_REQUIRED")
    old=existing_release(s,I,tx,allow_inactive=existing_bounded_claim)
    prior_hashes=approved_prior_receipts(tx)
    if production:
        control=read(tx,s.STATE/"production-control-state.json",0o600)
        # The current policy is checked against the original immutable
        # desired-state proof below. The independent evaluator is read-only.
        drift=observe_native_readonly(s)
        verify_known_native_incident(control,drift,allow_clean=existing_bounded_claim)
    changed=validate_reviewed_trust(s,payload,tx)
    for unit,raw in I.health_dropins(s).items():
        need(read_raw(tx,Path("/etc/systemd/system")/(unit+".d")/"94-audit-journal.conf",0o644)==raw,
             "UNEXPECTED_NATIVE_HEALTH_DROPIN:"+unit)
    for path in (s.PROFILE,s.CONTROL/"profile.json"):
        need(digest(read_raw(tx,path,0o444))==old["policy"].get("profile_sha256"),
             "OLD_PROFILE_BYTES_DIVERGED")
    need(old["adoption"].get("policy_sha256")==digest(old["policy"]),
         "OLD_ADOPTION_POLICY_DIVERGED")
    source=LIVE.lstat()
    need(stat.S_ISREG(source.st_mode) and not LIVE.is_symlink()
         and source.st_uid==source.st_gid==1000 and
         stat.S_IMODE(source.st_mode)==0o600 and source.st_nlink==1
         and (source.st_dev,source.st_ino)==(66306,10261846)
         and 0<source.st_size<MAX,
         "LEGACY_DATASET_IDENTITY_CHANGED")
    need(os.path.ismount(s.ARCHIVE) and s.ARCHIVE.stat().st_dev!=source.st_dev
         and shutil.disk_usage(s.ARCHIVE).free>source.st_size*3+RESERVE
         and shutil.disk_usage(LIVE.parent).free>RESERVE,
         "ROOT_OR_ARCHIVE_CAPACITY_RESERVE")
    need(not any((s.ARCHIVE/"governed-audit/orchestration").iterdir())
         and not any((s.PRIVATE.parent/"pending").iterdir()),
         "SEGMENTED_FILES_ALREADY_PRESENT")
    need(not (s.PRIVATE/"initial-cutover-claimed.json").exists()
         and not (s.PRIVATE/"initial-cutover-complete.json").exists()
         and not (s.PRIVATE/"recovery-recipe.json").exists(),
         "LEGACY_CUTOVER_OR_RECONSTRUCTION_ALREADY_CLAIMED")
    from tools.audit_journal_legacy_admission_rescue import sql as read_admission
    status=read_admission("read")
    need(status["before"]=={} and status["after"]=={} and status["writer_uid"]==1000,
         "LEGACY_ADMISSION_NOT_UNBLOCKED")
    docker=eng.DockerEngine()
    now={role:docker.inspect(role) for role in eng.ROLES}
    need(set(now)==set(eng.ROLES),"PROTECTED_CONSUMER_SET")
    for role,row in now.items():
        previous=old["previous"][role]
        need(row["Image"]==previous["Image"] and row["State"]["Running"] is True
             and eng.configuration_matches(row,eng.exact_original_configuration(previous)),
             "LIVE_CONSUMER_NOT_RESTORED:"+role)
        if role=="jason-pmv4-ticket-core":
            need(row["Id"]==CORE_ID and row["State"].get("Health",{}).get("Status")=="healthy",
                 "TICKET_CORE_RECOVERY_NOT_HEALTHY")
        elif role in ("jason-runtime","jason-mcp-pilot"):
            need(row["Id"]==previous["Id"],"OTHER_CONSUMER_REPLACED")
    if production:
        inventory=modules["audit_journal_root_inventory"].handles(LIVE)
        need(inventory["complete"],"INCOMPLETE_LIVE_DB_HANDLE_INVENTORY")
        for row in inventory["open_handles"]:
            cgroup=(Path("/proc")/str(row["pid"])/"cgroup").read_text()
            need(row["uid"]==1000 and any(v["Id"] in cgroup for v in now.values()),
                 "UNBOUND_LIVE_DB_HANDLE")
    peers=s.protected_peer_inventory()
    old_peers=old["plan"]["scope"]["protected_peer_before"]
    need(set(peers)==set(old_peers),"NATIVE_PROTECTED_PEER_SET_CHANGED")
    for role,was in old_peers.items():
        if role!="jason-pmv4-ticket-core":
            need(peers[role]==was,"UNRELATED_PRODUCTION_PEER_CHANGED:"+role)
    original_desired=read_raw(tx,s.PRIVATE/"desired-final.json",0o400)
    need(digest(json.loads(original_desired))==old["plan"]["scope"]["desired_state_after_sha256"],
         "FINAL_DESIRED_STATE_PROOF_CHANGED")
    rollback_desired=read_raw(tx,s.PRIVATE/"desired-rollback.json",0o400)
    need(digest(json.loads(rollback_desired))==old["plan"]["scope"]["rollback_desired_state_sha256"],
         "ROLLBACK_DESIRED_STATE_PROOF_CHANGED")
    live_desired=read_raw(tx,s.DESIRED,0o600)
    need(digest(live_desired) in (
         old["plan"]["scope"]["desired_state_initial_sha256"],
         old["plan"]["scope"]["rollback_desired_state_sha256"]),
         "UNKNOWN_PRODUCTION_DESIRED_STATE")
    # Original desired_initial and desired_rollback are identical by design.
    # The unchanged live policy must match the initial stage used by the
    # native pre-queue revalidation; no desired-policy rewrite is needed.
    need(digest(live_desired)==old["plan"]["scope"]["desired_state_initial_sha256"],
         "LIVE_DESIRED_NOT_BOUND_INITIAL_STAGE")
    desired=json.loads(live_desired)
    old_slots=(approved_review["bounded_objective_continuation"]["rollback_container_capacity_revalidated"]
               if existing_bounded_claim else None)
    retired=False
    if old_slots and old_slots.get("retirement") and retention.NAME not in retention.inventory(
            I,desired["rollback_container_prefixes"]):
        retention.verified_absence(I,s,candidate,ROOT/candidate,digest(approved_review),
                                   old_slots["retirement"])
        retired=True
    slots=verify_recovery_container_capacity(I,s,eng,old,desired,approved=old_slots,
                                             retirement_verified=retired)
    if slots["retirement"] is not None:
        retention.check_archive_destination(s,candidate,resuming=existing_bounded_claim)
        if not retired:
            need(shutil.disk_usage(s.ARCHIVE).free>source.st_size*3+RESERVE+retention.ARCHIVE_RESERVE,
                 "ARCHIVE_RESERVE_INCLUDES_EXACT_HISTORICAL_EXPORT")
    # Determine exact reviewed replacement before identities without reusing
    # the original stopped backup's immutable container IDs.
    source_hashes={name:digest(payload[name]) for name in s.SOURCES}
    native_hashes={name:digest(payload[name]) for name in s.NATIVE}
    unit_hashes={name:digest(payload["infrastructure/jason-audit-journal/"+name])
                 for name in (*s.UNITS,*I.OVERRIDES)}
    scope=dict(old["plan"]["scope"])
    scope["policy"]={"candidate_sha":candidate,"rollback_sha":OLD_ROLLBACK}
    scope["source_sha256"]=source_hashes
    scope["native_health_sha256"]=native_hashes
    scope["unit_source_sha256"]=unit_hashes
    scope["producer_before"]={
        role:{"id":row["Id"],"image":row["Image"],
              "configuration_sha256":s.digest(eng.exact_original_configuration(row))}
        for role,row in now.items()}
    scope["producer_after_configuration_sha256"]={
        role:s.digest(eng.planned_configuration(row,candidate)) for role,row in now.items()}
    scope["protected_peer_before"]=peers
    scope["source_dataset_identity"]={"device":source.st_dev,"inode":source.st_ino}
    scope["source_schema_sha256"]=I.schema_and_sample(s)
    scope["desired_state_before_sha256"]=digest(live_desired)
    scope["rollback_container_limit_before"]=21
    scope["rollback_container_limit_after"]=27
    scope["rollback_container_reserve"]=6
    scope["rollback_container_capacity_before"]={
        "existing_count":len(slots["after_stopped_names"]),
        "existing_names":slots["after_stopped_names"],
        "limit_before":21,"limit_after":27,"reserved_slots":6,"cleanup_allowed":False}
    scope["existing_rollback_containers_preserved"]=slots["retirement"] is None
    # Only the separately named archived retirement in this new Owner plan is
    # eligible. The installed migration worker gets no general cleanup authority.
    scope["rollback_container_cleanup_allowed"]=False
    scope["installer_sha256"]=digest(payload["tools/audit_journal_install.py"])
    scope["bootstrap_source_sha256"]={name:digest(payload[name]) for name in I.EXTRA}
    scope["bootstrap_resume_record"]=str(ROOT/candidate)
    scope["bootstrap_retry_limit"]=1
    scope.pop("pre_cutover_context_repair",None)
    scope.pop("fresh_owner_recovery",None)
    scope["bounded_objective_continuation"]={
        "schema_version":"1.0",
        "action":ACTION,
        "fresh_licensed_owner_decision_required":True,
        "prior_unrelated_approvals_reused":False,
        "original_failed_scope_sha256":OLD_SCOPE,
        "original_failed_journal_sha256":digest(old["journal"]),
        "original_failed_plan_sha256":digest(old["plan"]),
        "original_trusted_policy_sha256":digest(old["policy"]),
        "prior_exact_recovery_receipts_sha256":prior_hashes,
        "known_safe_source_repairs":changed,
        "rollback_container_capacity_revalidated":slots,
        "historical_rollback_slot_policy_is_provenance_only":True,
        "native_drift_refresh_before_queue":True,
        "native_breaker_only_original_governed_transition":True,
        "reviewed_slot_reservation_source_sha256":
            digest(payload["tools/audit_journal_rollback_slot_reservation.py"]),
        "allowed_steps":list(STEPS),
        "allowed_recovery_branches":list(RECOVERY_BRANCHES),
        "one_owner_decision_for_bounded_objective":True,
        "each_step_independently_pinned_and_one_use":True,
        "unknown_scope_requires_amended_objective":True,
        # Disk usage and journal byte count naturally grow while the Owner
        # authenticates. Bind a deterministic safety FORMULA rather than
        # volatile free-byte values; recompute both sides at each Root gate.
        "archive_capacity_rule":"free_bytes > active_db_bytes * 3 + 4563402752",
        "maximum_live_database_bytes":MAX,
        "archive_capacity_verified_at_every_step":True,
        "journal_timer_only_after_real_verification":True,
        "global_freeze_unchanged":True,
        "native_drift_breaker_not_overridden":True,
        "published_archive_deletion_disallowed":True,
        "production_storage_not_mutated_by_preflight":True,
        "source_commit_sha":candidate,
        "reviewed_objective_installer_sha256":
            digest(payload["tools/audit_journal_install.py"]),
        "reviewed_objective_recovery_sha256":
            digest(payload["tools/audit_journal_objective_recovery.py"]),
        "objective_grant_lifetime_seconds":28800,
        "root_execution_recovery_claims_maximum":2,
        "all_source_drift_revalidated_against_protected_main":True,
    }
    consent=dict(scope)
    consent["action"]=ACTION
    consent["installation_targets"]=[
        str(s.BASE/"trusted"/MATCHER),str(s.POLICY),
        str(s.PROFILE),str(s.CONTROL/"profile.json"),
        *(str(s.PRIVATE/name) for name in (
            "producer-before.json","adoption.json","release-plan.json","release-journal.json")),
        str(ROOT/candidate),
        "systemd://jason-audit-journal-release.service#disable-reset-failed-enable-start",
        *(f"docker://containers/{role}#exact-reviewed-replacement-and-rollback" for role in eng.ROLES),
        str(s.DESIRED),
        "systemd://jason-audit-journal-maintenance.timer#enable-after-cutover",
        str(s.STATE/"production-drift.json")+"#independent-native-evaluator-only",
        str(s.STATE/"production-control-state.json")+"#existing-governed-lkg-revalidation-only",
        "systemd://jason-production-drift-watchdog.service#reset-known-failed-oneshot-only",
        "systemd://jason-openclaw-authority-health.service#verify-current-native-health",
        str(LIVE)+"#approved-journal-and-rollback-only",
        str(s.ARCHIVE/"governed-audit/orchestration"),
    ]
    if slots["retirement"] is not None:
        consent["installation_targets"].extend((
            str(retention.archive_path(s,candidate)),
            "docker://containers/"+slots["retirement"]["id"]+"#archive-and-retire-exact-stopped-container"))
    consent["policy"]={"candidate_sha":candidate,"rollback_sha":OLD_ROLLBACK}
    return consent,{"old":old,"now":now,"peers":peers,
                    "prior_hashes":prior_hashes,"source":(source.st_dev,source.st_ino),
                    "desired_hash":digest(live_desired)}

def root_dir(path):
    m=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(m.st_mode) and
         m.st_uid==m.st_gid==0 and not m.st_mode&0o022,
         "ROOT_OBJECTIVE_LEDGER_CUSTODY")

def prepare_new_claim(s,candidate,review,pre,stamp):
    old=pre["old"]
    objective_sha=digest(review)
    original_scope=dict(review)
    original_scope["action"]=s.ACTION
    original_scope["bounded_objective_grant_sha256"]=objective_sha
    profile=s.public_profile(candidate)
    policy=dict(old["policy"])
    policy.update(candidate_sha=candidate,
                  trusted_source_sha256=original_scope["source_sha256"],
                  profile_sha256=digest(canonical(profile)),
                  public_profile=profile)
    adoption={"action":s.ACTION,"owner_oid":OLD_OWNER,
              "independently_verified_entra_owner":True,"approved_at":stamp,
              "scope_sha256":digest(original_scope),"policy_sha256":digest(canonical(policy)),
              "maintenance_policy_adopted":True,"predecessor_scope_sha256":OLD_SCOPE,
              "bounded_objective_consent_sha256":objective_sha}
    plan={**adoption,"candidate_sha":candidate,"scope":original_scope,
          "claimed_at":stamp,"oldest_producer_started_at":min(
              row["State"]["StartedAt"] for row in pre["now"].values()),
          "producer_before_sha256":digest(pre["now"])}
    journal={"steps":{},"scope_sha256":digest(original_scope),
             "started_at":stamp,
             "bounded_objective_consent_sha256":objective_sha,
             "superseded_interrupted_journal_sha256":digest(old["journal"])}
    # Audit private plan sha must verify exact source hashes, which reflect
    # only the already reviewed OOM Docker normalization.
    need(original_scope["policy"]=={"candidate_sha":candidate,"rollback_sha":OLD_ROLLBACK}
         and adoption["scope_sha256"]==plan["scope_sha256"]==journal["scope_sha256"]
         and plan["producer_before_sha256"]==digest(pre["now"]),
         "NEW_RELEASE_PLAN_NOT_INTERNALLY_CONSISTENT")
    return profile,policy,adoption,plan,journal

def frozen_producer_snapshot(s,eng,review,rows):
    need(isinstance(rows,dict) and set(rows)==set(eng.ROLES),"FROZEN_PRODUCER_ROLE_SET")
    for role,row in rows.items():
        need(review["producer_before"][role]=={
            "id":row["Id"],"image":row["Image"],
            "configuration_sha256":s.digest(eng.exact_original_configuration(row))}
             and review["producer_after_configuration_sha256"][role]==
                 s.digest(eng.planned_configuration(row,review["policy"]["candidate_sha"])),
             "FROZEN_PRODUCER_CONFIGURATION_CHANGED")
    return rows


def bounded_transaction_targets(s):
    """Only exact reviewed Root-file targets may occur in a resumable record."""
    return {
        str(s.BASE/"trusted"/MATCHER):0o444,
        str(s.PROFILE):0o444,
        str(s.CONTROL/"profile.json"):0o444,
        str(s.POLICY):0o600,
        str(s.PRIVATE/"producer-before.json"):0o400,
        str(s.PRIVATE/"adoption.json"):0o400,
        str(s.PRIVATE/"release-plan.json"):0o400,
        str(s.PRIVATE/"release-journal.json"):0o400,
    }


def validate_prequeue_recovery_grant(grant,state,candidate,targets,*,now=None):
    """Read-only exact grant/transaction check; no second human decision."""
    now=now or datetime.now(timezone.utc)
    need(isinstance(grant,dict) and isinstance(state,dict)
         and grant.get("schema_version")=="1.0" and
         grant.get("action")==ACTION and
         grant.get("candidate_sha")==candidate and
         grant.get("source_commit_sha")==candidate and
         grant.get("owner_oid")==OLD_OWNER and
         grant.get("independently_verified_entra_owner") is True and
         grant.get("one_original_owner_decision") is True and
         grant.get("derived_one_use_release_and_rollback_claim") is True and
         grant.get("previous_exact_grants_reused") is False,
         "PREVIOUS_BOUNDED_OWNER_IDENTITY_OR_POLICY")
    review=grant.get("scope")
    need(isinstance(review,dict) and
         review.get("action")==ACTION and
         review.get("policy")=={"candidate_sha":candidate,"rollback_sha":OLD_ROLLBACK}
         and review.get("bounded_objective_continuation",{}).get(
             "one_owner_decision_for_bounded_objective") is True and
         review.get("bounded_objective_continuation",{}).get(
             "allowed_recovery_branches")==list(RECOVERY_BRANCHES) and
         review.get("bounded_objective_continuation",{}).get(
             "root_execution_recovery_claims_maximum")==2 and
         digest(review)==grant.get("scope_sha256")==
         state.get("scope_sha256"),"PREVIOUS_BOUNDED_GRANT_SCOPE_CHANGED")
    issued=datetime.fromisoformat(grant["decided_at"].replace("Z","+00:00"))
    expires=datetime.fromisoformat(grant["expires_at"].replace("Z","+00:00"))
    need(now.tzinfo is not None and issued.tzinfo is not None
         and expires.tzinfo is not None
         and 0<=(now-issued).total_seconds()<=28800
         and expires>now and
         0<(expires-issued).total_seconds()<=28800,
         "BOUNDED_GRANT_EXPIRED_OR_CHANGED")
    # Never resume a queued/delivered transaction: it may have executed.
    need(state.get("outcome") in ("installing","rolling_back","rolled_back")
         and isinstance(state.get("entries"),list),
         "POSSIBLE_QUEUED_RELEASE_NOT_RETRYABLE")
    need(isinstance(targets,dict) and len(targets)==8,
         "EXACT_TARGET_SET_NOT_REVIEWED")
    seen=set()
    for entry in state["entries"]:
        need(isinstance(entry,dict) and entry.get("kind")=="replace"
             and entry.get("path") in targets
             and entry.get("path") not in seen
             and entry.get("mode")==targets[entry["path"]]
             and isinstance(entry.get("before_hex"),str)
             and len(entry["before_hex"])%2==0
             and len(entry["before_hex"])<=32000000
             and isinstance(entry.get("after_sha256"),str)
             and len(entry["after_sha256"])==64,
             "UNREVIEWED_ROOT_TRANSACTION_ENTRY")
        seen.add(entry["path"])
    return review


def install_reviewed_claim(I,s,candidate,payload,review,current,stamp,transaction):
    """Fresh release + exact rollback under the single original Owner grant."""
    profile,policy,adoption,plan,journal=prepare_new_claim(
        s,candidate,review,current,stamp)
    try:
        # Do not leave an automatic boot path pointing at partially updated
        # private records. This disable is included in the same Owner scope.
        I.command(["/usr/bin/systemctl","disable","jason-audit-journal-release.service"])
        slots=review["bounded_objective_continuation"]["rollback_container_capacity_revalidated"]
        retention.apply(I,s,candidate,transaction.path.parent,digest(review),slots)
        need(shutil.disk_usage(s.ARCHIVE).free>LIVE.stat().st_size*3+RESERVE,
             "ARCHIVE_RESERVE_AFTER_EXACT_RETIREMENT")
        transaction.replace(s.BASE/"trusted"/MATCHER,payload[MATCHER],0o444)
        transaction.replace(s.PROFILE,canonical(profile),0o444)
        transaction.replace(s.CONTROL/"profile.json",canonical(profile),0o444)
        transaction.replace(s.POLICY,canonical(policy),0o600)
        transaction.replace(s.PRIVATE/"producer-before.json",
                            canonical(current["now"]),0o400)
        transaction.replace(s.PRIVATE/"adoption.json",canonical(adoption),0o400)
        transaction.replace(s.PRIVATE/"release-plan.json",canonical(plan),0o400)
        transaction.replace(s.PRIVATE/"release-journal.json",canonical(journal),0o400)
        # The native transition worker rejects dirty evidence before it can
        # refresh an aged PASS. Clear only the actual stopped failed service,
        # then obtain a genuine independent native PASS under the existing
        # transaction lock; never write a fabricated PASS or close the breaker.
        release=systemd_show(I,"jason-audit-journal-release.service")
        need(release.get("MainPID")=="0" and release.get("ActiveState") in ("failed","inactive"),
             "RELEASE_NOT_QUIESCED_BEFORE_NATIVE_READMISSION")
        if release["ActiveState"]=="failed":
            I.command(["/usr/bin/systemctl","reset-failed","jason-audit-journal-release.service"])
        watchdog=systemd_show(I,"jason-production-drift-watchdog.service")
        if watchdog.get("ActiveState")=="failed":
            need(watchdog.get("MainPID")=="0","NATIVE_WATCHDOG_STILL_RUNNING")
            I.command(["/usr/bin/systemctl","reset-failed","jason-production-drift-watchdog.service"])
        # Reuse the reviewed, existing pre-cutover admission mechanism. It
        # performs fast health, genuine drift refresh, and the original
        # verified-LKG Root transition; the open breaker is never bypassed.
        from tools.audit_journal_pre_cutover_repair import revalidate_before_queue
        revalidate_before_queue(I,s,review)
        print("BOUNDED_JOURNAL_INDEPENDENT_NATIVE_DRIFT_REFRESH=PASS",flush=True)
        # Durable one-use queue BEFORE any executable systemd activation path.
        transaction.queued=True
        I.command(["/usr/bin/systemctl","enable","jason-audit-journal-release.service"])
        I.command(["/usr/bin/systemctl","--no-block","start","jason-audit-journal-release.service"])
        print("BOUNDED_JOURNAL_OBJECTIVE_RELEASE=QUEUED",flush=True)
        print("BOUNDED_OBJECTIVE_SINGLE_OWNER_DECISION_RECORDED=true",flush=True)
        print("NATIVE_ARCHIVE_AND_DISK_ACCEPTANCE_PENDING=true",flush=True)
    except Exception:
        if not transaction.queued:
            transaction.rollback()
        raise


def execute(I,s,modules,c,auth,candidate,payload):
    need(os.geteuid()==0,"ROOT_ISOLATION_REQUIRED")
    with auth["locks"]():
        review,prior=independent_preflight(I,s,modules,c,candidate,payload)
        # Build every exact new binding before involving the Owner.
        frozen_producer_snapshot(s,modules["audit_journal_container_release"],review,prior["now"])
        prepare_new_claim(s,candidate,review,prior,datetime.now(timezone.utc).isoformat())
        slots=review["bounded_objective_continuation"]["rollback_container_capacity_revalidated"]
        print("NATIVE_ROLLBACK_CONTAINER_COUNT="+str(slots["count"]),flush=True)
        print("NATIVE_ROLLBACK_RESERVED_AFTER="+str(slots["new_release_slots_after"]),flush=True)
        if slots["retirement"] is not None:
            print("EXACT_HISTORICAL_ROLLBACK_TO_ARCHIVE_AND_RETIRE="+slots["retirement"]["name"],flush=True)
        print("BOUNDED_JOURNAL_FULL_OBJECTIVE_PREFLIGHT=PASS",flush=True)
        print("BOUNDED_OBJECTIVE_ACTION="+ACTION,flush=True)
        print("BOUNDED_OBJECTIVE_SCOPE_SHA256="+digest(review),flush=True)
        print("LAST_OWNER_APPROVAL_NOT_REPLAYED=true",flush=True)
        actor=auth["owner"](review)
        need(actor==OLD_OWNER,"INDEPENDENT_LICENSED_OWNER_REQUIRED")
        root_dir(ROOT.parent)
        if not ROOT.exists():
            ROOT.mkdir(mode=0o700);os.chown(ROOT,0,0);ROOT.chmod(0o700)
        root_dir(ROOT)
        folder=ROOT/candidate
        need(not folder.exists(),"OBJECTIVE_ONE_USE_ALREADY_CLAIMED")
        folder.mkdir(mode=0o700);os.chown(folder,0,0);folder.chmod(0o700)
        txlib.sync(ROOT)
        stamp=datetime.now(timezone.utc).isoformat()
        # Preserve the authentic exact decision before any transient second
        # preflight. The same bounded grant can be resumed without another
        # Owner challenge, but never applied to a changed scope.
        frozen=frozen_producer_snapshot(s,modules["audit_journal_container_release"],
                                        review,prior["now"])
        record={
            "schema_version":"1.0","action":ACTION,
            "candidate_sha":candidate,"rollback_sha":OLD_ROLLBACK,
            "scope_sha256":digest(review),"owner_oid":actor,
            "independently_verified_entra_owner":True,
            "one_original_owner_decision":True,
            "derived_one_use_release_and_rollback_claim":True,
            "source_commit_sha":candidate,"decided_at":stamp,
            "expires_at":datetime.fromtimestamp(
                datetime.fromisoformat(stamp).timestamp()+28800,
                timezone.utc).isoformat(),
            "previous_exact_grants_reused":False,
            "producer_before_snapshot_sha256":digest(frozen),
            "scope":review,
        }
        txlib.atomic(folder/"producer-before.json",canonical(frozen),0o400)
        txlib.atomic(folder/"authorization.json",canonical(record),0o400)
        transaction=txlib.InstallTransaction(folder/"transaction.json",digest(review))
        reviewed_again,current=independent_preflight(
            I,s,modules,c,candidate,payload,existing_bounded_claim=True,approved_review=review)
        need(reviewed_again==review and
             prior["source"]==current["source"] and
             prior["prior_hashes"]==current["prior_hashes"] and
             prior["desired_hash"]==current["desired_hash"] and
             {role:item["Id"] for role,item in prior["now"].items()}==
             {role:item["Id"] for role,item in current["now"].items()},
             "HOST_CHANGED_DURING_OWNER_OBJECTIVE_DECISION")
        install_reviewed_claim(I,s,candidate,payload,review,{**current,"now":frozen},stamp,transaction)


def resume_prequeue(I,s,modules,c,auth,candidate,payload):
    """One fail-closed, zero-new-Owner continuation of an *unqueued* exact plan.

    The original authenticated decision is reused as a verified bounded-plan
    grant. An already queued service is never restarted by this continuation,
    because its actual execution outcome is ambiguous without native readback.
    """
    need(os.geteuid()==0,"ROOT_ONLY_RESUME")
    with auth["locks"]():
        child=ROOT/candidate
        root_dir(ROOT.parent)
        root_dir(ROOT)
        root_dir(child)
        tx=modules["audit_journal_install_transaction"]
        grant=read(tx,child/"authorization.json",0o400)
        state=read(tx,child/"transaction.json",0o600)
        approved=validate_prequeue_recovery_grant(
            grant,state,candidate,bounded_transaction_targets(s))
        need(not (child/"revoked.json").exists(),
             "BOUNDED_OWNER_PLAN_REVOKED")
        need(not (child/"prequeue-resume.json").exists(),
             "BOUNDED_PREQUEUE_RESUME_ALREADY_CONSUMED")
        # Privilege, source, policy and native exactness are still gated by the
        # installer. Reverify the current installed policy and original Root
        # protected code before completing any new partial transaction.
        need(digest(payload["tools/audit_journal_objective_recovery.py"])==
             approved["bounded_objective_continuation"]["reviewed_objective_recovery_sha256"]
             and digest(payload["tools/audit_journal_install.py"])==
             approved["bounded_objective_continuation"]["reviewed_objective_installer_sha256"] and
             digest(payload["tools/audit_journal_rollback_slot_reservation.py"])==
             approved["bounded_objective_continuation"]["reviewed_slot_reservation_source_sha256"],
             "REVIEWED_BOUNDED_INSTALLER_SOURCE_CHANGED")
        I.installation_parent_custody(c)
        for name,expected in s.PROTECTED.items():
            need(digest(I.read(Path(name)))==expected,
                 "REVIEWED_PROTECTED_BASELINE_CHANGED")
        release=systemd_show(I,"jason-audit-journal-release.service")
        need(release.get("ActiveState") in ("failed","inactive") and
             release.get("MainPID")=="0","RELEASE_MAY_HAVE_BEEN_QUEUED")
        # Consume bounded prequeue repair before modifying a Root file. This
        # is ONE finite technical branch of the original authenticated grant.
        tx.atomic(child/"prequeue-resume.json",canonical({
            "schema_version":"1.0",
            "original_decision_sha256":digest(grant),
            "scope_sha256":grant["scope_sha256"],
            "candidate_sha":candidate,
            "reviewed_root_transaction_sha256":digest(state),
            "action":"one_prequeue_reconcile_then_resume_exact_plan",
            "at":datetime.now(timezone.utc).isoformat(),
            "one_use":True,"new_owner_prompt":False,
            "no_queued_service_replay":True,
        }),0o400)
        journal_tx=tx.InstallTransaction(child/"transaction.json",
                                         grant["scope_sha256"])
        need(not journal_tx.queued,"QUEUED_RELEASE_NOT_SAFE_TO_RETRY")
        journal_tx.rollback()
        # Host state must now match the old legacy Root plan and the original
        # exact Owner consent after the protected rollback. This check is
        # independent of whether the old attempt was interrupted or undone.
        review,current=independent_preflight(
            I,s,modules,c,candidate,payload,existing_bounded_claim=True,approved_review=approved)
        need(review==approved and
             digest(review)==grant["scope_sha256"],
             "RECOVERED_ROOT_HOST_NO_LONGER_WITHIN_ONE_OWNER_PLAN")
        frozen=read(tx,child/"producer-before.json",0o400)
        need(digest(frozen)==grant.get("producer_before_snapshot_sha256"),
             "FROZEN_PRODUCER_SNAPSHOT_CHANGED")
        frozen_producer_snapshot(s,modules["audit_journal_container_release"],review,frozen)
        # Current live configuration and identities were independently checked
        # above. Reuse exact bytes first bound to the authenticated decision.
        current={**current,"now":frozen}
        stamp=grant["decided_at"]
        install_reviewed_claim(I,s,candidate,payload,review,current,stamp,journal_tx)
        print("BOUNDED_JOURNAL_PREQUEUE_RESUME_NO_NEW_OWNER=PASS",flush=True)


def execute_with_continuation(I,s,modules,c,auth,candidate,payload):
    """At most one approved prequeue reconciliation, never a new Owner prompt.

    If authorization has already been durably recorded, this command either
    safely continues that exact plan or denies. An ambiguous queued release
    is not restarted. A pre-Owner failure is returned unchanged.
    """
    folder=ROOT/candidate
    if os.path.lexists(folder):
        return resume_prequeue(I,s,modules,c,auth,candidate,payload)
    try:
        return execute(I,s,modules,c,auth,candidate,payload)
    except (OSError,TimeoutError,subprocess.SubprocessError,RuntimeError) as error:
        if not (folder/"authorization.json").is_file() or not (folder/"transaction.json").is_file():
            raise
        tx=modules["audit_journal_install_transaction"]
        state=read(tx,folder/"transaction.json",0o600)
        if state.get("outcome") not in ("installing","rolling_back","rolled_back"):
            raise
        # Original execution's host locks have been released. The exact
        # continuation reacquires them, validates the immutable grant and
        # records its one-use claim before any approved mutation.
        print("BOUNDED_PREQUEUE_SAME_OWNER_RECONCILIATION=REQUESTED",flush=True)
        return resume_prequeue(I,s,modules,c,auth,candidate,payload)
