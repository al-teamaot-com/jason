from __future__ import annotations

import fcntl
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'pmv3_worker_release_gate', ROOT / 'tools/pmv3_worker_release_gate.py'
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(module)


def test_admission_allows_idle_real_lock_without_modification(tmp_path):
    lock = tmp_path / 'transaction.lock'
    lock.touch(mode=0o600)
    before = lock.stat().st_mtime_ns
    assert module.admission_allowed(lock)
    assert lock.stat().st_mtime_ns == before


def test_admission_denies_held_lock_without_modifying_it(tmp_path):
    lock = tmp_path / 'transaction.lock'
    lock.touch(mode=0o600)
    with lock.open('rb') as hold:
        fcntl.flock(hold.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not module.admission_allowed(lock)
        fcntl.flock(hold.fileno(), fcntl.LOCK_UN)
    assert module.admission_allowed(lock)


def test_admission_denies_missing_symlink_and_world_writable_lock(tmp_path):
    lock = tmp_path / 'transaction.lock'
    assert not module.admission_allowed(lock)
    lock.touch(mode=0o600)
    symlink = tmp_path / 'untrusted-link.lock'
    symlink.symlink_to(lock)
    assert not module.admission_allowed(symlink)
    lock.chmod(0o666)
    assert not module.admission_allowed(lock)


def test_systemd_worker_uses_fail_closed_exec_condition():
    service = (ROOT / 'infrastructure/openclaw-operations/systemd/user'
               / 'jason-support-repair-worker.service').read_text()
    installer = (ROOT / 'tools/install_support_repair_host_worker.py').read_text()
    assert service.count('ExecCondition=') == 1
    assert ('ExecCondition=/usr/bin/python3 '
            '/home/al/.local/lib/jason/pmv3_worker_release_gate.py') in service
    assert "_copy(worker_release_gate, install_root / 'pmv3_worker_release_gate.py', 0o700)" in installer


def test_admission_rejects_fifo_without_blocking(tmp_path):
    fifo = tmp_path / 'transaction.pipe'
    os.mkfifo(fifo, mode=0o600)
    assert not module.admission_allowed(fifo)


def test_admission_denies_cross_process_exclusive_lock(tmp_path):
    # Real kernel-level flock cross-process test, never the live transaction mutex.
    import select
    import subprocess
    import sys

    path = tmp_path / 'production-transaction.lock'
    path.touch(mode=0o600)
    script = (
        'import fcntl, sys\n'
        'with open(sys.argv[1], "rb") as stream:\n'
        '    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)\n'
        '    print("LOCKED", flush=True)\n'
        '    sys.stdin.readline()\n'
    )
    worker = subprocess.Popen(
        [sys.executable, '-c', script, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        assert select.select([worker.stdout], [], [], 5)[0], 'lock-holder never signaled readiness'
        assert worker.stdout.readline().strip() == 'LOCKED'
        assert not module.admission_allowed(path)
    finally:
        if worker.stdin is not None:
            worker.stdin.write('release\n')
            worker.stdin.flush()
        worker.wait(timeout=5)
        if worker.stdout is not None:
            worker.stdout.close()
        if worker.stderr is not None:
            worker.stderr.close()
    assert worker.returncode == 0
    assert module.admission_allowed(path)


def test_bounded_retry_admits_after_real_exclusive_lock_is_released(tmp_path, monkeypatch):
    import threading
    lock=tmp_path/'transaction.lock'
    lock.touch(mode=0o600)
    monkeypatch.setattr(module,'INITIAL_BACKOFF_SECONDS',0.01)
    monkeypatch.setattr(module,'MAX_BACKOFF_SECONDS',0.02)
    with lock.open('rb') as owner:
        fcntl.flock(owner.fileno(),fcntl.LOCK_EX)
        timer=threading.Timer(0.06,lambda:fcntl.flock(owner.fileno(),fcntl.LOCK_UN))
        timer.start()
        try:
            assert module.admission_status(lock,retry_seconds=0.5)=='allowed'
        finally:
            timer.join()


def test_persistent_contention_uses_bounded_exponential_backoff(monkeypatch,tmp_path):
    clock=[0.0]; delays=[]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    def sleep(seconds):
        delays.append(seconds);clock[0]+=seconds
    monkeypatch.setattr(module.time,'sleep',sleep)
    monkeypatch.setattr(module,'probe',lambda *a:'busy')
    assert module.admission_status(tmp_path/'lock',retry_seconds=5)=='busy'
    assert delays==[0.25,0.5,1.0,2.0,1.25]
    assert sum(delays)==5.0


def test_invalid_lock_never_retries(tmp_path,monkeypatch):
    def unexpected_sleep(_): raise AssertionError('invalid lock must not be retried')
    monkeypatch.setattr(module.time,'sleep',unexpected_sleep)
    lock=tmp_path/'lock'
    assert module.admission_status(lock,retry_seconds=20)=='unavailable'
    lock.touch(mode=0o600);lock.chmod(0o666)
    assert module.admission_status(lock,retry_seconds=20)=='untrusted'
    lock.unlink();os.mkfifo(lock,0o600)
    assert module.admission_status(lock,retry_seconds=20)=='untrusted'


def test_owner_pause_appearing_during_contention_denies_admission(tmp_path,monkeypatch):
    lock=tmp_path/'lock'; lock.touch(mode=0o600)
    pause=tmp_path/'owner-pause.json'
    with lock.open('rb') as owner:
        fcntl.flock(owner.fileno(),fcntl.LOCK_EX)
        def sleep(_):
            pause.touch(mode=0o600)
            fcntl.flock(owner.fileno(),fcntl.LOCK_UN)
        monkeypatch.setattr(module.time,'sleep',sleep)
        assert module.admission_status(lock,retry_seconds=20,pause_path=pause)=='paused'


def test_lock_replaced_during_probe_is_denied(tmp_path,monkeypatch):
    lock=tmp_path/'lock';lock.touch(mode=0o600)
    real=module.fcntl.flock
    def replace(fd,flags):
        real(fd,flags)
        lock.rename(tmp_path/'old-lock')
        lock.touch(mode=0o600)
    monkeypatch.setattr(module.fcntl,'flock',replace)
    assert module.admission_status(lock,retry_seconds=20)=='untrusted'


def test_retry_budget_cannot_be_unbounded(tmp_path):
    import pytest
    for value in (-1,21,float('inf'),float('nan')):
        with pytest.raises(ValueError,match='retry budget'):
            module.admission_status(tmp_path/'lock',retry_seconds=value)
