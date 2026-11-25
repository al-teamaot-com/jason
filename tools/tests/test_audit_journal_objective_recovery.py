"""No-Root synthetic tests for one bounded Owner plan and exact journal recovery."""
import copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import audit_journal_objective_recovery as r
from tools import audit_journal_release_scope as s
from tools import audit_journal_container_release as eng
from tools import audit_journal_rollback_slot_reservation as retention
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
        "rollback_container_limit_before":27,
        "rollback_container_limit_after":27,
        "rollback_container_reserve":s.ROLLBACK_CONTAINER_RESERVE,
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
    assert len(r.STEPS)==8 and len(r.RECOVERY_BRANCHES)==6
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
                         NATIVE={},UNITS=("jason-audit-journal-release.service",),BASE=s.BASE)
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
    scope["bounded_objective_continuation"]["rollback_container_capacity_revalidated"]={
        "count":21,"new_release_slots_after":27,"retirement":None}
    @__import__('contextlib').contextmanager
    def locks():
        yield
    called=[]
    auth={"locks":locks,"owner":lambda review:"UNLICENSED"}
    with pytest.raises(PermissionError,match="INDEPENDENT_LICENSED_OWNER_REQUIRED"):
        r.execute(None,s,{"audit_journal_container_release":eng},None,auth,CANDIDATE,{})
    assert called==[]


def test_native_readonly_evaluator_can_resolve_system_administration_tools(monkeypatch):
    from shutil import which
    actual_run=r.subprocess.run
    def evaluator(argv, **kwargs):
        assert argv==["/usr/bin/python3",str(s.ROOT_DRIFT_EVALUATOR),"--config",str(s.DESIRED)]
        assert kwargs["cwd"]=="/" and kwargs["env"]["HOME"]=="/root"
        path=kwargs["env"]["PATH"]
        assert "/usr/sbin" in path.split(":")
        assert which("runuser",path=path) is not None
        result=actual_run(["runuser","--version"],env=kwargs["env"],capture_output=True,text=True,check=True)
        assert "runuser" in result.stdout
        return SimpleNamespace(returncode=2,stdout=json.dumps({"schema_version":"1.0",
            "status":"drift_detected","problems":[{"kind":"failed_system_unit"}]}))
    monkeypatch.setattr(r.subprocess,"run",evaluator)
    assert r.observe_native_readonly(s)["status"]=="drift_detected"
    monkeypatch.setattr(r.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=1,stdout=""))
    with pytest.raises(PermissionError,match="NATIVE_READONLY_EVALUATION_UNAVAILABLE"):
        r.observe_native_readonly(s)


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
            "reviewed_slot_reservation_source_sha256":r.digest(b"reviewed-slots"),
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
    old,current,review=synthetic()
    grant["producer_before_snapshot_sha256"]=r.digest(current)
    mock_files={child/"authorization.json":grant,
                child/"transaction.json":state,
                child/"producer-before.json":current}
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
    monkeypatch.setattr(r,"frozen_producer_snapshot",
                        lambda _s,_eng,_review,rows:rows)
    monkeypatch.setattr(r,"install_reviewed_claim",
                        lambda *args:effects.append("queued_from_same_plan"))
    @contextmanager
    def locks():yield
    auth={"locks":locks}
    payload={"tools/audit_journal_install.py":b"reviewed-installer",
             "tools/audit_journal_objective_recovery.py":b"reviewed-recovery",
             "tools/audit_journal_rollback_slot_reservation.py":b"reviewed-slots"}
    r.resume_prequeue(I,fake_s,
                      {"audit_journal_install_transaction":FakeTxModule,"audit_journal_container_release":eng},
                      None,auth,CANDIDATE,payload)
    assert effects==["prequeue_claim","transaction_rollback","queued_from_same_plan"]
    assert "owner" not in auth
    (child/"revoked.json").write_text('{"revoked":true}')
    with pytest.raises(PermissionError,match="BOUNDED_OWNER_PLAN_REVOKED"):
        r.resume_prequeue(I,fake_s,
                          {"audit_journal_install_transaction":FakeTxModule,"audit_journal_container_release":eng},
                          None,auth,CANDIDATE,payload)
    assert effects==["prequeue_claim","transaction_rollback","queued_from_same_plan"]


def pin_prior_root_scope(monkeypatch,old):
    """In production OLD_SCOPE is a fixed Root-record hash, not a guess."""
    sha=r.digest(old["plan"]["scope"])
    old["plan"]["scope_sha256"]=sha
    monkeypatch.setattr(r,"OLD_SCOPE",sha)
    return sha


