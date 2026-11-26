"""Minimal one-use catalog-unit drift recovery: offline fail-closed tests."""
from __future__ import annotations
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import stat
import pytest

from tools import catalog_recovery_units_reconcile_root as root

TEST_DIR=Path(__file__).resolve().parents[1]

def synthetic_packet(tmp_path,monkeypatch):
    stage=tmp_path/("catalog-units-reconcile-"+"a"*12)
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(root,"SOURCE_ROOT",tmp_path)
    monkeypatch.setattr(root,"ROOT_STAGE_UID",os.geteuid())
    script=(TEST_DIR/"catalog_recovery_units_reconcile_root.py").read_bytes()
    manifest={
        "schema_version":"1.0","action":root.ACTION,
        "source_sha":"a"*40,
        "rollback_sha":root.LKG,
        "catalog_source_sha":root.SOURCE_CATALOG,
        "freeze_sha256":root.FREEZE_SHA,
        "desired_sha256":root.DESIRED_SHA,
        "unit_sha256":root.UNITS,
        "root_source_sha256":root.digest(script),
        "one_use":True,
        "catalog_root_controls_removed":False,
        "systemd_units_removed":sorted(root.UNITS),
        "protected_service_restarts":False,
        "financial_scheduler_activation":False,
    }
    manifest["scope_sha256"]=root.digest(root.canonical(manifest))
    for name,body in ((root.SOURCE_FILE,script),
                      ("manifest.json",json.dumps(manifest).encode())):
        path=stage/name
        path.write_bytes(body)
        path.chmod(0o400)
    return stage,manifest

def test_only_four_authorized_catalog_units():
    assert len(root.UNITS)==4
    assert len(root.TIMERS)==2 and len(root.SERVICES)==2
    assert all(n.startswith("jason-catalog-") for n in root.UNITS)
    assert all(len(h)==64 for h in root.UNITS.values())
    assert root.DESIRED_SHA and root.FREEZE_SHA
    assert "jason-runtime" in root.PROTECTED
    assert "jason-mcp-pilot" in root.PROTECTED

def test_exact_source_and_scope_preflight(tmp_path,monkeypatch):
    packet,expected=synthetic_packet(tmp_path,monkeypatch)
    manifest,blobs=root.stage(packet)
    assert manifest==expected
    assert root.SOURCE_FILE in blobs
    assert "owner-proof.json" not in blobs

def test_owner_proof_required_before_mutation(tmp_path,monkeypatch):
    packet,_=synthetic_packet(tmp_path,monkeypatch)
    with pytest.raises(root.Denied,match="STAGE_SET_CHANGED"):
        root.stage(packet,require_proof=True)

def test_tamper_and_extra_source_refused(tmp_path,monkeypatch):
    packet,manifest=synthetic_packet(tmp_path,monkeypatch)
    extra=packet/"unrelated"
    extra.write_bytes(b"unexpected")
    with pytest.raises(root.Denied,match="STAGE_SET_CHANGED"):
        root.stage(packet)
    extra.unlink()
    p=packet/root.SOURCE_FILE
    p.chmod(0o600)
    with pytest.raises(root.Denied,match="STAGE_FILE_UNTRUSTED"):
        root.stage(packet)
    p.chmod(0o400)
    p.chmod(0o600);p.write_bytes(b"tampered");p.chmod(0o400)
    with pytest.raises(root.Denied,match="ACTION_NOT_EXACT"):
        root.stage(packet)

def test_cannot_expand_scope_to_protected_service(tmp_path,monkeypatch):
    packet,manifest=synthetic_packet(tmp_path,monkeypatch)
    manifest["systemd_units_removed"].append("jason-core.service")
    unsigned=dict(manifest);unsigned.pop("scope_sha256")
    manifest["scope_sha256"]=root.digest(root.canonical(unsigned))
    p=packet/"manifest.json"
    p.chmod(0o600);p.write_text(json.dumps(manifest));p.chmod(0o400)
    with pytest.raises(root.Denied,match="ACTION_NOT_EXACT"):
        root.stage(packet)

