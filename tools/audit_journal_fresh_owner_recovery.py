"""One new authenticated Owner claim for the installed, never-cut-over journal.

This is not a retry of the expired November 23 scope. The expired plan and
journal are preserved immutably in a new Root-owned ledger; the licensed Owner
must authorize a new scope for the exact installed source and fixed unit bytes.
Only then can the existing, unchanged audited release service resume the
ORIGINAL journal objective. A failed/ambiguous queue is never retried blindly.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.audit_journal_install_transaction import InstallTransaction, atomic, raw_file, sync

ACTION = "ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
RECOVERY_ACTION = "FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL"
EXPIRED = "20b32548402d160f9c6a5ee33a0a17592eb9fa68"
EXPIRED_SCOPE = "6d815c67f58ec9fa5eb3e2367259a53d53baf30daaa460d45b4720019291d7e8"
OWNER = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ROLLBACK = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ROOT = Path("/var/lib/jason-owner-release/audit-journal-fresh-owner-recovery")
PRIVATE = Path("/var/lib/jason-audit-journal/private")
CONTROL = Path("/var/lib/jason-audit-journal/control")
BASE = Path("/usr/local/lib/jason/audit-journal")
SYSTEMD = Path("/etc/systemd/system")
ARCHIVE = Path("/srv/jason/archive")
ACTIVE = Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
STATE = Path("/var/lib/jason/openclaw/release-manager")
POLICY = Path("/etc/jason-owner-release/audit-journal-v1.json")
UNITS = ("jason-audit-journal-release.service",
         "jason-audit-journal-maintenance.service",
         "jason-audit-journal-data-recovery.service")
UNIT_AFTER_SHA = {
    "jason-audit-journal-release.service":
      "a272140be65859aaacb0fa3c569e8b77b77f4f06d1a0fbff15680420f93cbd1e",
    "jason-audit-journal-maintenance.service":
      "39c43f2f2ba606a80faa74d208319c1a4b60f45578defe68d96b296d9e2532ca",
    "jason-audit-journal-data-recovery.service":
      "5b0ab92c1234ef5d710526ebabda4b9b0256197bfca7dc8e3ec49a122abe372e",
}
UNIT_BEFORE_SHA = {
    "jason-audit-journal-release.service":
      "a0eb4c22128983dfdd347c4df7c7bb539320cc5ebc407c28b1b197a9dcd3518a",
    "jason-audit-journal-maintenance.service":
      "13836ef94614073b9c5631dfa24c637c28bd434808e5c5c404d6a51943922ecc",
    "jason-audit-journal-data-recovery.service":
      "1c06f7a14cc21c0f74d136b5a238a2bbb4b610a6669c34dbf9a813d880c0f530",
}
PROTECTED_PRIVATE = ("release-plan.json", "release-journal.json",
                     "adoption.json", "producer-before.json",
                     "desired-rollback.json", "desired-final.json",
                     "protected-ci-before.json")
SNAPSHOT_SOURCE = Path("/srv/jason/archive/engineering-artifacts/journal-retention-30day-20261123/old-stage-cleanup-result-20261124.json")
EXPECTED_DEV = 66306
EXPECTED_INODE = 10261846
EXPECTED_PRIOR_SHA = {
    "plan":"f88b423c8cf7922201e9b5020cd99a21f4df6ed36f5491b5d7f5fbb383a3c24e",
    "journal":"45b1d0154583c8f40c4d4b8b9755ac98a02ad481cde1b1c9c1543eea3ffaabbc",
    "adoption":"2cbf005b417a42fef41d6623849a598dfecfbc4822bc6105b2d9bec63722410",
    "catalog":"42de60cb250626f938228baf51b5e063f27a9e03cb257c4072deb467616a572",
    "policy":"18ea2f52d7c72146c128dcdc9cdb1360cd35376e57c11fc663f19edd971e5dd4",
}
PREVIOUS_ATTEMPTS = {
    "4ba98e05e4512d7accb77595b8e8c05086d8b0a6": {
        "scope":"301b077f04c7dfd2757da47949aede12b18f34ca82c692d6b8173f769875261f",
        "transaction":"b186c5afbe0f155ea8cf2834c4d55cbd9994c719a4cab3dccd968c28c2a0b549",
    },
    "b9274191a79bda16bb687a866b4458bda6bf6361": {
        "scope":"7dc2fc5b4a67ae9e8a896934525ce65be4815ad9184612a161d3e50b54fe9f94",
        "transaction":"365d48b358526e0cb05c0e0f26d215fc9de432e703c9eed2675bfee879bd4e06",
        "retry":"7b5db1ad2b879c2f373e4b01bdb40086da733a97b3a413f0a7367ec75da7dd00",
    },
    EXPIRED: {
        "scope":EXPIRED_SCOPE,
        "transaction":"5f10d907af5ba7b6955b507889e63ab1a72075c9bb05ec4a213a03008e039aed",
    },
}
MAX_DATA = 68719476736
RESERVE = 4563402752


def need(value, code):
    if not value:
        raise PermissionError("JOURNAL_FRESH_OWNER_RECOVERY_" + code)


def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def digest(obj):
    return sha256(obj if isinstance(obj, bytes) else canon(obj)).hexdigest()


def root_record(path, mode, maximum=16_000_000):
    return raw_file(path,mode)


def exact_unit_pair(new):
    """Return the exact reviewed new and installed before-image unit bytes."""
    need(isinstance(new,bytes) and new.count(b"AmbientCapabilities=CAP_SETUID\n")==1,
         "AMBIENT_ONLY_EXACT_SOURCE")
    before = new.replace(b"AmbientCapabilities=CAP_SETUID\n",b"")
    need(b"NoNewPrivileges=true\n" in before
         and b"CapabilityBoundingSet=" in before
         and b"CAP_SETUID CAP_SETGID" in before
         and b"RestrictAddressFamilies=AF_UNIX AF_NETLINK\n" in before,
         "HARDENING_BASELINE_MISSING")
    return before,new


def systemd_properties(unit):
    proc = subprocess.run(
        ["/usr/bin/systemctl","show",unit,
         "--property=ActiveState,SubState,MainPID,UnitFileState,Result,AmbientCapabilities"],
         capture_output=True,text=True,check=False,timeout=20)
    need(proc.returncode==0,"SYSTEMD_STATE_UNAVAILABLE")
    return dict(line.split("=",1) for line in proc.stdout.splitlines() if "=" in line)


def preflight(candidate,source_units,*,get_plan=None,get_journal=None,
              get_adoption=None,get_catalog=None,get_policy=None,
              read_fn=root_record,stat_fn=None,unit_fn=systemd_properties,
              check_live=True):
    """Produce a deterministic exact scope without changing any host artifact.

    Fixture arguments exist solely for offline tests; the Root installer uses
    the pinned production defaults and never accepts caller-supplied paths.
    """
    need(os.geteuid()==0 or not check_live,"ROOT_REQUIRED")
    need(len(candidate)==40 and all(v in "0123456789abcdef" for v in candidate),
         "REVIEWED_SOURCE_SHA")
    if check_live:
        need(Path("/proc/self/ns/mnt").stat().st_ino == Path("/proc/1/ns/mnt").stat().st_ino,
             "HOST_MOUNT_NAMESPACE")
        need(Path("/opt/jason/current").resolve().name==ROLLBACK,
             "UNRELATED_LIVE_RELEASE")
        need(not ROOT.joinpath(candidate).exists(),"ONE_USE_CANDIDATE_ALREADY_CLAIMED")
    plan = get_plan if get_plan is not None else json.loads(read_fn(PRIVATE/"release-plan.json",0o400))
    journal = get_journal if get_journal is not None else json.loads(read_fn(PRIVATE/"release-journal.json",0o400))
    adoption = get_adoption if get_adoption is not None else json.loads(read_fn(PRIVATE/"adoption.json",0o400))
    catalog = get_catalog if get_catalog is not None else json.loads(read_fn(CONTROL/"catalog.json",0o444))
    policy = get_policy if get_policy is not None else json.loads(read_fn(POLICY,0o600))
    need(isinstance(plan,dict) and isinstance(journal,dict) and
         isinstance(adoption,dict) and isinstance(catalog,dict) and isinstance(policy,dict),
         "OLD_ROOT_RECORD_SCHEMA")
    if check_live:
        prior_paths={
            "plan":(PRIVATE/"release-plan.json",0o400),
            "journal":(PRIVATE/"release-journal.json",0o400),
            "adoption":(PRIVATE/"adoption.json",0o400),
            "catalog":(CONTROL/"catalog.json",0o444),
            "policy":(POLICY,0o600),
        }
        for label,(path,mode) in prior_paths.items():
            # Source hashes are of exact Root-owned original bytes, NOT
            # reserialized JSON (which could silently alter the evidence).
            need(digest(read_fn(path,mode))==EXPECTED_PRIOR_SHA[label],
                 "PREVIOUS_PROTECTED_"+label.upper()+"_HASH_CHANGED")
    need(plan.get("candidate_sha")==EXPIRED and
         plan.get("scope_sha256")==EXPIRED_SCOPE and
         plan.get("action")==ACTION and
         plan.get("owner_oid")==OWNER and
         plan.get("independently_verified_entra_owner") is True and
         plan.get("scope",{}).get("policy")=={
             "candidate_sha":EXPIRED,"rollback_sha":ROLLBACK
         } and digest(plan["scope"])==EXPIRED_SCOPE,
         "EXACT_PREVIOUS_OWNER_CLAIM")
    need(policy.get("candidate_sha")==EXPIRED and
         policy.get("enabled") is True and
         policy.get("trusted_source_sha256")==plan["scope"]["source_sha256"] and
         policy.get("public_profile",{}).get("component_source_sha")==EXPIRED,
         "INSTALLED_EXPIRED_SOURCE_POLICY")
    need(adoption.get("scope_sha256")==EXPIRED_SCOPE and
         adoption.get("owner_oid")==OWNER and
         adoption.get("independently_verified_entra_owner") is True,
         "EXPIRED_OWNER_ADOPTION")
    need(journal.get("scope_sha256")==EXPIRED_SCOPE and journal.get("steps")=={} and
         "outcome" not in journal and
         isinstance(journal.get("recovery_started_at"),str) and
         isinstance(journal.get("started_at"),str),
         "NOT_AN_UNCONSUMED_FAILED_PRECUTOVER_JOURNAL")
    claimed=datetime.fromisoformat(journal["started_at"].replace("Z","+00:00"))
    recovering=datetime.fromisoformat(journal["recovery_started_at"].replace("Z","+00:00"))
    now=datetime.now(timezone.utc)
    need(claimed.tzinfo is not None and recovering.tzinfo is not None
         and recovering>=claimed and (now-claimed).total_seconds()>28800
         and (now-recovering).total_seconds()>28800,
         "PRIOR_CLAIM_NOT_EXPIRED")
    need(catalog.get("mode")=="legacy" and catalog.get("generation")==0
         and catalog.get("epoch") is None and catalog.get("segments")==[],
         "MIGRATION_CUTOVER_OR_ARCHIVE_PRESENT")
    state = unit_fn(UNITS[0])
    need(state.get("ActiveState")=="failed" and state.get("MainPID")=="0" and
         state.get("AmbientCapabilities","")=="" and
         state.get("UnitFileState")=="enabled",
         "FAILED_RELEASE_NOT_QUIESCED")
    before_units={}
    after_units={}
    for name in UNITS:
        need(name in source_units,"REVIEWED_UNIT_MISSING")
        expected,reviewed=exact_unit_pair(source_units[name])
        actual=read_fn(SYSTEMD/name,0o644)
        need(digest(reviewed)==UNIT_AFTER_SHA[name] and
             digest(expected)==UNIT_BEFORE_SHA[name] and
             actual==expected,"LIVE_UNIT_DIFFERS_FROM_EXACT_CAPSETUID_FIX")
        before_units[name]=digest(actual)
        after_units[name]=digest(reviewed)
    if check_live:
        for name in ("initial-cutover-claimed.json","initial-cutover-complete.json",
                     "recovery-recipe.json","rollback-mounted.json"):
            need(not (PRIVATE/name).exists(),"CUTOVER_MARKER_OR_RECIPE_PRESENT")
        for folder in (CONTROL.parent/"pending",ARCHIVE/"governed-audit/orchestration",
                       ARCHIVE/"governed-audit/rollback"):
            need(folder.is_dir() and not any(folder.iterdir()),
                 "EXISTING_SEGMENTED_WORK_OR_ARCHIVE")
        s=ACTIVE.lstat()
        need(not ACTIVE.is_symlink() and stat.S_ISREG(s.st_mode) and
             s.st_uid==s.st_gid==1000 and s.st_nlink==1
             and stat.S_IMODE(s.st_mode)==0o600
             and (s.st_dev,s.st_ino)==(EXPECTED_DEV,EXPECTED_INODE)
             and 0<s.st_size<=MAX_DATA,
             "PRODUCTION_DATASET_IDENTITY_CHANGED")
        need(plan["scope"]["source_dataset_identity"]=={
                "device":s.st_dev,"inode":s.st_ino
             },"PREVIOUS_DATASET_BINDING_CHANGED")
        need(os.path.ismount(ARCHIVE) and ARCHIVE.stat().st_dev!=s.st_dev,
             "SEPARATE_ARCHIVE_MOUNT_REQUIRED")
        v=os.statvfs(ARCHIVE)
        need(v.f_bavail*v.f_frsize>s.st_size*3+RESERVE,
             "ARCHIVE_COLD_RESTORE_ROLLBACK_RESERVE")
        cleanup=json.loads(SNAPSHOT_SOURCE.read_text())
        need(cleanup["deleted_old_stage"] and cleanup["migration_capacity_check"]
             and cleanup["production_cutover_performed"] is False,
             "ARCHIVE_CAPACITY_CLEANUP_EVIDENCE")
        for name,sha in policy["trusted_source_sha256"].items():
            need(digest(read_fn(BASE/"trusted"/name,0o444))==sha,
                 "INSTALLED_REVIEWED_CODE_CHANGED")
        previous=Path("/var/lib/jason-owner-release/audit-journal-service-context-repairs")
        previous_proofs={}
        for old_candidate,record in PREVIOUS_ATTEMPTS.items():
            root=previous/old_candidate
            auth_raw=read_fn(root/"authorization.json",0o400)
            auth=json.loads(auth_raw)
            # Never publish private authorization-receipt fingerprints in
            # Git. Root derives the exact hash into the NEW authenticated
            # consent scope, and rechecks it before transaction execution.
            need(auth.get("candidate_sha")==old_candidate and
                 auth.get("scope_sha256")==record["scope"] and
                 auth.get("owner_oid")==OWNER and
                 auth.get("independently_verified_entra_owner") is True and
                 auth.get("scope",{}).get("action")==ACTION and
                 auth.get("scope",{}).get("policy")=={
                    "candidate_sha":old_candidate,"rollback_sha":ROLLBACK
                 } and digest(auth["scope"])==record["scope"],
                 "PREVIOUS_INDEPENDENT_OWNER_AUTHORIZATION_CHANGED")
            proofs={"authorization":digest(auth_raw)}
            for label in ("transaction","retry"):
                if label not in record:
                    need(not (root/(label+".json")).exists(),"UNEXPECTED_OLD_RETRY")
                    continue
                raw=read_fn(root/(label+".json"),0o600 if label=="transaction" else 0o400)
                need(digest(raw)==record[label],"PREVIOUS_"+label.upper()+"_CHANGED")
                row=json.loads(raw)
                need(row.get("scope_sha256")==record["scope"],
                     "PREVIOUS_"+label.upper()+"_SCOPE_CHANGED")
                if label=="transaction":
                    need(row.get("outcome")==("queued" if old_candidate==EXPIRED else "rolled_back"),
                         "OLD_TRANSACTION_STATE_CHANGED")
                proofs[label]=digest(raw)
            previous_proofs[old_candidate]=proofs
        need(not (PRIVATE/"initial-cutover-claimed.json").exists(),
             "RECORDED_INITIAL_CUTOVER")
    # Extra authorization fields belong to the NEW scope and never overwrite
    # the previous plan's captured immutable source and producer identities.
    current_scope=dict(plan["scope"])
    current_scope["fresh_owner_recovery"]={
        "schema_version":"1.0",
        "action":RECOVERY_ACTION,
        "reviewed_recovery_source_sha":candidate,
        "previous_candidate_sha":EXPIRED,
        "previous_scope_sha256":EXPIRED_SCOPE,
        "previous_attempt_root_fingerprints_sha256":
            previous_proofs if check_live else None,
        "previous_claim_sha256":digest(plan),
        "previous_journal_sha256":digest(journal),
        "previous_adoption_sha256":digest(adoption),
        "installed_policy_sha256":digest(policy),
        "legacy_catalog_sha256":digest(catalog),
        "service_units_before_sha256":before_units,
        "service_units_after_sha256":after_units,
        "old_execution_authority_reused":False,
        "fresh_authenticated_licensed_owner_required":True,
        "initial_cutover_not_performed":True,
        "source_root_policy_preserved":True,
        "production_freeze_unchanged":True,
        "retired_release_replayed":False,
        "owner_scope_hash_only":True,
        "recovery_installation_targets":[
            *(str(SYSTEMD/n) for n in UNITS),
            *(str(PRIVATE/n) for n in
                ("adoption.json","release-plan.json","release-journal.json")),
            str(ROOT/candidate),
        ],
    }
    return current_scope,{"plan":plan,"journal":journal,"adoption":adoption,
                          "catalog":catalog,"policy":policy,
                          "before_units_sha256":before_units}


def exact_consent_scope(scope,candidate):
    """Prompt for the *new recovery*, not the historical migration approval."""
    need(scope.get("fresh_owner_recovery",{}).get("reviewed_recovery_source_sha")==candidate,
         "REVIEWED_RECOVERY_SOURCE_BINDING")
    consent=dict(scope)
    consent["action"]=RECOVERY_ACTION
    consent["policy"]={"candidate_sha":candidate,"rollback_sha":ROLLBACK}
    consent["fresh_owner_recovery_install_scope_sha256"]=digest(scope)
    consent["installation_targets"]=scope["fresh_owner_recovery"]["recovery_installation_targets"]
    return consent


def install(I,s,candidate,source_units,new_scope,prior,actor,consent_scope):
    """Persist a new complete Root-owned claim before re-enabling the service."""
    need(os.geteuid()==0 and actor==OWNER,"FRESH_OWNER_REQUIRED")
    need(new_scope.get("fresh_owner_recovery",{}).get("old_execution_authority_reused") is False,
         "EXPIRED_GRANT_CANNOT_BE_REUSED")
    need(consent_scope==exact_consent_scope(new_scope,candidate) and
         consent_scope["action"]==RECOVERY_ACTION and
         consent_scope["policy"]["candidate_sha"]==candidate,
         "EXACT_NEW_OWNER_CONSENT_SCOPE_REQUIRED")
    base=ROOT.parent
    base_info=base.lstat()
    need(not base.is_symlink() and stat.S_ISDIR(base_info.st_mode)
         and base_info.st_uid==base_info.st_gid==0
         and not (base_info.st_mode & 0o022),
         "EXISTING_ROOT_GOVERNANCE_PARENT_CUSTODY")
    parent=ROOT
    if not parent.exists():
        parent.mkdir(mode=0o700)
        os.chown(parent,0,0);parent.chmod(0o700);sync(parent.parent)
    parent_info=parent.lstat()
    need(not parent.is_symlink() and stat.S_ISDIR(parent_info.st_mode)
         and parent_info.st_uid==parent_info.st_gid==0
         and stat.S_IMODE(parent_info.st_mode)==0o700,
         "NEW_ROOT_LEDGER_PARENT_CUSTODY")
    root=ROOT/candidate
    need(not root.exists(),"NEW_OWNER_APPROVAL_ALREADY_CONSUMED")
    root.mkdir(mode=0o700);os.chown(root,0,0);root.chmod(0o700);sync(root.parent)
    stamp=datetime.now(timezone.utc).isoformat()
    scope_sha=digest(new_scope)
    evidence={
        "schema_version":"1.0","action":RECOVERY_ACTION,
        "candidate_sha":candidate,"installed_candidate_sha":EXPIRED,
        "rollback_sha":ROLLBACK,"scope_sha256":scope_sha,
        "owner_oid":actor,"independently_verified_entra_owner":True,
        "verified_at":stamp,"one_use":True,"old_approval_reused":False,
        "new_execution_claim":True,
        "owner_consent_scope_sha256":digest(consent_scope),
    }
    atomic(root/"authorization.json",canon(evidence),0o400)
    for label,content in prior.items():
        if label in ("plan","journal","adoption","catalog","policy"):
            atomic(root/("before-"+label+".json"),canon(content),0o400)
    tx=InstallTransaction(root/"transaction.json",scope_sha)
    # Each fixed target has an exact SHA-checked before image from the
    # previous claim and a reviewed protected-Main after image.
    previous_plan=prior["plan"]
    adoption={**prior["adoption"],"approved_at":stamp,
              "scope_sha256":scope_sha,
              "fresh_recovery_authorization_sha256":digest(evidence)}
    plan={**previous_plan,"scope":new_scope,"scope_sha256":scope_sha,
          "approved_at":stamp,"claimed_at":stamp,
          "fresh_recovery_authorization_sha256":digest(evidence)}
    journal={"steps":{},"scope_sha256":scope_sha,"started_at":stamp,
             "fresh_owner_recovery_authorization_sha256":digest(evidence),
             "supersedes_expired_journal_sha256":digest(prior["journal"])}
    try:
        for name in UNITS:
            old,new=exact_unit_pair(source_units[name])
            need(digest(new)==UNIT_AFTER_SHA[name] and
                 digest(old)==UNIT_BEFORE_SHA[name] and
                 digest(old)==prior["before_units_sha256"][name],
                 "INSTALL_UNIT_BEFORE_IMAGE_CHANGED")
            tx.replace(SYSTEMD/name,new,0o644)
        # A private Root journal, not a reset of the old executed authority.
        for name,new in (("adoption.json",adoption),
                         ("release-plan.json",plan),
                         ("release-journal.json",journal)):
            tx.replace(PRIVATE/name,canon(new),0o400)
        I.command(["/usr/bin/systemctl","daemon-reload"],timeout=40)
        observed=systemd_properties(UNITS[0])
        need(observed.get("AmbientCapabilities") not in ("",None)
             and observed.get("ActiveState")=="failed"
             and observed.get("MainPID")=="0",
             "CORRECTED_SERVICE_UNIT_NOT_EFFECTIVE")
        # The one-use execution is irrevocably recorded before any boot path.
        tx.queued=True
        I.command(["/usr/bin/systemctl","reset-failed",UNITS[0]],timeout=30)
        I.command(["/usr/bin/systemctl","enable",UNITS[0]],timeout=30)
        I.command(["/usr/bin/systemctl","--no-block","start",UNITS[0]],timeout=30)
        print("JOURNAL_FRESH_OWNER_EXACT_RELEASE=QUEUED",flush=True)
        print("NEW_SCOPE_SHA256="+scope_sha,flush=True)
        print("ORIGINAL_EXPIRED_APPROVAL_UNCHANGED=true",flush=True)
        print("PRODUCTION_ACCEPTANCE_NOT_YET_VERIFIED=true",flush=True)
    except Exception:
        if not tx.queued:
            tx.rollback()
            I.command(["/usr/bin/systemctl","daemon-reload"],timeout=40)
        raise


def governed_readmission(I,s,modules,c,prior):
    """Revalidate source/peers and the *actual* protected open-breaker posture.

    A fresh exact Owner scope is a necessary gate but cannot override a drift
    anomaly, a changed producer, another executing release, or Root code drift.
    """
    need(os.geteuid()==0,"ROOT_REQUIRED")
    I.installation_parent_custody(c)
    protected={}
    for name,expected in s.PROTECTED.items():
        raw=I.read(Path(name))
        need(digest(raw)==expected,"PROTECTED_ROOT_BASELINE_CHANGED")
        protected[name]=expected
    peers=s.protected_peer_inventory()
    old=prior["plan"]["scope"]
    need(peers==old["protected_peer_before"],"PROTECTED_PEER_CHANGED")
    before=json.loads(root_record(PRIVATE/"producer-before.json",0o400))
    need(digest(before)==prior["plan"]["producer_before_sha256"],
         "PRODUCER_BEFORE_IMAGE_CHANGED")
    engine=modules["audit_journal_container_release"]
    need(set(before)==set(engine.ROLES),"PRODUCER_ROLE_SET_CHANGED")
    consumers={}
    client=engine.DockerEngine()
    for role in engine.ROLES:
        observed=client.inspect(role)
        original=before[role]
        need(observed["Id"]==original["Id"] and
             observed["Image"]==original["Image"] and
             observed["State"]["Running"] is True and
             digest(engine.exact_original_configuration(observed))==
             digest(engine.exact_original_configuration(original)),
             "PRODUCER_IMAGE_OR_CONFIG_CHANGED")
        consumers[role]={"id":observed["Id"],"image":observed["Image"]}
    # Read-only inventory has the same constraints as the original installer.
    inventory=modules["audit_journal_root_inventory"].handles(ACTIVE)
    need(inventory["complete"],"INCOMPLETE_LIVE_DB_HANDLE_INVENTORY")
    for row in inventory["open_handles"]:
        cgroup=(Path("/proc")/str(row["pid"])/"cgroup").read_text()
        need(row["uid"]==1000 and any(value["Id"] in cgroup for value in before.values()),
             "UNKNOWN_LIVE_DATABASE_HANDLE")
    status=systemd_properties("jason-audit-journal-maintenance.timer")
    need(status.get("ActiveState")=="inactive" and
         status.get("UnitFileState")=="disabled","OLD_TIMER_UNEXPECTEDLY_RUNNING")
    ctrl=json.loads(root_record(STATE/"production-control-state.json",0o600))
    drift=json.loads(root_record(STATE/"production-drift.json",0o600))
    breaker=ctrl.get("circuit_breaker",{})
    need(breaker.get("state")=="open" and
         breaker.get("reason")=="continuous_production_drift_detected",
         "UNEXPECTED_PRODUCTION_BREAKER")
    allowed={
        ("failed_system_unit","jason-audit-journal-release.service","failed"),
        ("failed_system_unit","jason-production-drift-watchdog.service","failed"),
        ("required_system_unit_not_active","jason-audit-journal-maintenance.timer","inactive"),
    }
    observed={(x.get("kind"),x.get("unit"),x.get("state"))
              for x in drift.get("problems",[]) if isinstance(x,dict)}
    need(drift.get("status")=="drift_detected" and
         ("failed_system_unit","jason-audit-journal-release.service","failed") in observed
         and observed <= allowed,
         "UNRELATED_PRODUCTION_DRIFT")
    timestamp=datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))
    age=(datetime.now(timezone.utc)-timestamp).total_seconds()
    need(timestamp.tzinfo is not None and -10<=age<=300,
         "NATIVE_DRIFT_EVIDENCE_STALE")
    return {"protected_sha256":protected,"producer_identities":consumers,
            "protected_peers":peers,"expected_open_breaker":True,
            "known_drift_kinds":sorted([list(x) for x in observed])}


def execute(I,s,modules,c,auth,candidate,payload):
    need(os.geteuid()==0,"ROOT_ONLY")
    with auth["locks"]():
        units={name:payload["infrastructure/jason-audit-journal/"+name] for name in UNITS}
        scope,prior=preflight(candidate,units)
        protected_evidence=governed_readmission(I,s,modules,c,prior)
        print("JOURNAL_FRESH_OWNER_ROLLFORWARD_PREFLIGHT=PASS",flush=True)
        print("FRESH_NATIVE_SAFETY_READMISSION=PASS",flush=True)
        print("EXPIRED_SCOPE_SHA256="+EXPIRED_SCOPE,flush=True)
        print("NEW_REVIEWED_SCOPE_SHA256="+digest(scope),flush=True)
        print("PRIOR_RELEASE_WILL_NOT_BE_REPLAYED=true",flush=True)
        consent_scope=exact_consent_scope(scope,candidate)
        print("NEW_EXACT_OWNER_ACTION="+RECOVERY_ACTION,flush=True)
        print("REVIEWED_RECOVERY_SOURCE_SHA="+candidate,flush=True)
        print("OWNER_CONSENT_SCOPE_SHA256="+digest(consent_scope),flush=True)
        actor=auth["owner"](consent_scope)
        need(actor==OWNER,"LICENSED_OWNER_IDENTITY_REQUIRED")
        new_scope,new_prior=preflight(candidate,units)
        after_evidence=governed_readmission(I,s,modules,c,new_prior)
        need(scope==new_scope and prior==new_prior and
             protected_evidence==after_evidence,
             "HOST_CHANGED_DURING_EXACT_OWNER_APPROVAL")
        install(I,s,candidate,units,scope,prior,actor,consent_scope)