def native_policy():
    return {"max_stopped_rollback_containers":27,
            "rollback_container_prefixes":[
                "jason-runtime-rollback-","jason-mcp-pilot-rollback-",
                "jason-mcp-rollback-","jason-teams-gateway-rollback-",
                "jason-pmv4-ticket-core-rollback-audit-"]}


def test_stopped_rollback_slots_checked_before_full_journal_migration(monkeypatch):
    old,_,_=synthetic()
    old["plan"]["scope"]["rollback_container_capacity_before"]={
        "existing_count":21,"existing_names":["historic-"+str(i) for i in range(21)],
        "limit_before":27,"limit_after":27,"reserved_slots":6,"cleanup_allowed":False}
    pin_prior_root_scope(monkeypatch,old)
    class I:
        values=[
            "jason-runtime-rollback-old",
            "jason-mcp-pilot-rollback-old",
            "jason-mcp-rollback-constant-contact-oauth-20261112",
            "jason-pmv4-ticket-core-rollback-audit-before-20b32548402d",
        ]
        @classmethod
        def command(cls,argv):
            assert argv[:2]==["/usr/bin/docker","ps"]
            return "\n".join(cls.values)
    got=r.verify_recovery_container_capacity(I,s,eng,old,native_policy())
    assert got["count"]==4 and got["new_release_slots_after"]==10
    assert got["reserve_for_new_release"]==6 and got["retirement"] is None
    I.values=["jason-runtime-rollback-%02d"%x for x in range(23)]
    with pytest.raises(PermissionError,match="INSUFFICIENT_RECOVERY_CONTAINER_SLOTS"):
        r.verify_recovery_container_capacity(I,s,eng,old,native_policy())
    I.values=["jason-runtime-rollback-same"]*2
    with pytest.raises(PermissionError,match="MALFORMED_STOPPED_CONTAINER_INVENTORY"):
        r.verify_recovery_container_capacity(I,s,eng,old,native_policy())


def test_exact_historical_census_scope_uses_current_native_policy(monkeypatch):
    """Actual historical record contains 27/27/6 and 21 old stopped names."""
    old,_,_=synthetic()
    class Live:
        @staticmethod
        def command(argv):
            assert argv[:2]==["/usr/bin/docker","ps"]
            return "\n".join("jason-runtime-rollback-%02d"%i for i in range(20))
    scope=old["plan"]["scope"]
    scope["rollback_container_limit_before"]=27
    scope["rollback_container_limit_after"]=27
    scope["rollback_container_reserve"]=6
    scope["rollback_container_capacity_before"]={
        "existing_count":21,"existing_names":["historic-%02d"%i for i in range(21)],
        "limit_before":27,"limit_after":27,"reserved_slots":6,"cleanup_allowed":False}
    pin_prior_root_scope(monkeypatch,old)
    result=r.verify_recovery_container_capacity(Live,s,eng,old,native_policy())
    assert result["count"]==20 and result["limit_before"]==21
    assert result["new_release_slots_after"]==26 and result["retirement"] is None
    # Hash identity, not a historical scalar assertion, is the authority.
    scope["rollback_container_limit_before"]=999
    with pytest.raises(PermissionError,match="PREVIOUS_IMMUTABLE_OWNER_SCOPE_CHANGED"):
        r.verify_recovery_container_capacity(Live,s,eng,old,native_policy())
    old["plan"]["scope_sha256"]=r.digest(scope)
    with pytest.raises(PermissionError,match="PREVIOUS_IMMUTABLE_OWNER_SCOPE_CHANGED"):
        r.verify_recovery_container_capacity(Live,s,eng,old,native_policy())
    scope["rollback_container_limit_before"]=27
    pin_prior_root_scope(monkeypatch,old)
    policy=native_policy();policy["max_stopped_rollback_containers"]=28
    with pytest.raises(PermissionError,match="CURRENT_PROTECTED_ROLLBACK_LIMITS_CHANGED"):
        r.verify_recovery_container_capacity(Live,s,eng,old,policy)


def test_root_hash_guard_rejects_unsigned_history_before_even_listing_docker(monkeypatch):
    old,_,_=synthetic()
    class NoDockerCalls:
        @staticmethod
        def command(argv):
            pytest.fail("Unsigned historical state must be denied before Docker read")
    with pytest.raises(PermissionError,match="PREVIOUS_IMMUTABLE_OWNER_SCOPE_CHANGED"):
        r.verify_recovery_container_capacity(NoDockerCalls,s,eng,old,native_policy())