def test_malformed_checksum_and_freeze_denied(tmp_path,monkeypatch):
    packet,manifest=synthetic_packet(tmp_path,monkeypatch)
    manifest["freeze_sha256"]="0"*64
    unsigned=dict(manifest);unsigned.pop("scope_sha256")
    manifest["scope_sha256"]=root.digest(root.canonical(unsigned))
    p=packet/"manifest.json"
    p.chmod(0o600);p.write_text(json.dumps(manifest));p.chmod(0o400)
    with pytest.raises(root.Denied,match="ACTION_NOT_EXACT"):
        root.stage(packet)

def test_cannot_execute_nonroot(tmp_path,monkeypatch):
    monkeypatch.setattr(root.os,"geteuid",lambda:1000)
    with pytest.raises(root.Denied,match="ISOLATED_ROOT_REQUIRED"):
        root.execute(tmp_path)

def test_backup_and_remove_only_declared_unit_files(tmp_path,monkeypatch):
    unitdir=tmp_path/"units";unitdir.mkdir()
    ledger=tmp_path/"root-audit";ledger.mkdir()
    hashes={}
    for name in root.UNITS:
        b=("approved:"+name).encode()
        (unitdir/name).write_bytes(b)
        hashes[name]=root.digest(b)
    (unitdir/"jason-core.service").write_text("preserved")
    monkeypatch.setattr(root,"UNITS",hashes)
    monkeypatch.setattr(root,"ROOT_SYSTEMD",unitdir)
    monkeypatch.setattr(root,"ROOT_AUDIT",ledger)
    events=[]
    def fake_system(*args,**kwargs):
        events.append(args)
        if args[0]=="show":return "inactive"
        return ""
    monkeypatch.setattr(root,"system",fake_system)
    root.backup()
    root.remove_only_units()
    assert all(not (unitdir/n).exists() for n in hashes)
    assert (unitdir/"jason-core.service").read_text()=="preserved"
    assert sorted((ledger/"unit-backups").iterdir())==sorted(
        (ledger/"unit-backups"/name for name in hashes))
    assert sum(1 for e in events if e[:2]==("disable","--now"))==2
    root.revert()
    assert all(root.digest((unitdir/n).read_bytes())==hashes[n]
               for n in hashes)
    assert (unitdir/"jason-core.service").read_text()=="preserved"

def test_release_order_claim_proof_and_native_guard():
    source=(TEST_DIR/"catalog_recovery_units_reconcile_root.py").read_text()
    assert source.index("approval=signature(directory,manifest)") < source.index(
        'receipt(ROOT_AUDIT/"attempt.json",outcome)')
    assert source.index('receipt(ROOT_AUDIT/"attempt.json",outcome)') < source.index(
        "remove_only_units()", source.index("def execute"))
    assert source.index("check_clean_watchdog()",source.index("def execute")) < source.index(
        "native_revalidate()",source.index("def execute"))
    assert "os.system(" not in source and "shell=True" not in source
    assert "system(\"restart\"" not in source
    assert "system(\"stop\"" not in source
    assert "os.chmod(" not in source
    assert "system(\"disable\",\"--now\",n)" in source
    assert "CATALOG_PROMOTIONS_SUSPENDED" not in source

def test_owner_issuer_exact_entra_and_no_elevated_actions():
    source=(TEST_DIR/"catalog_recovery_units_reconcile_owner.py").read_text()
    assert "auth.jwt_owner(" in source
    assert "issue_exact_owner_release(" in source
    assert "verified_principal=principal" in source
    assert "APPROVE-EXACT-IDLE-CATALOG-RECOVERY-UNIT-RECONCILE" in source
    assert "systemctl" not in source
    assert "sudo" not in source

def test_oneuse_scope_does_not_change_catalog_root_or_financial():
    source=(TEST_DIR/"catalog_recovery_units_reconcile_root.py").read_text()
    assert '"catalog_root_controls_preserved":True' in source
    assert '"financial_component_activated":False' in source
    assert "CATALOG_STATE/\"transactions\"" in source
    assert "CATALOG_STATE/\"offers\"" in source
    assert "CATALOG_RECONCILE_ACTIVE_OR_PENDING_CATALOG_RELEASE" in source
    assert "DRIFT.stat().st_mtime>=since-2" in source
