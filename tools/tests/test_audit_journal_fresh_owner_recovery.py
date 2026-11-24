"""Fail-closed tests for one *new* Owner-approved journal claim.

Never runs Root host actions. All examples are synthetic; live recovery still
requires protected Main CI, independent Owner Entra login and Root preflight.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from tools import audit_journal_fresh_owner_recovery as r
from tools import audit_journal_install_transaction as t

REPO=Path(__file__).resolve().parents[2]
REVIEWED={name:(REPO/"infrastructure/jason-audit-journal"/name).read_bytes()
          for name in r.UNITS}


@pytest.fixture
def subject(monkeypatch):
    old=datetime.now(timezone.utc)-timedelta(days=3)
    scope={
        "action":r.ACTION,
        "policy":{"candidate_sha":r.EXPIRED,"rollback_sha":r.ROLLBACK},
        "source_sha256":{"tools/audit_journal_control.py":"a"*64},
        "source_dataset_identity":{"device":66306,"inode":10261846},
        "producer_before":{},
    }
    monkeypatch.setattr(r,"EXPIRED_SCOPE",r.digest(scope))
    plan={"action":r.ACTION,"candidate_sha":r.EXPIRED,
          "scope":scope,"scope_sha256":r.digest(scope),"owner_oid":r.OWNER,
          "independently_verified_entra_owner":True}
    journal={"scope_sha256":r.digest(scope),"steps":{},
             "started_at":old.isoformat(),
             "recovery_started_at":(old+timedelta(minutes=1)).isoformat()}
    adoption={"scope_sha256":r.digest(scope),"owner_oid":r.OWNER,
              "independently_verified_entra_owner":True}
    catalog={"mode":"legacy","generation":0,"epoch":None,"segments":[]}
    policy={"candidate_sha":r.EXPIRED,"enabled":True,
            "trusted_source_sha256":scope["source_sha256"],
            "public_profile":{"component_source_sha":r.EXPIRED}}
    old_units={n:r.exact_unit_pair(REVIEWED[n])[0] for n in r.UNITS}
    def read_fn(path,mode):
        assert mode==0o644
        return old_units[Path(path).name]
    def unit_fn(name):
        return {"ActiveState":"failed","MainPID":"0",
                "AmbientCapabilities":"","UnitFileState":"enabled"}
    obj={"get_plan":plan,"get_journal":journal,"get_adoption":adoption,
         "get_catalog":catalog,"get_policy":policy,"read_fn":read_fn,
         "unit_fn":unit_fn,"check_live":False}
    return obj


def verify(subject):
    return r.preflight("c"*40,REVIEWED,**subject)


def test_fresh_exact_owner_scope_has_strong_supersession_evidence(subject):
    scope,_=verify(subject)
    rec=scope["fresh_owner_recovery"]
    assert scope["action"]==r.ACTION
    assert rec["action"]==r.RECOVERY_ACTION
    assert rec["previous_candidate_sha"]==r.EXPIRED
    assert rec["previous_scope_sha256"]==r.EXPIRED_SCOPE
    assert rec["old_execution_authority_reused"] is False
    assert rec["initial_cutover_not_performed"] is True
    assert rec["fresh_authenticated_licensed_owner_required"] is True
    assert rec["service_units_before_sha256"]==r.UNIT_BEFORE_SHA
    assert rec["service_units_after_sha256"]==r.UNIT_AFTER_SHA
    assert r.digest(scope)!=r.EXPIRED_SCOPE


@pytest.mark.parametrize("change",[
    ("plan", "candidate_sha", "d"*40),
    ("plan", "scope_sha256", "f"*64),
    ("plan", "owner_oid", "other"),
    ("plan", "independently_verified_entra_owner", False),
    ("journal", "scope_sha256", "f"*64),
    ("journal", "steps", {"install:runtime":{"verified":True}}),
    ("journal", "outcome", "rolled_back"),
    ("journal", "recovery_started_at", ""),
    ("adoption", "owner_oid", "other"),
    ("catalog", "mode", "segmented"),
    ("catalog", "segments", [{"id":"bad"}]),
    ("policy", "candidate_sha", "c"*40),
    ("policy", "enabled", False),
])
def test_changed_previous_scope_or_cutover_is_denied(subject,change):
    where,key,value=change
    label={"plan":"get_plan","journal":"get_journal","adoption":"get_adoption",
           "catalog":"get_catalog","policy":"get_policy"}[where]
    subject[label][key]=value
    with pytest.raises((PermissionError,TypeError,ValueError)):
        verify(subject)


def test_prior_claim_must_be_expired(subject):
    subject["get_journal"]["started_at"]=(datetime.now(timezone.utc)-timedelta(hours=4)).isoformat()
    subject["get_journal"]["recovery_started_at"]=(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat()
    with pytest.raises(PermissionError,match="PRIOR_CLAIM_NOT_EXPIRED"):
        verify(subject)


def test_prior_release_must_be_stopped(subject):
    subject["unit_fn"]=lambda _:{"ActiveState":"activating","MainPID":"919",
                                "AmbientCapabilities":"","UnitFileState":"enabled"}
    with pytest.raises(PermissionError,match="FAILED_RELEASE_NOT_QUIESCED"):
        verify(subject)


def test_live_unit_must_be_exact_one_line_security_correction(subject):
    source=REVIEWED[r.UNITS[0]]
    assert source.count(b"AmbientCapabilities=CAP_SETUID\n")==1
    tampered=dict(REVIEWED)
    tampered[r.UNITS[0]]=source+b"AmbientCapabilities=CAP_SYS_ADMIN\n"
    with pytest.raises(PermissionError,match="LIVE_UNIT_DIFFERS"):
        r.preflight("c"*40,tampered,**subject)


def test_installed_before_image_is_exact(subject):
    source=REVIEWED[r.UNITS[1]]
    good=r.exact_unit_pair(source)[0]
    assert r.digest(good)==r.UNIT_BEFORE_SHA[r.UNITS[1]]
    def read(p,mode):
        value=r.exact_unit_pair(REVIEWED[Path(p).name])[0]
        if Path(p).name==r.UNITS[1]:
            value+=b"# unexpected change\n"
        return value
    subject["read_fn"]=read
    with pytest.raises(PermissionError,match="LIVE_UNIT_DIFFERS"):
        verify(subject)


def test_changed_or_missing_unit_hardening_denied():
    base=REVIEWED[r.UNITS[0]]
    for raw in (base.replace(b"NoNewPrivileges=true\n",b""),
                base.replace(b"AmbientCapabilities=CAP_SETUID\n",b""),
                base.replace(b"RestrictAddressFamilies=AF_UNIX AF_NETLINK\n",b"")):
        with pytest.raises(PermissionError):
            r.exact_unit_pair(raw)


def test_transaction_mode_644_only_allowed_for_three_journal_units(monkeypatch):
    orig_raw=t.raw_file
    monkeypatch.setattr(t,"raw_file",lambda path,mode:b"old")
    tx=object.__new__(t.InstallTransaction)
    tx.state={"entries":[]};tx.fault=lambda _name:None
    def record(kind,path,**kw):
        value={"kind":kind,"path":str(path),**kw}
        tx.state["entries"].append(value)
        return value
    tx.record=record
    for name in r.UNITS:
        tx.state={"entries":[]}
        tx.replace(Path("/etc/systemd/system")/name,b"old",0o644)
    with pytest.raises(PermissionError,match="REPLACEMENT_MODE"):
        tx.replace(Path("/etc/systemd/system/unrelated.service"),b"old",0o644)
    with pytest.raises(PermissionError,match="REPLACEMENT_MODE"):
        tx.replace(Path("/etc/systemd/system/jason-audit-journal-release.service"),b"old",0o777)
    monkeypatch.setattr(t,"raw_file",orig_raw)


def test_one_owner_challenge_cannot_be_skipped(monkeypatch,subject):
    scope,prior=verify(subject)
    monkeypatch.setattr(r,"preflight",lambda *a,**kw:(scope,prior))
    monkeypatch.setattr(r,"governed_readmission",lambda *a,**kw:{"protected":True})
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    called=[]
    scope["fresh_owner_recovery"]["reviewed_recovery_source_sha"]="c"*40
    scope["fresh_owner_recovery"]["recovery_installation_targets"]=["/exact/owned"]

    monkeypatch.setattr(r,"install",lambda *a:called.append(a))
    @contextmanager
    def lock():yield
    auth={"locks":lock,"owner":lambda x:"unlicensed"}
    payload={"infrastructure/jason-audit-journal/"+name:body for name,body in REVIEWED.items()}
    with pytest.raises(PermissionError,match="LICENSED_OWNER_IDENTITY_REQUIRED"):
        r.execute(None,None,None,None,auth,"c"*40,payload)
    assert called==[]
    prompts=[]
    def signed_owner(consent):
        prompts.append(consent)
        assert consent["action"] == r.RECOVERY_ACTION
        assert consent["policy"]["candidate_sha"] == "c"*40
        assert consent["fresh_owner_recovery_install_scope_sha256"] == r.digest(scope)
        assert consent["installation_targets"] == ["/exact/owned"]
        return r.OWNER
    auth["owner"]=signed_owner
    r.execute(None,None,None,None,auth,"c"*40,payload)
    assert len(called)==1 and len(prompts)==1
    assert called[0][4]==scope and called[0][5]==prior
    assert called[0][7]==prompts[0]

def test_recovery_consent_differs_from_expired_owner_action(subject):
    scope,_=verify(subject)
    scope["fresh_owner_recovery"]["reviewed_recovery_source_sha"]="c"*40
    value=r.exact_consent_scope(scope,"c"*40)
    assert value["action"]==r.RECOVERY_ACTION
    assert value["policy"]=={"candidate_sha":"c"*40,"rollback_sha":r.ROLLBACK}
    assert value["fresh_owner_recovery_install_scope_sha256"]==r.digest(scope)
    assert scope["action"]==r.ACTION
    assert value["installation_targets"]==scope["fresh_owner_recovery"]["recovery_installation_targets"]
    with pytest.raises(PermissionError,match="REVIEWED_RECOVERY_SOURCE_BINDING"):
        r.exact_consent_scope(scope,"d"*40)


def test_real_readmission_checks_protected_peers_and_open_breaker(monkeypatch):
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    before={"jason-runtime":{"Id":"cid-1","Image":"sha256:"+"a"*64,"State":{"Running":True}}}
    live=deepcopy(before)
    raw=r.canon(before)
    given={
        "plan":{"scope":{"protected_peer_before":{"ticket-core":"baseline"}},
                "producer_before_sha256":r.digest(raw)},
    }
    state={"breaker":"open","reason":"continuous_production_drift_detected"}
    drift={
        "status":"drift_detected",
        "problems":[{"kind":"failed_system_unit","unit":"jason-audit-journal-release.service",
                     "state":"failed"}],
        "observed_at":datetime.now(timezone.utc).isoformat(),
    }
    class FakeI:
        @staticmethod
        def installation_parent_custody(c):pass
        @staticmethod
        def read(path):return b"protected fixed baseline"
    fake=FakeI()
    fake_s=SimpleNamespace(
        PROTECTED={"/irrelevant":{"sha":"none"}},
        protected_peer_inventory=lambda:{"ticket-core":"baseline"},
    )
    fake_s.PROTECTED={"/immutable/protected":r.digest(b"protected fixed baseline")}
    class FakeEngine:
        ROLES=("jason-runtime",)
        @staticmethod
        def exact_original_configuration(x):
            return {"image":x["Image"]}
        class DockerEngine:
            def inspect(self,role):
                assert role=="jason-runtime"
                return live["jason-runtime"]
    class FakeInventory:
        @staticmethod
        def handles(path):return {"complete":True,"open_handles":[]}
    modules={"audit_journal_container_release":FakeEngine,
             "audit_journal_root_inventory":FakeInventory}
    monkeypatch.setattr(r,"root_record",
        lambda path,mode:r.canon(before) if path==r.PRIVATE/"producer-before.json"
            else r.canon({"circuit_breaker":{"state":state["breaker"],"reason":state["reason"]}})
                 if path==r.STATE/"production-control-state.json" else r.canon(drift))
    monkeypatch.setattr(r,"systemd_properties",
                        lambda unit:{"ActiveState":"inactive","UnitFileState":"disabled"})
    got=r.governed_readmission(fake,fake_s,modules,None,given)
    assert got["expected_open_breaker"] is True
    assert got["producer_identities"]["jason-runtime"]["id"]=="cid-1"
    drift["problems"].append({"kind":"failed_system_unit","unit":"unrelated.service","state":"failed"})
    with pytest.raises(PermissionError,match="UNRELATED_PRODUCTION_DRIFT"):
        r.governed_readmission(fake,fake_s,modules,None,given)
    drift["problems"].pop()
    state["breaker"]="closed"
    with pytest.raises(PermissionError,match="UNEXPECTED_PRODUCTION_BREAKER"):
        r.governed_readmission(fake,fake_s,modules,None,given)
    state["breaker"]="open"
    live["jason-runtime"]["State"]["Running"]=False
    with pytest.raises(PermissionError,match="PRODUCER_IMAGE_OR_CONFIG_CHANGED"):
        r.governed_readmission(fake,fake_s,modules,None,given)


def test_every_preapproved_root_evidence_hash_has_full_sha256_length():
    """Regression: the first new recovery attempt mistakenly pinned 63-hex hashes."""
    r.validate_reference_pins()
    assert set(r.EXPECTED_PRIOR_SHA)=={"plan","journal","adoption","catalog","policy"}
    assert r.EXPECTED_PRIOR_SHA["adoption"] == (
        "2cbf005b417a42fef41d6623849a598dfecfbcf4822bc6105b2d9bec63722410"
    )
    assert r.EXPECTED_PRIOR_SHA["catalog"] == (
        "42de60cb250626f938228baf51b5e063f27a9e03cb257c4072fdeb467616a572"
    )
    assert all(len(v)==64 for v in r.EXPECTED_PRIOR_SHA.values())
    assert all(len(v)==64 for v in r.UNIT_BEFORE_SHA.values())
    assert all(len(v)==64 for v in r.UNIT_AFTER_SHA.values())
    for record in r.PREVIOUS_ATTEMPTS.values():
        assert all(len(value)==64 for value in record.values())


@pytest.mark.parametrize("field",["adoption","catalog","plan","journal","policy"])
def test_truncated_root_evidence_fingerprint_fails_before_any_read(monkeypatch,subject,field):
    other=dict(r.EXPECTED_PRIOR_SHA)
    other[field]=other[field][:-1]
    monkeypatch.setattr(r,"EXPECTED_PRIOR_SHA",other)
    called=[]
    subject["read_fn"]=lambda *args:called.append(args) or b"never_read"
    with pytest.raises(PermissionError,match="INVALID_REFERENCE_SHA256:original_evidence:"+field):
        verify(subject)
    assert called==[]


def test_non_hex_root_evidence_pin_denied(monkeypatch,subject):
    data=dict(r.EXPECTED_PRIOR_SHA)
    data["adoption"]=data["adoption"][:-1]+"x"
    monkeypatch.setattr(r,"EXPECTED_PRIOR_SHA",data)
    with pytest.raises(PermissionError,match="INVALID_REFERENCE_SHA256:original_evidence:adoption"):
        verify(subject)


def test_malformed_previous_approval_scope_pin_denied(monkeypatch,subject):
    records={k:dict(v) for k,v in r.PREVIOUS_ATTEMPTS.items()}
    key=next(iter(records))
    records[key]["transaction"]=records[key]["transaction"][1:]
    monkeypatch.setattr(r,"PREVIOUS_ATTEMPTS",records)
    with pytest.raises(PermissionError,match="INVALID_REFERENCE_SHA256:prior:transaction"):
        verify(subject)