def test_frozen_snapshot_reuses_exact_bytes_despite_volatile_health_changes():
    old,current,review=synthetic()
    frozen=copy.deepcopy(current)
    r.frozen_producer_snapshot(s,eng,review,frozen)
    current["jason-runtime"]["State"]["Health"]={"Status":"healthy","Log":[{"End":"later"}]}
    r.frozen_producer_snapshot(s,eng,review,current)
    pre={"old":old,"now":frozen}
    first=r.prepare_new_claim(s,CANDIDATE,review,pre,"2026-11-24T13:00:00+00:00")
    retry=r.prepare_new_claim(s,CANDIDATE,review,{**pre,"now":frozen},"2026-11-24T13:00:00+00:00")
    assert first==retry
    current["jason-runtime"]["Config"]["User"]="root"
    with pytest.raises((PermissionError,ValueError)):
        r.frozen_producer_snapshot(s,eng,review,current)


def test_single_command_continues_existing_grant_without_owner(monkeypatch,tmp_path):
    root=tmp_path/"ledger";(root/CANDIDATE).mkdir(parents=True)
    monkeypatch.setattr(r,"ROOT",root)
    monkeypatch.setattr(r,"execute",lambda *a:pytest.fail("new human decision not permitted"))
    effects=[]
    monkeypatch.setattr(r,"resume_prequeue",lambda *a:effects.append("existing_claim"))
    r.execute_with_continuation(None,None,{},None,{},CANDIDATE,{})
    assert effects==["existing_claim"]


@pytest.mark.parametrize("phase",["pre_owner","installing","queued"])
def test_single_invocation_automatically_reconciles_only_durable_unqueued_claim(
        monkeypatch,tmp_path,phase):
    root=tmp_path/"ledger";root.mkdir()
    monkeypatch.setattr(r,"ROOT",root)
    effects=[]
    def execute(*args):
        effects.append("original")
        if phase!="pre_owner":
            folder=root/CANDIDATE;folder.mkdir()
            (folder/"authorization.json").write_text("{}")
            (folder/"transaction.json").write_text("{}")
        raise PermissionError("test interruption")
    monkeypatch.setattr(r,"execute",execute)
    monkeypatch.setattr(r,"resume_prequeue",lambda *a:effects.append("same_claim"))
    tx=SimpleNamespace(raw_file=lambda path,mode:r.canonical({"outcome":phase}))
    args=(None,None,{"audit_journal_install_transaction":tx},None,{},CANDIDATE,{})
    if phase=="installing":
        r.execute_with_continuation(*args)
        assert effects==["original","same_claim"]
    else:
        with pytest.raises(PermissionError,match="test interruption"):
            r.execute_with_continuation(*args)
        assert effects==["original"]

