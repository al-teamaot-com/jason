"""No-Root synthetic tests for one bounded Owner plan and exact journal recovery."""
import copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import audit_journal_objective_recovery as r
from tools import audit_journal_release_scope as s
from tools import audit_journal_container_release as eng
from tools.tests.test_audit_journal_release_plan import before as fixture_before

CANDIDATE="a"*40

def synthetic():
    original={role:fixture_before(role) for role in eng.ROLES}
    for idx,(role,v) in enumerate(original.items()):
        v["Id"]=str(idx+1)*64
        v["State"]={"Running":True,"StartedAt":"2026-11-24T08:00:00Z"}
    current=copy.deepcopy(original)
    current["jason-pmv4-ticket-core"]["Id"]=r.CORE_ID
    current["jason-pmv4-ticket-core"]["State"]["StartedAt"]="2026-11-24T08:02:00Z"
    for role in current:
        current[role]["Image"]=original[role]["Image"]
    old_scope={
        "schema_version":"1.0","action":s.ACTION,
        "policy":{"candidate_sha":r.OLD,"rollback_sha":r.OLD_ROLLBACK},
        "source_sha256":{name:"0"*64 for name in s.SOURCES},
        "native_health_sha256":{name:"0"*64 for name in s.NATIVE},
        "unit_source_sha256":{name:"0"*64 for name in (*s.UNITS, "93-jason-audit-data-recovery.conf")},
        "producer_before":{
            role:{"id":row["Id"],"image":row["Image"],
                  "configuration_sha256":s.digest(eng.exact_original_configuration(row))}
            for role,row in original.items()},
        "producer_after_configuration_sha256":{
            role:s.digest(eng.planned_configuration(row,r.OLD)) for role,row in original.items()},
        "protected_peer_before":{"jason-runtime":{"id":original["jason-runtime"]["Id"]}},
        "source_dataset_identity":{"device":66306,"inode":10261846},
        "desired_state_after_sha256":"8"*64,
        "desired_state_initial_sha256":"7"*64,
        "rollback_desired_state_sha256":"6"*64,
    }
    plan={"action":s.ACTION,"candidate_sha":r.OLD,
          "scope_sha256":r.digest(old_scope),"scope":old_scope,
          "owner_oid":r.OLD_OWNER,"independently_verified_entra_owner":True,
          "approved_at":"2026-11-24T07:00:00+00:00",
          "producer_before_sha256":r.digest(original)}
    journal={"scope_sha256":r.digest(old_scope),"steps":{
        "install:jason-pmv4-ticket-core":{"before_id":original["jason-pmv4-ticket-core"]["Id"]},
        "restore:jason-pmv4-ticket-core":{"before_id":"5"*64},
    },"started_at":"2026-11-24T07:00:00+00:00",
       "recovery_started_at":"2026-11-24T07:01:00+00:00"}
    data={
        "plan":plan,"journal":journal,"adoption":{
            "scope_sha256":r.digest(old_scope),"owner_oid":r.OLD_OWNER,
            "independently_verified_entra_owner":True,"action":s.ACTION,
            "maintenance_policy_adopted":True},
        "policy":{
            "candidate_sha":r.OLD,"trusted_source_sha256":old_scope["source_sha256"],
            "public_profile":s.public_profile(r.OLD),
            "enabled":True},
        "catalog":{"schema_version":"1.0","mode":"legacy","generation":0,
                   "epoch":None,"segments":[]},
        "previous":original,
    }
    mocked_review=copy.deepcopy(old_scope)
    mocked_review["action"]=r.ACTION
    mocked_review["installation_targets"]=["/exact/Root"]
    mocked_review["policy"]={"candidate_sha":CANDIDATE,"rollback_sha":r.OLD_ROLLBACK}
    mocked_review["source_sha256"]={name:"1"*64 for name in s.SOURCES}
    mocked_review["native_health_sha256"]={name:"2"*64 for name in s.NATIVE}
    mocked_review["unit_source_sha256"]={name:"3"*64 for name in (*s.UNITS,"93-jason-audit-data-recovery.conf")}
    mocked_review["producer_before"]={role:{
        "id":row["Id"],"image":row["Image"],
        "configuration_sha256":s.digest(eng.exact_original_configuration(row))}
        for role,row in current.items()}
    mocked_review["producer_after_configuration_sha256"]={
        role:s.digest(eng.planned_configuration(row,CANDIDATE)) for role,row in current.items()}
    mocked_review["bounded_objective_continuation"]={
        "action":r.ACTION,"allowed_steps":list(r.STEPS),
        "allowed_recovery_branches":list(r.RECOVERY_BRANCHES)}
    return data,current,mocked_review

