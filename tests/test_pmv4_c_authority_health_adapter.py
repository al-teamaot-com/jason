from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import os
import subprocess

import pytest

from tools import pmv4_c_authority_health_adapter as h


@pytest.fixture
def state(tmp_path,monkeypatch):
    source=tmp_path/"legacy"
    shared=tmp_path/"shared"
    authority=tmp_path/"authority"
    for part in (source,shared,authority):
        part.mkdir(mode=0o700)
    paths={
        "authority":authority/"authority.sqlite3",
        "replay":source/"replay.sqlite3",
        "security_audit":source/"security-audit.sqlite3",
        "orchestration_audit":shared/"orchestration-events.sqlite3",
    }
    for p in paths.values():
        p.write_bytes(b"synthetic; no SQL")
        p.chmod(0o600)
    monkeypatch.setattr(h,"DATABASES",paths)
    monkeypatch.setattr(h,"ORCH",paths["orchestration_audit"])
    monkeypatch.setattr(h,"LEGACY_ORCH",source/"orchestration-events.sqlite3")
    monkeypatch.setattr(h,"AUTHORITY",paths["authority"])
    monkeypatch.setattr(h,"REPLAY",paths["replay"])
    monkeypatch.setattr(h,"SECURITY",paths["security_audit"])
    monkeypatch.setattr(h,"REGISTRY",source/"trusted-keys"/"registry.json")
    return paths,source,shared


def full_pass():
    return {
        "status":"pass","failures":[],
        "provider_contacted":False,
        "provider_credentials_used":False,
        "files":{k:{"path":str(v),"present":True,
                    "mode":"0o600","integrity":"ok"}
                 for k,v in h.DATABASES.items()},
        "trusted_key_registry":{"present":True,"mode":"0o600",
                                "active_records":2},
        "delegations":{"active":0,"expired_active_records":0},
        "backup_restore_proof":{
            "backup_integrity":"ok","restore_integrity":"ok",
            "backup_mode":"0o600","restore_mode":"0o600",
            "counts_match":True,
        },
    }


def test_exact_canonical_roots_no_legacy_alias_and_no_writes(state):
    paths,source,_=state
    before={p:(p.stat().st_ino,p.read_bytes()) for p in paths.values()}
    assert set(h.canonical_path_gate(uid=os.getuid()))==set(paths)
    assert before=={p:(p.stat().st_ino,p.read_bytes()) for p in paths.values()}
    legacy=source/"orchestration-events.sqlite3"
    legacy.write_bytes(b"stale alias")
    with pytest.raises(h.CanonicalHealthDenied,match="SPLIT_BRAIN"):
        h.canonical_path_gate(uid=os.getuid())


def test_symlink_and_weak_mode_are_rejected(state):
    paths,source,_=state
    f=paths["orchestration_audit"]
    f.chmod(0o644)
    with pytest.raises(h.CanonicalHealthDenied,match="CANONICAL_DB_NOT_TRUSTED"):
        h.canonical_path_gate(uid=os.getuid())
    f.unlink()
    f.symlink_to(paths["replay"])
    with pytest.raises(h.CanonicalHealthDenied,match="CANONICAL_PATH_NOT_TRUSTED"):
        h.canonical_path_gate(uid=os.getuid())


def test_full_evidence_requires_actual_new_path_and_integrity(state):
    report=full_pass()
    assert h.expected_full_report(report)
    report["files"]["orchestration_audit"]["path"]=str(h.LEGACY_ORCH)
    assert not h.expected_full_report(report)
    report=full_pass()
    report["files"]["orchestration_audit"]["integrity"]="not_run_in_frequent_check"
    assert not h.expected_full_report(report)


@pytest.mark.parametrize("patch",(
    ("status","fail"),("provider_contacted",True),
    ("provider_credentials_used",True),("failures",["timeout"]),
))
def test_full_fail_closed_for_nonpassing_or_provider_evidence(state,patch):
    report=full_pass()
    report[patch[0]]=patch[1]
    assert not h.expected_full_report(report)


def test_full_proof_backup_registry_delegation_validation(state):
    for field,value in (
        ("counts_match",False),("restore_integrity","bad"),
        ("backup_mode","0o644"),
    ):
        report=full_pass()
        report["backup_restore_proof"][field]=value
        assert not h.expected_full_report(report)
    report=full_pass();report["delegations"]["expired_active_records"]=1
    assert not h.expected_full_report(report)
    report=full_pass();report["trusted_key_registry"]["active_records"]=0
    assert not h.expected_full_report(report)


def test_fresh_full_scan_includes_canonical_flag_and_writes_only_report(
    state,tmp_path,
):
    paths,_,_=state
    calls=[]
    writes=[]
    def runner(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return subprocess.CompletedProcess(cmd,0,json.dumps(full_pass()),"")
    result=h.full_cycle(writer=lambda p,r:writes.append((p,r)),
                        runner=runner,uid=os.getuid(),
                        archive=tmp_path,output=tmp_path/"proof.json")
    assert result["status"]=="pass"
    assert len(calls)==1 and len(writes)==1
    cmd,kw=calls[0]
    assert cmd[cmd.index("--orchestration-audit")+1]==str(paths["orchestration_audit"])
    assert cmd[cmd.index("--backup-temp-root")+1].startswith(str(tmp_path))
    assert kw["timeout"]==5400 and kw["check"] is False
    assert writes[0][1]["snapshot_source_exit_code"]==0
    assert not (tmp_path/"proof.json").exists()


def test_full_invalid_or_timeout_never_writes_pass(state,tmp_path):
    for fake in (
        lambda cmd,**kw:subprocess.CompletedProcess(cmd,0,json.dumps({
            **full_pass(),"files":{**full_pass()["files"],
              "orchestration_audit":{"path":str(h.LEGACY_ORCH),
              "present":True,"mode":"0o600","integrity":"ok"}}}),""),
        lambda cmd,**kw:(_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd,kw["timeout"])
        ),
    ):
        writes=[]
        r=h.full_cycle(writer=lambda p,v:writes.append(v),
                       runner=fake,uid=os.getuid(),archive=tmp_path)
        assert r["status"]=="fail" and r["failures"]
        assert writes==[r]
        assert r["provider_contacted"] is False
        assert r["provider_credentials_used"] is False


def test_fast_health_uses_canonical_db_but_does_not_override_old_proof(
    state,tmp_path,
):
    observed=[]
    def check(**kwargs):
        observed.append(kwargs)
        # The LKG native fast verifier itself rejects full proofs whose
        # DB path still names the old legacy location.
        return {
            "status":"fail",
            "failures":["full_integrity_proof_missing_stale_or_invalid"],
            "provider_contacted":False,"provider_credentials_used":False,
        }
    writer=[]
    result=h.fast_cycle(checker=SimpleNamespace(check=check),
                        writer=lambda p,v:writer.append((p,v)),
                        output=tmp_path/"fast.json",full=tmp_path/"old.json",
                        uid=os.getuid())
    assert result["status"]=="fail"
    assert observed[0]["databases"]==h.DATABASES
    assert observed[0]["full_path"]==tmp_path/"old.json"
    assert len(writer)==1 and writer[0][1] is result


def test_preapproved_root_install_required_for_cli(monkeypatch):
    monkeypatch.setattr(h.os,"geteuid",lambda:1000)
    monkeypatch.setattr(h.sys,"argv",["health","--mode","fast"])
    with pytest.raises(h.CanonicalHealthDenied,match="OWNER_ROOT_INSTALL_REQUIRED"):
        h.main()
