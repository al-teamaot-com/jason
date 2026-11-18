"""Disposable Stage C SQLite handoff tests. Never connect to live providers."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

from tools import pmv4_ticket_core_ledger_snapshot as snap


@pytest.fixture
def ledgers(tmp_path):
    old=tmp_path/"legacy"
    new=tmp_path/"ticket-core"
    old.mkdir(mode=0o700)
    new.mkdir(mode=0o700)
    db=old/"autonomy-operational-work.sqlite3"
    con=sqlite3.connect(db)
    con.execute("CREATE TABLE autonomy_ticket_scan_cycle("
                "scanned_at TEXT, provider_items INTEGER,"
                "duplicate_items INTEGER, evaluated INTEGER)")
    con.execute("CREATE TABLE autonomy_ticket_worker_heartbeat("
                "singleton_id INTEGER PRIMARY KEY,state TEXT)")
    for i in range(3):
        con.execute("INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?)",
                    (f"2026-11-17T12:0{i}:00Z",152,0,152))
    con.execute("INSERT INTO autonomy_ticket_worker_heartbeat VALUES (1,'idle')")
    con.commit()
    con.close()
    db.chmod(0o600)
    lock=old/(db.name+".owner.lock")
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    return db,new/db.name


def copy(db,dest):
    return snap.snapshot_quiesced_ledger(
        db,dest,expected_uid=os.geteuid(),
        expected_directory_uid=os.geteuid(),
    )


def test_consistent_disposable_snapshot_preserves_original_and_lock(ledgers):
    source,dest=ledgers
    source_inode=source.stat().st_ino
    source_lock_inode=Path(str(source)+".owner.lock").stat().st_ino
    result=copy(source,dest)
    assert result["status"]=="consistent_quiesced_snapshot"
    assert result["scan_cycle_count"]==3
    assert result["latest_scan"]=="2026-11-17T12:02:00Z"
    assert result["source_retained"] is True
    assert result["external_worker_started"] is False
    assert result["provider_actions"] is False
    assert source.stat().st_ino==source_inode
    assert Path(str(source)+".owner.lock").stat().st_ino==source_lock_inode
    assert dest.is_file() and Path(str(dest)+".owner.lock").is_file()
    assert source.stat().st_ino!=dest.stat().st_ino
    assert source_lock_inode!=Path(str(dest)+".owner.lock").stat().st_ino
    assert stat.S_IMODE(dest.stat().st_mode)==0o600
    assert stat.S_IMODE(Path(str(dest)+".owner.lock").stat().st_mode)==0o600
    assert snap._facts(source)==snap._facts(dest)
    with pytest.raises(snap.LedgerSnapshotDenied,match="ALREADY_PRESENT"):
        copy(source,dest)


def test_wal_only_committed_transaction_is_carried_into_target(ledgers):
    source,dest=ledgers
    con=sqlite3.connect(source)
    try:
        assert con.execute("PRAGMA journal_mode=WAL").fetchone()[0]=="wal"
        con.execute("PRAGMA wal_autocheckpoint=0")
        con.execute(
            "INSERT INTO autonomy_ticket_scan_cycle VALUES (?,?,?,?)",
            ("2026-11-17T12:03:00Z",153,0,153))
        con.commit()
        assert Path(str(source)+"-wal").exists()
        result=copy(source,dest)
        assert result["scan_cycle_count"]==4
        assert snap._facts(dest)==snap._facts(source)
    finally:
        con.close()


def test_active_legacy_worker_owner_blocks_copy(ledgers):
    source,dest=ledgers
    lock=Path(str(source)+".owner.lock")
    program=(
        "import os,fcntl,sys,time;"
        "f=os.open(sys.argv[1],os.O_RDWR);"
        "fcntl.flock(f,fcntl.LOCK_EX);"
        "print('LOCKED',flush=True);"
        "time.sleep(8)"
    )
    proc=subprocess.Popen(
        [sys.executable,"-c",program,str(lock)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert proc.stdout.readline().strip()=="LOCKED"
        with pytest.raises(
            snap.LedgerSnapshotDenied,match="WORKER_STILL_OWNS_LEDGER"
        ):
            copy(source,dest)
        assert not dest.exists()
    finally:
        proc.terminate()
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def test_unknown_existing_target_or_lock_fails_closed(ledgers):
    source,dest=ledgers
    dest.write_bytes(b"not a proper SQLite ledger")
    dest.chmod(0o600)
    with pytest.raises(snap.LedgerSnapshotDenied,match="ALREADY_PRESENT"):
        copy(source,dest)
    dest.unlink()
    new_lock=Path(str(dest)+".owner.lock")
    new_lock.write_text("unknown")
    new_lock.chmod(0o600)
    with pytest.raises(snap.LedgerSnapshotDenied,match="ALREADY_PRESENT"):
        copy(source,dest)


def test_symlinked_source_or_target_root_refused(ledgers):
    source,dest=ledgers
    alias=source.parent/"alias.sqlite3"
    alias.symlink_to(source)
    with pytest.raises(snap.LedgerSnapshotDenied,match="UNTRUSTED_PATH"):
        copy(alias,dest)
    new_alias=dest.parent.parent/"alias-ticket-core"
    new_alias.symlink_to(dest.parent,target_is_directory=True)
    with pytest.raises(snap.LedgerSnapshotDenied,match="DESTINATION_NOT_ISOLATED"):
        copy(source,new_alias/dest.name)


def test_world_readable_source_and_untrusted_target_mode_fail(ledgers):
    source,dest=ledgers
    source.chmod(0o644)
    with pytest.raises(snap.LedgerSnapshotDenied,match="UNTRUSTED_FILE"):
        copy(source,dest)
    source.chmod(0o600)
    dest.parent.chmod(0o755)
    with pytest.raises(snap.LedgerSnapshotDenied,match="DESTINATION_ROOT_UNTRUSTED"):
        copy(source,dest)


def test_target_must_be_on_same_filesystem_and_no_alt_ledger(ledgers,monkeypatch):
    source,dest=ledgers
    orig=snap._regular
    def different_device(path,uid):
        item=orig(path,uid)
        if path==source:
            return type("Stat",(),dict(
                st_dev=item.st_dev+1,st_ino=item.st_ino,st_uid=item.st_uid
            ))()
        return item
    monkeypatch.setattr(snap,"_regular",different_device)
    with pytest.raises(snap.LedgerSnapshotDenied,match="DB_LOCK_DIFFERENT_FS"):
        copy(source,dest)


def test_schema_missing_refuses_copy(ledgers):
    source,dest=ledgers
    con=sqlite3.connect(source)
    con.execute("DROP TABLE autonomy_ticket_worker_heartbeat")
    con.commit()
    con.close()
    with pytest.raises(snap.LedgerSnapshotDenied,match="SCHEMA_MISSING"):
        copy(source,dest)
    assert not dest.exists()


def test_precommit_disk_error_removes_only_new_staged_files(ledgers,monkeypatch):
    source,dest=ledgers
    prior_source_inode=source.stat().st_ino
    prior_lock_inode=Path(str(source)+".owner.lock").stat().st_ino
    def disk_denied(_src,_dest):
        raise OSError("simulated target atomic install failure")
    monkeypatch.setattr(snap.os,"replace",disk_denied)
    with pytest.raises(OSError,match="simulated target"):
        copy(source,dest)
    assert not dest.exists()
    assert not Path(str(dest)+".owner.lock").exists()
    assert list(dest.parent.iterdir())==[]
    assert source.stat().st_ino==prior_source_inode
    assert Path(str(source)+".owner.lock").stat().st_ino==prior_lock_inode


def test_detects_source_wal_change_during_copy(ledgers,monkeypatch):
    source,dest=ledgers
    original=snap._journal_markers
    times=[0]
    def changing_markers(path):
        times[0]+=1
        seen=original(path)
        if times[0]>=2:
            return ((1,2,3,4),seen[1])
        return seen
    monkeypatch.setattr(snap,"_journal_markers",changing_markers)
    with pytest.raises(snap.LedgerSnapshotDenied,match="CHANGED_DURING_BACKUP"):
        copy(source,dest)
    assert not dest.exists()
    assert not Path(str(dest)+".owner.lock").exists()


def test_unusual_sqlite_table_names_do_not_form_executable_sql(ledgers):
    source,dest=ledgers
    con=sqlite3.connect(source)
    con.execute('CREATE TABLE "autonomy_odd"" name" (id INTEGER)')
    con.execute('INSERT INTO "autonomy_odd"" name" VALUES (1)')
    con.commit()
    con.close()
    result=copy(source,dest)
    assert result["status"]=="consistent_quiesced_snapshot"
    assert snap._facts(dest)["counts"]['autonomy_odd" name']==1


def test_default_destination_contract_matches_nonroot_worker_uid():
    import inspect
    signature=inspect.signature(snap.snapshot_quiesced_ledger)
    assert signature.parameters["expected_uid"].default==1000
    assert signature.parameters["expected_directory_uid"].default==1000