def test_fixed_approval_plan_covers_migration_recovery_verification_not_provider_mutations():
    assert len(r.STEPS)==6 and len(r.RECOVERY_BRANCHES)==5
    assert len(set(r.STEPS))==len(r.STEPS)
    assert all(v in r.STEPS for v in
               ("reconcile_exact_interrupted_legacy_release",
                "verify_sealed_history_and_cold_restore",
                "reclaim_legacy_root_storage_after_independent_acceptance"))
    assert "arbitrary_shell" not in r.STEPS
    assert r.ACTION!="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"


def test_new_plan_uses_current_restored_producer_ids_not_consumed_before_images():
    old,current,review=synthetic()
    pre={"old":old,"now":current}
    profile,policy,adoption,plan,journal=r.prepare_new_claim(s,CANDIDATE,review,pre,
                                                              "2026-11-24T13:00:00+00:00")
    scope=plan["scope"]
    assert plan["candidate_sha"]==CANDIDATE
    assert profile["component_source_sha"]==CANDIDATE
    assert policy["trusted_source_sha256"]==review["source_sha256"]
    assert policy["candidate_sha"]==CANDIDATE
    assert adoption["scope_sha256"]==plan["scope_sha256"]==journal["scope_sha256"]
    assert adoption["policy_sha256"]==r.digest(r.canonical(policy))
    assert scope["producer_before"]["jason-pmv4-ticket-core"]["id"]==r.CORE_ID
    assert scope["producer_before"]["jason-pmv4-ticket-core"]["id"]!=(
        old["plan"]["scope"]["producer_before"]["jason-pmv4-ticket-core"]["id"])
    assert plan["producer_before_sha256"]==r.digest(current)
    assert journal["steps"]=={} and "recovery_started_at" not in journal
    assert journal["superseded_interrupted_journal_sha256"]==r.digest(old["journal"])
    assert old["journal"]["steps"]
    assert old["policy"]["candidate_sha"]==r.OLD
    assert scope["bounded_objective_grant_sha256"]==r.digest(review)
    assert scope["policy"]["rollback_sha"]==r.OLD_ROLLBACK
    assert plan["bounded_objective_consent_sha256"]==r.digest(review)


def test_original_scope_synthetic_meets_exact_original_custody(monkeypatch):
    old,current,review=synthetic()
    monkeypatch.setattr(r,"OLD_SCOPE",r.digest(old["plan"]["scope"]))
    def read(path,mode):
        key={
            s.POLICY:"policy",
            s.PRIVATE/"adoption.json":"adoption",
            s.PRIVATE/"release-plan.json":"plan",
            s.PRIVATE/"release-journal.json":"journal",
            s.PRIVATE/"producer-before.json":"previous",
            s.CONTROL/"catalog.json":"catalog",
        }[Path(path)]
        return r.canonical(old[key])
    tx=SimpleNamespace(raw_file=read)
    class I:
        @staticmethod
        def command(argv):
            name=argv[2]
            if name=="jason-audit-journal-release.service":
                return "ActiveState=failed\nMainPID=0\nResult=exit-code\nUnitFileState=enabled"
            return "ActiveState=inactive\nMainPID=0\nResult=success\nUnitFileState=disabled"
    result=r.existing_release(s,I,tx)
    assert result["plan"]["candidate_sha"]==r.OLD
    assert result["journal"]["steps"]
    old["journal"]["outcome"]="accepted"
    with pytest.raises(PermissionError,match="INTERRUPTED_PRECUTOVER_LEDGER_CHANGED"):
        r.existing_release(s,I,tx)
    old["journal"].pop("outcome")
    old["catalog"]["mode"]="segmented"
    with pytest.raises(PermissionError,match="PRIOR_BEFORE_IMAGE_OR_LEGACY_CATALOG_CHANGED"):
        r.existing_release(s,I,tx)


