"""Governed Stage C legacy mode repair. Only disposable synthetic files mutate."""
from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from tools import pmv4_c_atomic_root as root
from tools import pmv4_c_sqlite_family_handoff as handoff

LEGACY = {
    "governed-execution.sqlite3",
    "resolution-memory.sqlite3",
    "autonomy-targeted-wakes.sqlite3-wal",
    "autonomy-targeted-wakes.sqlite3-shm",
    "resolution-memory.sqlite3-wal",
    "resolution-memory.sqlite3-shm",
}


@pytest.fixture
def case(tmp_path, monkeypatch):
    source=tmp_path/"legacy"
    ticket=tmp_path/"ticket-core"
    shared=tmp_path/"shared"
    source.mkdir(mode=0o700)
    ticket.mkdir(mode=0o700)
    shared.mkdir(mode=0o700)
    source.chmod(0o700)
    ticket.chmod(0o700)
    shared.chmod(0o700)
    monkeypatch.setattr(root,"TICKET_SOURCE",source)
    monkeypatch.setattr(root,"TICKET_TARGET",ticket)
    monkeypatch.setattr(root,"SHARED_TARGET",shared)
    names=handoff.ALLOWED_TICKET+handoff.ALLOWED_SHARED
    docs={}
    for name in names:
        file=source/name
        file.write_bytes(("sensitive synthetic DB "+name).encode())
        file.chmod(0o644 if name in LEGACY else 0o600)
        docs[str(file)]=root._metadata(file)
    for name in (
        "autonomy-targeted-wakes.sqlite3-wal",
        "autonomy-targeted-wakes.sqlite3-shm",
        "resolution-memory.sqlite3-wal",
        "resolution-memory.sqlite3-shm",
        "orchestration-events.sqlite3-wal",
        "autonomy-operational-work.sqlite3.owner.lock",
    ):
        path=source/name
        path.write_bytes(("synthetic sidecar "+name).encode())
        path.chmod(0o644 if name in LEGACY else 0o600)
    return {"db_identities":docs},source,ticket,shared,os.getuid(),os.getgid()


def changes(case):
    plan,src,_,_,uid,gid=case
    return root._legacy_mode_changes(plan,uid=uid,gid=gid)


def mode(path):
    return stat.S_IMODE(path.lstat().st_mode)


def test_pre_auth_review_identifies_exact_six_without_writes(case):
    plan,src,_,_,uid,gid=case
    original={p.name:(p.stat().st_ino,p.stat().st_size,mode(p))
              for p in src.iterdir()}
    reviewed=changes(case)
    assert {Path(p).name for p in reviewed}==LEGACY
    assert all(v==0o644 for v in reviewed.values())
    assert original=={p.name:(p.stat().st_ino,p.stat().st_size,mode(p))
                     for p in src.iterdir()}


def test_signed_normalization_maintains_inode_and_allows_handoff(case):
    plan,src,ticket,shared,uid,gid=case
    before={p.name:(p.stat().st_ino,p.read_bytes(),mode(p))
            for p in src.iterdir()}
    changed={}
    root._repair_modes(plan,changed,uid=uid,gid=gid)
    assert {Path(p).name for p in changed}==LEGACY
    # The immutable pre-cutover plan retains its ORIGINAL 0644 mode values;
    # once normalized, only the explicit post-normalization check may pass.
    with pytest.raises(root.StageCRootDenied,match="C_LEGACY_MODE_MAIN_BASELINE_CHANGED"):
        changes(case)
    assert root._legacy_mode_changes(plan,uid=uid,gid=gid,baseline=False)=={}
    assert all(mode(p)==0o600 for p in src.iterdir())
    assert all(p.stat().st_ino==before[p.name][0] and
               p.read_bytes()==before[p.name][1]
               for p in src.iterdir())
    ticket_plan=handoff.preview(src,ticket,kind="ticket",uid=uid)
    shared_plan=handoff.preview(src,shared,kind="shared",uid=uid)
    assert ticket_plan.entries and shared_plan.entries
    assert all(entry.mode==0o600 for entry in (
        ticket_plan.entries+shared_plan.entries))
    root._restore_modes(changed,target=False,uid=uid,gid=gid)
    assert changes(case)==changed
    assert all(mode(p)==before[p.name][2] and
               p.stat().st_ino==before[p.name][0]
               for p in src.iterdir())


