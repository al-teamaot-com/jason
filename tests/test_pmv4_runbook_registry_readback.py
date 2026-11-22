"""PMv4 Stage D independent readback never writes the source registry."""
from pathlib import Path
import os
import sqlite3

import pytest

from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from tools import pmv4_runbook_registry_readback as gate
from tools.pmv4_runbook_lifecycle_acceptance import sample


@pytest.fixture
def existing(tmp_path):
    db=tmp_path/"json-playbooks.sqlite3"
    s=SQLitePlaybookRegistry(db)
    try: assert s.generation()==0
    finally:s.close()
    return db


def test_readback_fully_ready_but_not_independent_service(existing):
    before=existing.stat()
    result=gate.readback(existing)
    assert result["lifecycle_schema_ready"] is True
    assert result["runbook_independent_management_operational"] is False
    assert result["generation"]==0
    assert result["audit_events"]==0
    assert result["production_mutations"] is False
    after=existing.stat()
    assert (before.st_ino,before.st_mtime_ns,before.st_size)==(
        after.st_ino,after.st_mtime_ns,after.st_size)


def test_readback_existing_old_schema_detects_missing_audit(tmp_path):
    p=tmp_path/"json-playbooks.sqlite3"
    c=sqlite3.connect(str(p))
    c.executescript("""
    CREATE TABLE json_playbook_registry_meta(singleton INTEGER,generation INTEGER);
    INSERT INTO json_playbook_registry_meta VALUES(1,0);
    CREATE TABLE json_playbooks (
        playbook_id TEXT,version TEXT,state TEXT,fingerprint TEXT,
        canonical_json TEXT,created_by TEXT,created_at TEXT,
        activated_by TEXT,activated_at TEXT,retired_at TEXT);
    """)
    c.close();p.chmod(0o600)
    result=gate.readback(p)
    assert result["lifecycle_schema_ready"] is False
    assert result["required_tables_missing"]==["json_playbook_lifecycle_events"]
    assert result["production_mutations"] is False


def test_copy_proves_lifecycle_and_original_unchanged(existing):
    before=existing.stat()
    result=gate.isolated_upgrade_acceptance(existing)
    assert result["status"]=="isolated_copy_accepted"
    assert result["copied_lifecycle_operations"]==3
    assert result["copied_new_generation"]==3
    assert result["live_registry_unchanged"] is True
    assert result["production_mutations"] is False
    after=existing.stat()
    assert (before.st_ino,before.st_mtime_ns,before.st_size)==(
        after.st_ino,after.st_mtime_ns,after.st_size)
    assert gate.readback(existing)["generation"]==0


def test_copy_accepts_missing_events_table_without_live_migration(tmp_path):
    p=tmp_path/"old.sqlite3"
    c=sqlite3.connect(str(p))
    c.executescript("""
    CREATE TABLE json_playbook_registry_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        generation INTEGER NOT NULL);
    INSERT INTO json_playbook_registry_meta VALUES(1,0);
    CREATE TABLE json_playbooks (
        playbook_id TEXT NOT NULL,version TEXT NOT NULL,state TEXT NOT NULL,
        fingerprint TEXT NOT NULL,canonical_json TEXT NOT NULL,
        created_by TEXT NOT NULL,created_at TEXT NOT NULL,
        activated_by TEXT,activated_at TEXT,retired_at TEXT,
        PRIMARY KEY(playbook_id,version));
    """)
    c.close();p.chmod(0o600)
    assert gate.readback(p)["lifecycle_schema_ready"] is False
    result=gate.isolated_upgrade_acceptance(p)
    assert result["live_registry_unchanged"] is True
    assert gate.readback(p)["lifecycle_schema_ready"] is False


def test_production_path_cannot_be_supplied_by_caller(existing):
    with pytest.raises(gate.RunbookReadbackDenied,match="PATH_NOT_PINNED"):
        gate.readback(existing,production=True)


def test_symlink_denied(existing):
    alias=existing.parent/"alias.sqlite3"
    alias.symlink_to(existing)
    with pytest.raises(gate.RunbookReadbackDenied,match="PATH_UNTRUSTED"):
        gate.readback(alias)


def test_corrupt_generation_denied(existing):
    conn=sqlite3.connect(str(existing))
    conn.execute("UPDATE json_playbook_registry_meta SET generation=-1 WHERE singleton=1")
    conn.commit();conn.close()
    with pytest.raises(gate.RunbookReadbackDenied,match="GENERATION_UNTRUSTED"):
        gate.readback(existing)


def test_fingerprint_audit_generation_mismatch_denied(existing):
    s=SQLitePlaybookRegistry(existing)
    try:
        s.stage(sample(),actor="synthetic-technician")
        assert s.generation()==1
    finally:s.close()
    conn=sqlite3.connect(str(existing))
    conn.execute("DELETE FROM json_playbook_lifecycle_events")
    conn.commit();conn.close()
    with pytest.raises(gate.RunbookReadbackDenied,match="AUDIT_GENERATION_MISMATCH"):
        gate.readback(existing)


def test_unsafe_world_writable_db_denied(existing):
    existing.chmod(0o666)
    with pytest.raises(gate.RunbookReadbackDenied,match="METADATA_UNTRUSTED"):
        gate.readback(existing)


def test_readback_no_sensitive_fields(existing):
    output=gate.readback(existing)
    assert "canonical_json" not in output
    assert "owner_oid" not in output
    assert "provider_secret" not in output
    assert "playbook_id" not in output