def test_prior_owner_and_rescue_receipts_cannot_be_forged():
    data={}
    for label,(path,action,candidate,scope) in r.OLD_RESCUE_PROOFS.items():
        data[path]={"action":action,"candidate_sha":candidate,"scope_sha256":scope,
                    "owner_oid":r.OLD_OWNER,"independently_verified_entra_owner":True}
    data[(r.PREVIOUS_GRANT_ROOT/"audit-journal-ticket-core-rescue"/r.RESCUED_CORE/"result.json")]={
        "schema_version":"1.0","status":"ticket_core_running_verified",
        "restored_container_id":r.CORE_ID}
    data[(r.PREVIOUS_GRANT_ROOT/"audit-journal-legacy-admission-rescue"/r.RESCUED_ADMISSION/"result.json")]={
        "schema_version":"1.0","status":"legacy_admission_restored"}
    tx=SimpleNamespace(raw_file=lambda path,mode:r.canonical(data[Path(path)]))
    assert len(r.approved_prior_receipts(tx))==5
    path=next(iter(r.OLD_RESCUE_PROOFS.values()))[0]
    data[path]["independently_verified_entra_owner"]=False
    with pytest.raises(PermissionError,match="PRIOR_IDENTITY_OR_SCOPE_MISMATCH"):
        r.approved_prior_receipts(tx)


def test_only_one_approved_source_delta_and_exact_units(monkeypatch):
    from pathlib import Path
    source_root=Path(__file__).resolve().parents[2]
    fake=SimpleNamespace(SOURCES=("tools/audit_journal_control.py",r.MATCHER),
                         UNITS=("jason-audit-journal-release.service",),BASE=s.BASE)
    payload={
        "tools/audit_journal_control.py":b"unchanged",
        r.MATCHER:(source_root/r.MATCHER).read_bytes(),
        "infrastructure/jason-audit-journal/jason-audit-journal-release.service":
            (source_root/"infrastructure/jason-audit-journal/jason-audit-journal-release.service").read_bytes(),
    }
    installed={
        s.BASE/"trusted/tools/audit_journal_control.py":b"unchanged",
        s.BASE/"trusted"/r.MATCHER:b"older Docker 29 matcher",
        Path("/etc/systemd/system/jason-audit-journal-release.service"):
            payload["infrastructure/jason-audit-journal/jason-audit-journal-release.service"],
    }
    tx=SimpleNamespace(raw_file=lambda path,mode:installed[Path(path)])
    assert r.validate_reviewed_trust(fake,payload,tx)==[r.MATCHER]
    installed[s.BASE/"trusted/tools/audit_journal_control.py"]=b"unknown mutation"
    with pytest.raises(PermissionError,match="UNREVIEWED_NATIVE_OR_SQL_SOURCE_DELTA"):
        r.validate_reviewed_trust(fake,payload,tx)
    installed[s.BASE/"trusted/tools/audit_journal_control.py"]=b"unchanged"
    installed[Path("/etc/systemd/system/jason-audit-journal-release.service")]=b"weakened hardening"
    with pytest.raises(PermissionError,match="UNEXPECTED_INSTALLED_SYSTEMD_UNIT"):
        r.validate_reviewed_trust(fake,payload,tx)