@pytest.mark.parametrize("extra",(
    "orchestration-events.sqlite3-wal",
    "autonomy-operational-work.sqlite3.owner.lock",
    "playbook-autonomy.sqlite3-shm",
))
def test_unreviewed_insecure_sidecar_denied_before_approval(case, extra):
    plan,src,_,_,uid,gid=case
    target=src/extra
    target.write_bytes(b"synthetic")
    target.chmod(0o644)
    with pytest.raises(root.StageCRootDenied,match="C_LEGACY_MODE_SIDECAR_UNREVIEWED"):
        changes(case)


def test_symlinked_sidecar_denied(case):
    plan,src,_,_,uid,gid=case
    target=src/"autonomy-targeted-wakes.sqlite3-wal"
    target.unlink()
    target.symlink_to(src/"autonomy-targeted-wakes.sqlite3")
    with pytest.raises(root.StageCRootDenied,match="C_LEGACY_MODE_SIDECAR_UNTRUSTED"):
        changes(case)


def test_hardlink_on_sidecar_denied(case):
    plan,src,_,_,uid,gid=case
    target=src/"resolution-memory.sqlite3-wal"
    os.link(target,src/"other-hardlink")
    with pytest.raises(root.StageCRootDenied,match="C_LEGACY_MODE_SIDECAR_UNTRUSTED"):
        changes(case)


def test_unreviewed_world_writable_is_always_denied(case):
    plan,src,_,_,uid,gid=case
    target=src/"autonomy-targeted-wakes.sqlite3-wal"
    target.chmod(0o666)
    with pytest.raises(root.StageCRootDenied,match="C_LEGACY_MODE_SIDECAR_UNREVIEWED"):
        changes(case)


def test_file_inodes_and_contents_survive_partial_permission_failure(
    case, monkeypatch,
):
    plan,src,_,_,uid,gid=case
    before={p.name:(p.stat().st_ino,p.read_bytes(),mode(p))
            for p in src.iterdir()}
    actual=root._exact_mode_change
    attempts=[]
    def fail_second(path,**kwargs):
        attempts.append(path.name)
        if len(attempts)==2:
            raise root.StageCRootDenied("SIMULATED_FCHMOD_DENIAL")
        return actual(path,**kwargs)
    changed={}
    monkeypatch.setattr(root,"_exact_mode_change",fail_second)
    with pytest.raises(root.StageCRootDenied,match="SIMULATED_FCHMOD_DENIAL"):
        root._repair_modes(plan,changed,uid=uid,gid=gid)
    assert len(changed)==2
    monkeypatch.setattr(root,"_exact_mode_change",actual)
    root._restore_modes(changed,target=False,uid=uid,gid=gid)
    assert before=={p.name:(p.stat().st_ino,p.read_bytes(),mode(p))
                    for p in src.iterdir()}


def test_optional_wal_sidecars_may_be_absent_after_stop(case):
    plan,src,_,_,uid,gid=case
    for suffix in ("-wal","-shm"):
        (src/("autonomy-targeted-wakes.sqlite3"+suffix)).unlink()
    actual=changes(case)
    assert set(Path(p).name for p in actual)==(
        LEGACY-{
            "autonomy-targeted-wakes.sqlite3-wal",
            "autonomy-targeted-wakes.sqlite3-shm",
        })


def test_exact_main_db_mode_must_still_match_signed_plan(case):
    plan,src,_,_,uid,gid=case
    path=src/"governed-execution.sqlite3"
    path.chmod(0o600)
    with pytest.raises(root.StageCRootDenied,match="C_LEGACY_MODE_MAIN_BASELINE_CHANGED"):
        changes(case)


def test_no_production_file_operations_in_source_review():
    source=Path(root.__file__).read_text()
    assert "LEGACY_SIDECAR_MODE_REPAIR" in source
    assert "C_LEGACY_MODE_SIDECAR_UNREVIEWED" in source
    assert "PMV4_C_EXACT_LEGACY_SQLITE_MODE_PREFLIGHT=PASS" in source
    assert "C_LEGACY_MODE_REPAIR_POSTCHECK_FAILED" in source
    assert "legacy_mode_normalized" in source
    assert "os.O_NOFOLLOW" in source
