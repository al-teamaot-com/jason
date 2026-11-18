"""Isolated root-safe tests for exact live Ticket Core FLOCK ownership evidence."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_e_ticket_owner_readback as lockproof


def _fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(lockproof.os,"geteuid",lambda:0)
    lock=tmp_path/"autonomy-operational-work.sqlite3.owner.lock"
    lock.touch()
    lock.chmod(0o600)
    if os.geteuid()==0:
        os.chown(lock,1000,1000)
    else:
        assert lock.stat().st_uid==1000
    s=lock.stat()
    pid=550
    container=501
    line=(f"33: FLOCK  ADVISORY  WRITE {pid} "
          f"{os.major(s.st_dev):02x}:{os.minor(s.st_dev):02x}:{s.st_ino} 0 EOF")
    locks=tmp_path/"locks"
    locks.write_text(line+"\n")
    proc=tmp_path/"proc"
    (proc/str(pid)).mkdir(parents=True)
    (proc/str(pid)/"status").write_text(f"Name:\tpython\nPPid:\t{container}\n")
    return lock,locks,proc,line,pid,container


def _runner(cmd,**kw):
    assert cmd[:3]==["/usr/bin/docker","inspect","--format"]
    assert cmd[-1]==lockproof.CONTAINER
    return SimpleNamespace(returncode=0,
        stdout=("a"*64+"|501|true|healthy\n"),stderr="")


def test_exact_one_flock_owner_descends_from_external_core(tmp_path,monkeypatch):
    lock,locks,proc,_,pid,container=_fixture(tmp_path,monkeypatch)
    record=lockproof.inspect(runner=_runner,lock_path=lock,
                             locks_path=locks,proc_root=proc)
    assert record["unique_owner"] is True
    assert record["lock_owner_pid"]==pid
    assert record["container_init_pid"]==container
    assert record["exclusive_owner_count"]==1
    assert record["production_mutations"] is False


def test_duplicate_exclusive_inode_claims_fail_closed(tmp_path,monkeypatch):
    lock,locks,proc,line,_,_=_fixture(tmp_path,monkeypatch)
    locks.write_text(line+"\n"+line.replace(" 550 "," 551 ")+"\n")
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="EXCLUSIVE_LOCK_OWNER_NOT_UNIQUE"):
        lockproof.inspect(runner=_runner,lock_path=lock,locks_path=locks,proc_root=proc)


def test_no_lock_denied_even_when_container_running(tmp_path,monkeypatch):
    lock,locks,proc,_,_,_=_fixture(tmp_path,monkeypatch)
    locks.write_text("")
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="EXCLUSIVE_LOCK_OWNER_NOT_UNIQUE"):
        lockproof.inspect(runner=_runner,lock_path=lock,locks_path=locks,proc_root=proc)


def test_wrong_process_ancestry_denied(tmp_path,monkeypatch):
    lock,locks,proc,_,pid,_=_fixture(tmp_path,monkeypatch)
    (proc/str(pid)/"status").write_text("Name:\tpython\nPPid:\t1\n")
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="LOCK_OWNER_NOT_EXTERNAL_TICKET_CORE"):
        lockproof.inspect(runner=_runner,lock_path=lock,locks_path=locks,proc_root=proc)


def test_container_not_healthy_denied(tmp_path,monkeypatch):
    lock,locks,proc,_,_,_=_fixture(tmp_path,monkeypatch)
    def bad(cmd,**kw):
        return SimpleNamespace(returncode=0,
            stdout=("a"*64+"|501|true|unhealthy\n"),stderr="")
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="TICKET_CONTAINER_NOT_HEALTHY"):
        lockproof.inspect(runner=bad,lock_path=lock,locks_path=locks,proc_root=proc)


def test_symlink_lock_denied(tmp_path,monkeypatch):
    lock,locks,proc,_,_,_=_fixture(tmp_path,monkeypatch)
    link=tmp_path/"alias.lock"
    link.symlink_to(lock)
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="LOCK_PATH_UNTRUSTED"):
        lockproof.inspect(runner=_runner,lock_path=link,locks_path=locks,proc_root=proc)


def test_wrong_ownership_or_mode_denied(tmp_path,monkeypatch):
    lock,locks,proc,_,_,_=_fixture(tmp_path,monkeypatch)
    lock.chmod(0o666)
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="LOCK_FILE_UNTRUSTED"):
        lockproof.inspect(runner=_runner,lock_path=lock,locks_path=locks,proc_root=proc)


def test_kernel_lock_parser_requires_exact_inode_and_exclusive_flock(tmp_path,monkeypatch):
    lock,locks,proc,line,pid,_=_fixture(tmp_path,monkeypatch)
    assert lockproof.locks_for_inode(line,lock.stat())==[("FLOCK","WRITE",pid)]
    wrong=line.replace(" FLOCK "," POSIX ")
    assert lockproof.locks_for_inode(wrong,lock.stat())==[("POSIX","WRITE",pid)]
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="EXCLUSIVE_LOCK_OWNER_NOT_UNIQUE"):
        locks.write_text(wrong+"\n")
        lockproof.inspect(runner=_runner,lock_path=lock,locks_path=locks,proc_root=proc)


def test_unprivileged_read_denied_before_docker_or_proc(tmp_path,monkeypatch):
    monkeypatch.setattr(lockproof.os,"geteuid",lambda:1000)
    with pytest.raises(lockproof.TicketOwnerReadbackDenied,match="ROOT_ONLY"):
        lockproof.inspect(runner=lambda *a,**kw:pytest.fail("unexpected call"))


def test_no_host_or_provider_mutations_in_module():
    s=(Path(__file__).resolve().parents[2]/"tools/pmv4_e_ticket_owner_readback.py").read_text()
    for operation in ("docker restart","docker stop","subprocess.Popen(",
                      "os.system(","os.replace(","systemctl start",
                      "requests.post(","fcntl.flock("):
        assert operation not in s