def test_wrong_owner_denied_before_any_root_authorization_or_service_write(monkeypatch):
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    old,current,scope=synthetic()
    pre={"old":old,"now":current,"source":(66306,10261846),
         "prior_hashes":{"original":"a"*64},"desired_hash":"b"*64}
    monkeypatch.setattr(r,"independent_preflight",lambda *args,**kwargs:(scope,pre))
    @__import__('contextlib').contextmanager
    def locks():
        yield
    called=[]
    auth={"locks":locks,"owner":lambda review:"UNLICENSED"}
    with pytest.raises(PermissionError,match="INDEPENDENT_LICENSED_OWNER_REQUIRED"):
        r.execute(None,None,None,None,auth,CANDIDATE,{})
    assert called==[]


def test_native_open_breaker_allows_only_documented_failed_journal():
    from datetime import datetime,timezone
    now=datetime.now(timezone.utc)
    control={"circuit_breaker":{"state":"open",
             "reason":"continuous_production_drift_detected"}}
    drift={"status":"drift_detected",
           "observed_at":now.isoformat(),
           "problems":[{"kind":"failed_system_unit",
                         "unit":"jason-audit-journal-release.service",
                         "state":"failed"}]}
    assert r.verify_known_native_incident(control,drift,now=now)["known_incident"] is True
    drift["problems"].append({"kind":"failed_system_unit",
                             "unit":"jason-production-drift-watchdog.service",
                             "state":"failed"})
    assert r.verify_known_native_incident(control,drift,now=now)["problem_count"]==2
    drift["problems"].append({"kind":"failed_system_unit",
                             "unit":"jason-runtime.service",
                             "state":"failed"})
    with pytest.raises(PermissionError,match="UNRELATED_PRODUCTION_NATIVE_DRIFT"):
        r.verify_known_native_incident(control,drift,now=now)


def test_native_drift_staleness_and_breaker_bypass_denied():
    from datetime import datetime,timedelta,timezone
    now=datetime.now(timezone.utc)
    drift={"status":"drift_detected",
           "observed_at":(now-timedelta(minutes=6)).isoformat(),
           "problems":[{"kind":"failed_system_unit",
                        "unit":"jason-audit-journal-release.service",
                        "state":"failed"}]}
    control={"circuit_breaker":{"state":"open",
             "reason":"continuous_production_drift_detected"}}
    with pytest.raises(PermissionError,match="NATIVE_DRIFT_EVIDENCE_EXPIRED"):
        r.verify_known_native_incident(control,drift,now=now)
    drift["observed_at"]=now.isoformat()
    control["circuit_breaker"]["state"]="closed"
    with pytest.raises(PermissionError,match="PROTECTED_BREAKER_NOT_IN_KNOWN_INCIDENT_HOLD"):
        r.verify_known_native_incident(control,drift,now=now)
    control["circuit_breaker"]["state"]="open"
    drift["problems"]=[]
    with pytest.raises(PermissionError,match="NATIVE_DRIFT_UNEXPECTED_STATUS"):
        r.verify_known_native_incident(control,drift,now=now)
    drift["problems"]=[{"kind":"failed_system_unit",
                        "unit":"jason-production-drift-watchdog.service",
                        "state":"failed"}]
    with pytest.raises(PermissionError,match="KNOWN_FAILED_RELEASE_NOT_IN_NATIVE_EVIDENCE"):
        r.verify_known_native_incident(control,drift,now=now)


