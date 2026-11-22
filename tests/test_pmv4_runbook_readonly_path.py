"""Pure read-only PMv4 D registry access, no live schema migration."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import sqlite3

import pytest

from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from tools.pmv4_runbook_lifecycle_acceptance import sample
from jason_mcp import json_playbook_admin


def historical_two_table_db(tmp_path):
    db=tmp_path/"json-playbooks.sqlite3"
    con=sqlite3.connect(str(db))
    con.executescript("""
    CREATE TABLE json_playbook_registry_meta(
        singleton INTEGER PRIMARY KEY, generation INTEGER NOT NULL);
    INSERT INTO json_playbook_registry_meta VALUES(1,0);
    CREATE TABLE json_playbooks(
        playbook_id TEXT, version TEXT, state TEXT, fingerprint TEXT,
        canonical_json TEXT, created_by TEXT, created_at TEXT,
        activated_by TEXT, activated_at TEXT, retired_at TEXT);
    """)
    con.close()
    db.chmod(0o600)
    return db


def schema_tables(db):
    con=sqlite3.connect("file:"+db.as_posix()+"?mode=ro",uri=True)
    try:
        return {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def state(db):
    info=db.stat()
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_mode


def test_historical_two_table_read_is_genuinely_nonmutating(tmp_path):
    db=historical_two_table_db(tmp_path)
    before=state(db)
    tables=schema_tables(db)
    assert "json_playbook_lifecycle_events" not in tables
    store=SQLitePlaybookRegistry(db,read_only=True)
    try:
        assert store.generation()==0
        assert store.list_all()==()
        assert store.active_snapshot()==(0,())
        assert store._connection.execute("PRAGMA query_only").fetchone()[0]==1
        with pytest.raises(RuntimeError,match="READONLY_MUTATION_FORBIDDEN"):
            store.stage(sample(),actor="synthetic-technician")
    finally:
        store.close()
    assert state(db)==before
    assert schema_tables(db)==tables
    assert not db.with_name(db.name+"-wal").exists()


def test_read_nonempty_registry_without_changing_generation(tmp_path):
    db=tmp_path/"json-playbooks.sqlite3"
    writer=SQLitePlaybookRegistry(db)
    try:
        staged=writer.stage(sample(),actor="synthetic-technician")
        writer.activate(staged.document.playbook_id,staged.document.version,
                        actor="synthetic-owner",
                        expected_fingerprint=staged.document.fingerprint)
        assert writer.generation()==2
    finally:writer.close()
    before=state(db)
    ro=SQLitePlaybookRegistry(db,read_only=True)
    try:
        assert ro.generation()==2
        items=ro.list_all()
        assert len(items)==1
        assert items[0].state=="active"
        assert items[0].document.fingerprint==staged.document.fingerprint
        for action in (
            lambda:ro.stage(sample("1.1.0"),actor="test"),
            lambda:ro.activate(staged.document.playbook_id,staged.document.version,
                               actor="test"),
            lambda:ro.retire(staged.document.playbook_id,actor="test"),
        ):
            with pytest.raises(RuntimeError,match="READONLY_MUTATION_FORBIDDEN"):
                action()
    finally:ro.close()
    assert state(db)==before


def test_nonexistent_registry_never_created_by_read(tmp_path):
    db=tmp_path/"does-not-exist"/"json-playbooks.sqlite3"
    with pytest.raises(RuntimeError,match="READONLY_REGISTRY_UNTRUSTED"):
        SQLitePlaybookRegistry(db,read_only=True)
    assert not db.exists()
    assert not db.parent.exists()


@pytest.mark.parametrize("case",["symlink","world_writable","relative","uri","fragment","wrong_uid"])
def test_untrusted_readonly_paths_fail_closed(tmp_path,monkeypatch,case):
    db=historical_two_table_db(tmp_path)
    if case=="symlink":
        alias=tmp_path/"alias.sqlite3"
        alias.symlink_to(db)
        db=alias
    elif case=="world_writable":
        db.chmod(0o666)
    elif case=="relative":
        db=Path("json-playbooks.sqlite3")
    elif case=="uri":
        db.rename(tmp_path/"json-playbooks?.sqlite3")
        db=tmp_path/"json-playbooks?.sqlite3"
    elif case=="fragment":
        db.rename(tmp_path/"json-playbooks#.sqlite3")
        db=tmp_path/"json-playbooks#.sqlite3"
    elif case=="wrong_uid":
        original_uid=os.geteuid()
        monkeypatch.setattr(os,"geteuid",lambda:original_uid+1)
    with pytest.raises(RuntimeError,match="READONLY_REGISTRY_UNTRUSTED"):
        SQLitePlaybookRegistry(db,read_only=True)


def test_mcp_admin_defaults_writer_but_supports_explicit_readonly(tmp_path,monkeypatch):
    db=historical_two_table_db(tmp_path)
    monkeypatch.setenv("JASON_JSON_PLAYBOOK_DB",str(db))
    before=state(db)
    reader=json_playbook_admin.open_registry(read_only=True)
    try:
        assert reader.generation()==0
        assert reader.list_all()==()
    finally:reader.close()
    assert before==state(db)
    assert "json_playbook_lifecycle_events" not in schema_tables(db)


def test_mcp_list_handler_invokes_strict_readonly_without_changing_writes():
    source=(Path(__file__).parents[1]/
        "implementation/mcp_service/src/jason_mcp/server.py")
    tree=ast.parse(source.read_text())
    funcs={node.name:node for node in tree.body if isinstance(node,ast.FunctionDef)}
    read_calls=[node for node in ast.walk(funcs["list_json_playbooks"])
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                and node.func.id=="open_json_playbook_registry"]
    assert len(read_calls)==1
    assert len(read_calls[0].keywords)==1
    assert read_calls[0].keywords[0].arg=="read_only"
    assert isinstance(read_calls[0].keywords[0].value,ast.Constant)
    assert read_calls[0].keywords[0].value.value is True
    for mutation in ("stage_json_playbook","activate_json_playbook","retire_json_playbook"):
        calls=[node for node in ast.walk(funcs[mutation])
               if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
               and node.func.id=="open_json_playbook_registry"]
        assert len(calls)==1
        assert not calls[0].keywords


def test_readonly_sqlite_connection_denies_raw_write(tmp_path):
    db=historical_two_table_db(tmp_path)
    store=SQLitePlaybookRegistry(db,read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            store._connection.execute("UPDATE json_playbook_registry_meta SET generation=9")
    finally:store.close()
    assert sqlite3.connect(str(db)).execute(
        "SELECT generation FROM json_playbook_registry_meta").fetchone()==(0,)
