"""Fail-closed synthetic root Stage E evidence; never touch production."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import stat

import pytest
from tools import pmv4_e_root_receipt_readback as e


@pytest.fixture
def evidence(tmp_path,monkeypatch):
    c=tmp_path/"stage-c.json"
    d=tmp_path/"stage-d.json"
    a=tmp_path/"shadow.json"
    audit=tmp_path/"v5-audit.jsonl"
    policy=tmp_path/"policy.json"
    c.write_text(json.dumps({
        "schema_version":"1.0","status":"postmigration_stage_c_accepted",
        "approval_id":"owner-mcp-8fb03f9faea44336b216456b5afcf663",
        "candidate_sha":e.STAGE_C_SHA,
        "scan_cycle_ids":["scan-"+"a"*32,"scan-"+"b"*32],
        "no_database_relocation":True,"mcp_restarts":0,
    }))
    d.write_text(json.dumps({
        "schema_version":"1.0",
        "status":"independent_runbook_read_service_accepted",
        "source_sha":e.STAGE_D_SHA,
        "scope_sha256":e.STAGE_D_SCOPE,
        "owner_approval_id":"pmv4-d-owner-"+"a"*32,
        "native_drift":"pass","provider_writes":0,
        "runtime_restarts":0,"mcp_restarts":0,
        "ticket_core_restarts":0,
        "production_freeze_unchanged":True,
    }))
    a.write_text(json.dumps({
        "schema_version":"1.0","service":"jason-pmv4-shadow",
        "state":"accepted","candidate_sha":e.A1_SHA,
        "rollback_sha":e.A1_PRIOR,"approval_id":e.A1_OWNER,
        "release_id":"release-"+e.A1_SHA[:16],
        "manifest_sha256":e.A1_MANIFEST,
        "scope_sha256":e.A1_SCOPE,
        "freeze_sha256":e.A1_FREEZE,
        "no_pmv3_or_provider_mutation":True,
    }))
    rows=[]
    prev="0"*64
    for i,event in enumerate((
        "begin","intent-create-root","created-file","root-stage-verified",
        "promoting","root-verified","committed",
    )):
        rec={
            "schema_version":"1.0","index":i,"event":event,
            "previous_sha256":prev,
            "source_sha":e.A1_SHA,
            "approval_id":e.A1_OWNER,
            "details":{"test_only":True},
            "occurred_at":"2026-11-18T14:17:00+00:00",
        }
        digest=sha256(e.canonical(rec)).hexdigest()
        rec["hash"]=digest
        rows.append(rec);prev=digest
    audit.write_bytes(b"".join(e.canonical(rec)+b"\n" for rec in rows))
    policy.write_text(json.dumps({
        "schema_version":"1.0",
        "required_user_units":sorted(e.LEGACY_REQUIRED_USER),
        "required_system_units":sorted(e.LEGACY_REQUIRED_SYSTEM),
        "allowed_system_units":["jason-runbook-management-read.service"],
    }))
    monkeypatch.setattr(e,"STAGE_C_PATH",c)
    monkeypatch.setattr(e,"STAGE_D_PATH",d)
    monkeypatch.setattr(e,"A1_RECEIPT",a)
    monkeypatch.setattr(e,"A1_AUDIT",audit)
    monkeypatch.setattr(e,"ACTIVE_POLICY",policy)
    monkeypatch.setattr(e,"ACTIVE_POLICY_SHA",sha256(policy.read_bytes()).hexdigest())
    original_lstat=Path.lstat
    def fake_lstat(path):
        original=original_lstat(path)
        if path in (c,d,a,audit,policy):
            return SimpleNamespace(st_mode=stat.S_IFREG|0o600,
                                   st_uid=0,st_gid=0,st_nlink=1,
                                   st_size=original.st_size)
        return original
    monkeypatch.setattr(Path,"lstat",fake_lstat)
    monkeypatch.setattr(e.os,"geteuid",lambda:0)
    return c,d,a,audit,policy


def test_exact_protected_root_evidence_is_not_retirement_authority(evidence):
    result=e.inspect()
    assert result["status"]=="pre_retirement_root_acceptance_verified"
    assert result["stage_c_root_acceptance_verified"] is True
    assert result["stage_d_root_acceptance_verified"] is True
    assert result["a1_root_acceptance_verified"] is True
    assert result["a1_root_audit_rows"]==7
    assert result["legacy_units_still_required"] is True
    assert result["replacement_controller_parity_verified"] is False
    assert result["retirement_authorized"] is False
    assert result["production_mutations"] is False


@pytest.mark.parametrize("field,value",[
    ("status","staged"),
    ("candidate_sha","f"*40),
    ("no_database_relocation",False),
    ("mcp_restarts",1),
    ("approval_id","owner-mcp-"+"f"*32),
    ("scan_cycle_ids",["scan-"+"a"*32,"scan-"+"a"*32]),
    ("scan_cycle_ids",[]),
])
def test_stage_c_wrong_or_ambiguous_accepted_evidence_denied(evidence,field,value):
    c=evidence[0]
    data=json.loads(c.read_bytes());data[field]=value
    c.write_text(json.dumps(data))
    with pytest.raises(e.StageERootEvidenceDenied,match="C_ROOT_ACCEPTANCE_NOT_EXACT"):
        e.inspect()


@pytest.mark.parametrize("field,value",[
    ("status","failed"),("source_sha","0"*40),
    ("scope_sha256","a"*64),("provider_writes",1),
    ("native_drift","skipped"),("runtime_restarts",1),
    ("ticket_core_restarts",1),("production_freeze_unchanged",False),
])
def test_stage_d_deployment_mutation_or_scope_drift_denied(evidence,field,value):
    p=evidence[1];x=json.loads(p.read_bytes());x[field]=value
    p.write_text(json.dumps(x))
    with pytest.raises(e.StageERootEvidenceDenied,match="D_ROOT_ACCEPTANCE_NOT_EXACT"):
        e.inspect()


@pytest.mark.parametrize("field,value",[
    ("state","started"),("candidate_sha","f"*40),
    ("rollback_sha","0"*40),("approval_id","owner-mcp-"+"f"*32),
    ("manifest_sha256","f"*64),("scope_sha256","f"*64),
    ("no_pmv3_or_provider_mutation",False),("freeze_sha256","f"*64),
])
def test_a1_acceptance_must_match_exact_prior_recovery(evidence,field,value):
    p=evidence[2];x=json.loads(p.read_bytes());x[field]=value
    p.write_text(json.dumps(x))
    with pytest.raises(e.StageERootEvidenceDenied,match="A1_ROOT_ACCEPTANCE_NOT_EXACT"):
        e.inspect()


def test_a1_audit_mutation_is_detected_and_cannot_claim_acceptance(evidence):
    p=evidence[3]
    rows=[json.loads(x) for x in p.read_bytes().splitlines()]
    rows[-1]["details"]={"tampered":True}
    p.write_bytes(b"".join(e.canonical(row)+b"\n" for row in rows))
    with pytest.raises(e.StageERootEvidenceDenied,
                       match="A1_ROOT_AUDIT_HASH_OR_SCOPE_CHANGED"):
        e.inspect()


@pytest.mark.parametrize("last",["rolled_back","requires_review"])
def test_a1_audit_failure_terminal_state_denied(evidence,last):
    p=evidence[3]
    rows=[json.loads(x) for x in p.read_bytes().splitlines()]
    lastrow=rows[-1]
    lastrow["event"]=last
    lastrow.pop("hash")
    lastrow["hash"]=sha256(e.canonical(lastrow)).hexdigest()
    p.write_bytes(b"".join(e.canonical(row)+b"\n" for row in rows))
    with pytest.raises(e.StageERootEvidenceDenied,match="A1_ROOT_AUDIT_NOT_COMMITTED"):
        e.inspect()


def test_live_protected_desired_state_hash_must_match_installed_stage_d(evidence):
    p=evidence[4]
    x=json.loads(p.read_bytes());x["allowed_system_units"].append("unguarded.service")
    p.write_text(json.dumps(x))
    with pytest.raises(e.StageERootEvidenceDenied,match="ROOT_DESIRED_STATE_NOT_REVIEWED"):
        e.inspect()


def test_root_evidence_must_not_be_asserted_by_unprivileged_runner(evidence,monkeypatch):
    monkeypatch.setattr(e.os,"geteuid",lambda:1000)
    with pytest.raises(e.StageERootEvidenceDenied,match="EXACT_ROOT_READ_ONLY_REQUIRED"):
        e.inspect()


def test_root_document_missing_or_symlink_not_trusted(evidence,monkeypatch):
    p=evidence[2]
    p.unlink()
    with pytest.raises(e.StageERootEvidenceDenied,match="PROTECTED_SOURCE_UNAVAILABLE"):
        e.inspect()


def test_no_production_mutation_authorized_by_root_readback_source():
    raw=Path(e.__file__).read_text()
    for forbidden in (
        'os.system(', 'subprocess.run(', 'docker compose up',
        'systemctl stop', 'systemctl disable', 'os.replace(',
        'os.unlink(', 'os.chmod(', 'os.chown(', 'authorization_granted": True',
    ):
        assert forbidden not in raw
    assert '"retirement_authorized":False' in raw
    assert '"production_mutations":False' in raw