def bounded_grant_fixture(*,outcome="installing",age_minutes=1):
    from datetime import datetime,timedelta,timezone
    now=datetime.now(timezone.utc)
    scope={
        "action":r.ACTION,
        "policy":{"candidate_sha":CANDIDATE,"rollback_sha":r.OLD_ROLLBACK},
        "bounded_objective_continuation":{
            "one_owner_decision_for_bounded_objective":True,
            "allowed_recovery_branches":list(r.RECOVERY_BRANCHES),
            "root_execution_recovery_claims_maximum":2,
            "reviewed_objective_installer_sha256":r.digest(b"reviewed-installer"),
            "reviewed_objective_recovery_sha256":r.digest(b"reviewed-recovery"),
        },
    }
    grant={
        "schema_version":"1.0","action":r.ACTION,
        "candidate_sha":CANDIDATE,"source_commit_sha":CANDIDATE,
        "rollback_sha":r.OLD_ROLLBACK,
        "owner_oid":r.OLD_OWNER,"independently_verified_entra_owner":True,
        "one_original_owner_decision":True,
        "derived_one_use_release_and_rollback_claim":True,
        "previous_exact_grants_reused":False,
        "decided_at":(now-__import__("datetime").timedelta(minutes=age_minutes)).isoformat(),
        "expires_at":(now+__import__("datetime").timedelta(hours=7)).isoformat(),
        "scope":scope,"scope_sha256":r.digest(scope),
    }
    state={"scope_sha256":r.digest(scope),"outcome":outcome,"entries":[]}
    return grant,state,now


def test_prior_bounded_owner_decision_permits_one_prequeue_recovery_only():
    grant,state,now=bounded_grant_fixture()
    targets=r.bounded_transaction_targets(s)
    approved=r.validate_prequeue_recovery_grant(grant,state,CANDIDATE,targets,now=now)
    assert approved==grant["scope"]
    assert len(targets)==8
    assert targets[str(s.PRIVATE/"release-journal.json")]==0o400
    assert targets[str(s.BASE/"trusted"/r.MATCHER)]==0o444
    assert r.validate_prequeue_recovery_grant(grant,{**state,"outcome":"rolled_back"},
                                              CANDIDATE,targets,now=now)==approved


@pytest.mark.parametrize("fault",[
    "wrong_owner","approval_absent","other_commit","scope_changed",
    "expired","queued","already_accepted","unknown_target","duplicate_target",
    "unsupported_mode","extra_file_operation","unbounded_expiry",
])
def test_old_plan_cannot_widen_scope_or_replay_queued_action(fault):
    from datetime import timedelta
    grant,state,now=bounded_grant_fixture()
    targets=r.bounded_transaction_targets(s)
    if fault=="wrong_owner":grant["owner_oid"]="foreign-actor"
    elif fault=="approval_absent":grant["independently_verified_entra_owner"]=False
    elif fault=="other_commit":grant["candidate_sha"]="b"*40
    elif fault=="scope_changed":grant["scope"]["policy"]["candidate_sha"]="b"*40
    elif fault=="expired":grant["expires_at"]=(now-timedelta(seconds=1)).isoformat()
    elif fault=="queued":state["outcome"]="queued"
    elif fault=="already_accepted":state["outcome"]="accepted"
    elif fault=="unbounded_expiry":grant["expires_at"]=(now+timedelta(days=5)).isoformat()
    elif fault in ("unknown_target","unsupported_mode","extra_file_operation"):
        path=str(s.PRIVATE/"release-plan.json")
        state["entries"]=[{"kind":"replace","path":path,
                           "mode":0o400,"before_hex":"78",
                           "after_sha256":"e"*64}]
        if fault=="unknown_target":state["entries"][0]["path"]="/etc/systemd/system/unrelated.service"
        if fault=="unsupported_mode":state["entries"][0]["mode"]=0o777
        if fault=="extra_file_operation":state["entries"][0]["kind"]="directory"
    elif fault=="duplicate_target":
        entry={"kind":"replace","path":str(s.PRIVATE/"release-plan.json"),
               "mode":0o400,"before_hex":"78","after_sha256":"e"*64}
        state["entries"]=[entry,dict(entry)]
    with pytest.raises(PermissionError):
        r.validate_prequeue_recovery_grant(grant,state,CANDIDATE,targets,now=now)


