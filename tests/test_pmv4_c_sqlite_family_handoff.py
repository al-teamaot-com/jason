"""Nonproduction, inode-preserving Stage C SQLite-family relocation tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from tools import pmv4_c_sqlite_family_handoff as handoff


@pytest.fixture
def layout(tmp_path):
    source=tmp_path/"legacy"; target=tmp_path/"ticket-core"
    source.mkdir(mode=0o700);target.mkdir(mode=0o700)
    source.chmod(0o700);target.chmod(0o700)
    uid=os.geteuid()
    for name in handoff.ALLOWED_TICKET:
        p=source/name
        p.write_bytes(("synthetic "+name).encode())
        p.chmod(0o600)
    for suffix in ("-wal","-shm",".owner.lock"):
        p=source/("autonomy-operational-work.sqlite3"+suffix)
        p.write_bytes(("synthetic "+suffix).encode())
        p.chmod(0o600)
    return source,target,uid


def preview(layout, *, kind="ticket", active=True):
    source,target,uid=layout
    return handoff.preview(source,target,kind=kind,uid=uid,
                           require_quiescence=active)


def journal_for(plan):
    root=plan.source.parent/"root-evidence"
    root.mkdir(mode=0o700,exist_ok=True)
    root.chmod(0o700)
    return root/("pmv4-c-"+plan.digest+".jsonl")


def move(plan,journal):
    return handoff.move_under_signed_root(
        plan,journal=journal,
        signed_host_fence=lambda:None,
        verify_all_producers_stopped=lambda:None,
        journal_owner_uid=os.geteuid(),
    )


def rollback(plan,journal):
    return handoff.rollback_before_new_writer(
        plan,journal=journal,
        signed_host_fence=lambda:None,
        verify_no_new_writer_or_provider_action=lambda:None,
        journal_owner_uid=os.geteuid(),
    )


def test_source_only_preview_has_stable_exact_source_inode_budget(layout):
    source,target,uid=layout
    plan=preview(layout)
    assert len(plan.entries)==7
    assert plan.uid==uid
    assert handoff.MIN_UID==1000
    assert plan.bytes_not_copied==sum((source/x.name).stat().st_size
                                      for x in plan.entries)
    assert len(plan.digest)==64
    assert sorted(target.iterdir())==[]
    assert all((source/x.name).stat().st_ino==x.inode for x in plan.entries)
    assert all(x.mode==0o600 for x in plan.entries)


def test_atomic_same_fs_inode_relocation_and_pre_activation_recovery(layout):
    source,target,uid=layout
    plan=preview(layout)
    journal=journal_for(plan)
    report=move(plan,journal)
    assert report["status"]=="files_moved_not_activated"
    assert report["owner_approval_issued"] is False
    assert report["external_worker_activated"] is False
    assert report["bytes_not_copied"]==plan.bytes_not_copied
    assert journal.is_file()
    rows=handoff.read_exact_journal(plan,journal)
    assert rows[0]["event"]=="begin"
    assert rows[-1]["event"]=="all_files_moved"
    assert all(x["index"]==i for i,x in enumerate(rows))
    for x in plan.entries:
        assert not (source/x.name).exists()
        assert (target/x.name).stat().st_ino==x.inode
    result=rollback(plan,journal)
    assert result["status"]=="original_inodes_restored_without_new_writer"
    assert handoff.read_exact_journal(plan,journal)[-1]["event"]=="rollback_complete"
    for x in plan.entries:
        assert (source/x.name).stat().st_ino==x.inode
        assert not (target/x.name).exists()
    assert sorted(target.iterdir())==[]
    with pytest.raises(handoff.HandoffDenied,match="ROLLBACK_ALREADY_CLOSED"):
        rollback(plan,journal)


def test_real_sqlite_db_records_survive_no_byte_copy(tmp_path):
    source=tmp_path/"old";target=tmp_path/"new"
    source.mkdir(mode=0o700);target.mkdir(mode=0o700)
    source.chmod(0o700);target.chmod(0o700)
    uid=os.geteuid()
    for name in handoff.ALLOWED_TICKET:
        db=source/name
        con=sqlite3.connect(db)
        con.execute("CREATE TABLE if not exists sample (id INTEGER PRIMARY KEY, label TEXT)")
        con.execute("INSERT INTO sample(label) VALUES (?)",("known-count",))
        con.commit();con.close()
        db.chmod(0o600)
    plan=handoff.preview(source,target,kind="ticket",uid=uid)
    inode=(source/handoff.ALLOWED_TICKET[0]).stat().st_ino
    move(plan,journal_for(plan))
    assert (target/handoff.ALLOWED_TICKET[0]).stat().st_ino==inode
    con=sqlite3.connect(f"file:{target/handoff.ALLOWED_TICKET[0]}?mode=ro",uri=True)
    try:
        assert con.execute("SELECT label FROM sample").fetchone()[0]=="known-count"
    finally:
        con.close()
    # Re-open may update SQLite metadata; real rollback requires no new writer.
    # No rollback of this newly accessed target is attempted in this test.


def test_file_open_by_process_must_refuse_quiescence(layout):
    source,target,uid=layout
    item=source/handoff.ALLOWED_TICKET[0]
    with open(item,"rb") as active:
        assert active.read(1)
        with pytest.raises(handoff.HandoffDenied,match="ACTIVE_SQLITE_OWNER"):
            preview(layout)
    preview(layout)


def test_foreign_path_and_file_permissions_denied(layout):
    source,target,uid=layout
    bad=source/handoff.ALLOWED_TICKET[0]
    bad.chmod(0o644)
    with pytest.raises(handoff.HandoffDenied,match="UNTRUSTED_FILE"):
        preview(layout,active=False)
    bad.chmod(0o600)
    target.chmod(0o755)
    with pytest.raises(handoff.HandoffDenied,match="UNTRUSTED_ROOT"):
        preview(layout,active=False)
    target.chmod(0o700)
    alias=source.parent/"alias-root"
    alias.symlink_to(source,target_is_directory=True)
    with pytest.raises(handoff.HandoffDenied,match="SYMLINKED_ROOT"):
        handoff.preview(alias,target,kind="ticket",uid=uid,
                        require_quiescence=False)


def test_unknown_extra_target_and_duplicate_file_denied(layout):
    source,target,uid=layout
    p=target/handoff.ALLOWED_TICKET[0]
    p.write_text("foreign")
    with pytest.raises(handoff.HandoffDenied,match="TARGET_NOT_EMPTY"):
        preview(layout,active=False)
    p.unlink()
    p=source/(handoff.ALLOWED_TICKET[0]+"-wal")
    p.unlink()
    p.symlink_to(source/handoff.ALLOWED_TICKET[0])
    with pytest.raises(handoff.HandoffDenied,match="UNTRUSTED_FILE"):
        preview(layout,active=False)


def test_quiescence_command_fails_closed_if_lsof_unavailable(layout):
    source,target,uid=layout
    with pytest.raises(handoff.HandoffDenied,match="LSOF_UNAVAILABLE"):
        handoff.inspect_quiescence((source/handoff.ALLOWED_TICKET[0],),
                                  lsof="/does-not-exist/lsof")


def test_move_denied_if_signed_gate_refuses_without_mutation(layout):
    plan=preview(layout)
    def deny():
        raise handoff.HandoffDenied("SYNTHETIC_SIGNED_HOST_DENIAL")
    with pytest.raises(handoff.HandoffDenied,match="SIGNED_HOST_DENIAL"):
        handoff.move_under_signed_root(
            plan,journal=journal_for(plan),
            signed_host_fence=deny,
            verify_all_producers_stopped=lambda:None,
            journal_owner_uid=os.geteuid(),
        )
    assert sorted(plan.destination.iterdir())==[]
    assert all((plan.source/x.name).exists() for x in plan.entries)


def test_crash_between_inode_renames_recovers_original(layout,monkeypatch):
    plan=preview(layout)
    journal=journal_for(plan)
    real_rename=handoff._rename_noreplace
    attempts=[0]
    def interrupted(source,target):
        attempts[0]+=1
        if attempts[0]==2:
            raise OSError("simulated power loss between renames")
        return real_rename(source,target)
    monkeypatch.setattr(handoff,"_rename_noreplace",interrupted)
    with pytest.raises(OSError,match="simulated power loss"):
        move(plan,journal)
    monkeypatch.setattr(handoff,"_rename_noreplace",real_rename)
    moved=[x for x in plan.entries if (plan.destination/x.name).exists()]
    assert len(moved)==1
    rows=handoff.read_exact_journal(plan,journal)
    assert rows[-1]["event"]=="intent"
    rollback(plan,journal)
    assert all((plan.source/x.name).stat().st_ino==x.inode for x in plan.entries)
    assert all(not (plan.destination/x.name).exists() for x in plan.entries)


def test_tampered_journal_is_never_accepted_for_recovery(layout):
    plan=preview(layout)
    journal=journal_for(plan)
    move(plan,journal)
    rows=journal.read_bytes().splitlines()
    fake=json.loads(rows[-1])
    fake["event"]="rolled_back"
    rows[-1]=handoff._canon(fake)
    journal.write_bytes(b"\n".join(rows)+b"\n")
    journal.chmod(0o600)
    with pytest.raises(handoff.HandoffDenied,match="JOURNAL_CHAIN_INVALID"):
        rollback(plan,journal)
    assert all((plan.destination/x.name).exists() for x in plan.entries)


def test_recovery_refuses_different_inode_or_modified_destination(layout):
    plan=preview(layout)
    journal=journal_for(plan)
    move(plan,journal)
    changed=plan.destination/plan.entries[0].name
    changed.write_bytes(b"not original bytes")
    with pytest.raises(handoff.HandoffDenied,match="RECOVERY_INODE_CHANGED"):
        rollback(plan,journal)


def test_recovery_refuses_any_new_provider_or_worker_writer(layout):
    plan=preview(layout)
    journal=journal_for(plan)
    move(plan,journal)
    def reject():
        raise handoff.HandoffDenied("PRODUCTION_NEW_WRITER_CANNOT_RESTORE_STALE_STATE")
    with pytest.raises(handoff.HandoffDenied,match="NEW_WRITER"):
        handoff.rollback_before_new_writer(
            plan,journal=journal,signed_host_fence=lambda:None,
            verify_no_new_writer_or_provider_action=reject,
            journal_owner_uid=os.geteuid())
    assert all((plan.destination/x.name).exists() for x in plan.entries)


def test_native_rename_noreplace_never_clobbers_foreign_target(layout):
    source,target,uid=layout
    first=source/handoff.ALLOWED_TICKET[0]
    other=target/first.name
    other.write_bytes(b"foreign payload")
    old_inode=other.stat().st_ino
    with pytest.raises(FileExistsError):
        handoff._rename_noreplace(first,other)
    assert first.exists()
    assert other.stat().st_ino==old_inode
    assert other.read_bytes()==b"foreign payload"


def test_journal_cannot_be_inside_mutable_worker_state(layout):
    plan=preview(layout)
    journal=plan.destination/("pmv4-c-"+plan.digest+".jsonl")
    with pytest.raises(handoff.HandoffDenied,match="JOURNAL_NOT_EXACT_ROOT"):
        move(plan,journal)
    assert all((plan.source/x.name).exists() for x in plan.entries)
    assert not journal.exists()


def test_stage_c_requires_exact_control_owner(layout):
    plan=preview(layout)
    journal=journal_for(plan)
    different_uid=os.geteuid()+1
    with pytest.raises(handoff.HandoffDenied,match="ROOT_AUDIT_AUTHORITY_REQUIRED"):
        handoff.move_under_signed_root(
            plan,journal=journal,
            signed_host_fence=lambda:None,
            verify_all_producers_stopped=lambda:None,
            journal_owner_uid=different_uid)
    assert not journal.exists()


def test_signed_manifest_uid_is_part_of_exact_identity(layout):
    source,target,uid=layout
    plan=preview(layout,active=False)
    wrong=handoff._fingerprint(source,target,plan.kind,uid+1,plan.entries)
    assert wrong!=plan.digest
    assert plan.uid==uid