def test_complete_preflight_builds_native_slot_plan_and_rechecks_identically(
        monkeypatch,tmp_path):
    """Integration of full preflight using sealed historical record shape.

    Real filesystem, Docker, and privileged read boundaries are substituted;
    the new scope construction and all intermediate semantic gates run.
    """
    from tools import audit_journal_install as installer
    from tools import audit_journal_legacy_admission_rescue as admission
    from tools.tests.test_audit_journal_rollback_slot_reservation import Docker
    old,current,_=synthetic()
    current["jason-pmv4-ticket-core"]["State"]["Health"]={"Status":"healthy"}
    live=tmp_path/"live.sqlite3";live.write_bytes(b"fixture")
    archive=tmp_path/"archive";archive.mkdir()
    private=tmp_path/"private";private.mkdir()
    control=tmp_path/"control";control.mkdir()
    (tmp_path/"pending").mkdir()
    (archive/"governed-audit"/"orchestration").mkdir(parents=True)
    fake_s=SimpleNamespace(**{
        k:getattr(s,k) for k in ("ACTION","SOURCES","NATIVE","UNITS","BASE",
        "ROLLBACK_LIMIT_BEFORE","ROLLBACK_CONTAINER_RESERVE","public_profile","digest")
    },ARCHIVE=archive,PRIVATE=private,CONTROL=control,
        PROFILE=tmp_path/"profile.json",POLICY=tmp_path/"policy.json",
        DESIRED=tmp_path/"desired.json",STATE=tmp_path/"state")
    desired=native_policy()
    desired_raw=r.canonical(desired)
    original_scope=old["plan"]["scope"]
    original_scope["desired_state_initial_sha256"]=r.digest(desired_raw)
    original_scope["rollback_desired_state_sha256"]=r.digest(desired_raw)
    original_scope["desired_state_after_sha256"]=r.digest(desired_raw)
    original_scope["rollback_container_capacity_before"]={
        "existing_count":21,"existing_names":["historic-"+str(i) for i in range(21)],
        "limit_before":27,"limit_after":27,"reserved_slots":6,"cleanup_allowed":False}
    pin_prior_root_scope(monkeypatch,old)
    old["policy"]["profile_sha256"]=r.digest(r.canonical(s.public_profile(r.OLD)))
    old["adoption"]["policy_sha256"]=r.digest(old["policy"])
    old["adoption"]["scope_sha256"]=r.OLD_SCOPE
    old["journal"]["scope_sha256"]=r.OLD_SCOPE
    monkeypatch.setattr(r,"LIVE",live)
    monkeypatch.setattr(r,"ROOT",tmp_path/"root")
    # Synthetic file metadata models the known Root-protected live identity.
    real_lstat=Path.lstat
    real_stat=Path.stat
    def lstat(path):
        if path==live:
            return SimpleNamespace(st_mode=0o100600,st_uid=1000,st_gid=1000,
                                   st_nlink=1,st_dev=66306,st_ino=10261846,st_size=47_500_000_000)
        return real_lstat(path)
    def stat_path(path,*args,**kwargs):
        value=real_stat(path,*args,**kwargs)
        if path==archive:
            fields=list(value);fields[2]=2049
            return __import__("os").stat_result(fields)
        return value
    monkeypatch.setattr(Path,"lstat",lstat)
    monkeypatch.setattr(Path,"stat",stat_path)
    monkeypatch.setattr(r.os.path,"ismount",lambda path:path==archive)
    monkeypatch.setattr(r.shutil,"disk_usage",lambda path:SimpleNamespace(free=175_000_000_000))
    monkeypatch.setattr(r,"existing_release",lambda *args,**kwargs:old)
    monkeypatch.setattr(r,"approved_prior_receipts",lambda *args:{"sealed":"c"*64})
    monkeypatch.setattr(r,"validate_reviewed_trust",lambda *args:[r.MATCHER])
    monkeypatch.setattr(retention,"check_archive_destination",lambda *args,**kwargs:None)
    monkeypatch.setattr(admission,"sql",lambda operation:{
        "before":{},"after":{},"writer_uid":1000,"operation":operation})
    peers=original_scope["protected_peer_before"]
    fake_s.protected_peer_inventory=lambda:peers
    fake_eng=SimpleNamespace(**{
        k:getattr(eng,k) for k in ("ROLES","configuration_matches","planned_configuration",
                                  "exact_original_configuration")
    },DockerEngine=lambda:SimpleNamespace(inspect=lambda role:current[role]))
    payload={name:b"fixture-"+name.encode() for name in (
        *s.SOURCES,*s.NATIVE,*installer.EXTRA,
        *("infrastructure/jason-audit-journal/"+name for name in (*s.UNITS,*installer.OVERRIDES)))}
    raw_files={fake_s.PROFILE:r.canonical(s.public_profile(r.OLD)),
               control/"profile.json":r.canonical(s.public_profile(r.OLD)),
               private/"desired-final.json":desired_raw,
               private/"desired-rollback.json":desired_raw,
               fake_s.DESIRED:desired_raw}
    tx=SimpleNamespace(raw_file=lambda path,mode:raw_files[Path(path)])
    docker=Docker()
    I=SimpleNamespace(EXTRA=installer.EXTRA,OVERRIDES=installer.OVERRIDES,
                      command=docker.command,health_dropins=lambda _: {},
                      schema_and_sample=lambda _:"a"*64)
    modules={"audit_journal_install_transaction":tx,"audit_journal_container_release":fake_eng}
    review,pre=r.independent_preflight(I,fake_s,modules,None,CANDIDATE,payload,production=False)
    assert review["rollback_container_limit_before"]==21
    assert review["rollback_container_capacity_before"]["existing_count"]==21
    assert review["bounded_objective_continuation"]["rollback_container_capacity_revalidated"]["count"]==22
    assert review["bounded_objective_continuation"]["rollback_container_capacity_revalidated"]["retirement"]["id"]==retention.ID
    assert any(retention.ID in x for x in review["installation_targets"])
    assert review["source_dataset_identity"]=={"device":66306,"inode":10261846}
    again,pre2=r.independent_preflight(I,fake_s,modules,None,CANDIDATE,payload,production=False)
    assert review==again and pre["source"]==pre2["source"]
    profile,policy,adoption,plan,journal=r.prepare_new_claim(
        fake_s,CANDIDATE,review,pre,"2026-11-24T15:00:00+00:00")
    assert plan["scope_sha256"]==r.digest(plan["scope"])==adoption["scope_sha256"]==journal["scope_sha256"]
    assert plan["scope"]["rollback_container_limit_before"]==21
    assert docker.removed==[]