def test_resume_keeps_original_decision_and_never_calls_owner(monkeypatch,tmp_path):
    from contextlib import contextmanager
    grant,state,now=bounded_grant_fixture()
    root=tmp_path/"trusted-ledger"
    child=root/CANDIDATE
    child.mkdir(parents=True)
    monkeypatch.setattr(r,"ROOT",root)
    monkeypatch.setattr(r,"root_dir",lambda path:None)
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    class FakeS:
        PROTECTED={}
    fake_s=FakeS()
    targets=r.bounded_transaction_targets(s)
    monkeypatch.setattr(r,"bounded_transaction_targets",lambda _s:targets)
    mock_files={child/"authorization.json":grant,
                child/"transaction.json":state}
    class FakeTx:
        def raw_file(self,path,mode):
            return r.canonical(mock_files[Path(path)])
        def __init__(self,*args):
            self.queued=False
        def rollback(self):
            effects.append("transaction_rollback")
    class FakeTxModule:
        raw_file=staticmethod(lambda path,mode:r.canonical(mock_files[Path(path)]))
        InstallTransaction=FakeTx
        @staticmethod
        def atomic(path,raw,mode):
            effects.append("prequeue_claim")
            assert str(path).endswith("prequeue-resume.json")
    effects=[]
    monkeypatch.setattr(r,"txlib",FakeTxModule)
    class I:
        @staticmethod
        def installation_parent_custody(c):pass
        @staticmethod
        def read(path):return b"not_called_no_protected"
    monkeypatch.setattr(r,"systemd_show",
                        lambda *args:{"ActiveState":"failed","MainPID":"0"})
    monkeypatch.setattr(r,"independent_preflight",
                        lambda *args,**kwargs:(grant["scope"],{"valid":"after_rollback"}))
    monkeypatch.setattr(r,"install_reviewed_claim",
                        lambda *args:effects.append("queued_from_same_plan"))
    @contextmanager
    def locks():yield
    auth={"locks":locks}
    payload={"tools/audit_journal_install.py":b"reviewed-installer",
             "tools/audit_journal_objective_recovery.py":b"reviewed-recovery"}
    r.resume_prequeue(I,fake_s,
                      {"audit_journal_install_transaction":FakeTxModule},
                      None,auth,CANDIDATE,payload)
    assert effects==["prequeue_claim","transaction_rollback","queued_from_same_plan"]
    assert "owner" not in auth
    (child/"revoked.json").write_text('{"revoked":true}')
    with pytest.raises(PermissionError,match="BOUNDED_OWNER_PLAN_REVOKED"):
        r.resume_prequeue(I,fake_s,
                          {"audit_journal_install_transaction":FakeTxModule},
                          None,auth,CANDIDATE,payload)
    assert effects==["prequeue_claim","transaction_rollback","queued_from_same_plan"]


def test_stopped_rollback_slots_checked_before_full_journal_migration():
    old,_,_=synthetic()
    old["plan"]["scope"]["rollback_container_capacity_before"]={
        "existing_count":2,
        "existing_names":["jason-runtime-rollback-old","jason-mcp-pilot-rollback-old"],
        "limit_before":s.ROLLBACK_LIMIT_BEFORE,
        "reserved_slots":s.ROLLBACK_CONTAINER_RESERVE,
    }
    class I:
        values=[
            "jason-runtime-rollback-old",
            "jason-mcp-pilot-rollback-old",
            "jason-pmv4-ticket-core-rollback-audit-before-20b32548402d",
        ]
        @classmethod
        def command(cls,argv):
            assert argv[:2]==["/usr/bin/docker","ps"]
            return "\n".join(cls.values)
    got=r.verify_recovery_container_capacity(I,s,eng,old)
    assert got["count"]==3 and got["new_release_slots_after"]==9
    assert got["reserve_for_new_release"]==6
    I.values=["jason-runtime-rollback-%02d"%x for x in range(22)]
    with pytest.raises(PermissionError,match="INSUFFICIENT_RECOVERY_CONTAINER_SLOTS"):
        r.verify_recovery_container_capacity(I,s,eng,old)
    I.values=["jason-runtime-rollback-same"]*2
    with pytest.raises(PermissionError,match="MALFORMED_STOPPED_CONTAINER_INVENTORY"):
        r.verify_recovery_container_capacity(I,s,eng,old)
