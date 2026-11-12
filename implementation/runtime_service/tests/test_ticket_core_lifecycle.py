"""PMv4 preproduction contract: one ticket worker independent of PM/HTTP."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import os
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

import pytest

from jason_runtime.composition import RuntimeSettings
from jason_runtime.ticket_worker_ownership import (
    TicketWorkerOwnershipError, exclusive_ticket_worker_owner,
    ticket_worker_lock_path,
)
from jason_runtime import main as main_module
from jason_runtime import ticket_worker_service as standalone


def _settings(monkeypatch, tmp_path, *, hosting="embedded", enabled=True):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("JASON_TICKET_WORKER_HOSTING", hosting)
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_DB", str(tmp_path / "ticket-work.sqlite3"))
    return RuntimeSettings.from_env()


def test_default_embedded_and_invalid_modes_fail_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("JASON_TICKET_WORKER_HOSTING", raising=False)
    settings = _settings(monkeypatch, tmp_path)
    # The real installed default is still "embedded" unless explicitly set.
    monkeypatch.delenv("JASON_TICKET_WORKER_HOSTING", raising=False)
    assert RuntimeSettings.from_env().ticket_worker_hosting == "embedded"
    assert settings.ticket_worker_hosting == "embedded"
    settings.validate()
    replace(settings, ticket_worker_hosting="external").validate()
    with pytest.raises(ValueError, match="JASON_TICKET_WORKER_HOSTING"):
        replace(settings, ticket_worker_hosting="auto").validate()


def test_lock_blocks_another_owner_even_if_both_modes_share_ledger(tmp_path):
    db = tmp_path / "ticket-work.sqlite3"
    lock = ticket_worker_lock_path(db)
    with exclusive_ticket_worker_owner(db) as actual:
        assert actual == lock
        assert lock.is_file()
        assert lock.stat().st_mode & 0o777 == 0o600
        with pytest.raises(TicketWorkerOwnershipError, match="ALREADY_OWNED"):
            with exclusive_ticket_worker_owner(db):
                pytest.fail("duplicate worker accepted")
    # The persistent lockfile must never be unlinked between owners.
    assert lock.exists()
    with exclusive_ticket_worker_owner(db):
        assert lock.exists()


def test_kernel_lock_blocks_separate_process(tmp_path):
    db = tmp_path / "ticket-work.sqlite3"
    script = (
        "from pathlib import Path\n"
        "from jason_runtime.ticket_worker_ownership import exclusive_ticket_worker_owner\n"
        "with exclusive_ticket_worker_owner(Path(" + repr(str(db)) + ")):\n"
        "    print('UNEXPECTED_SECOND_OWNER')\n"
    )
    with exclusive_ticket_worker_owner(db):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=12,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        )
        assert result.returncode != 0
        assert "TICKET_CORE_WORKER_ALREADY_OWNED" in result.stderr
        assert "UNEXPECTED_SECOND_OWNER" not in result.stdout


def test_untrusted_lockfile_and_invalid_paths_rejected(tmp_path):
    db = tmp_path / "ticket-work.sqlite3"
    lock = ticket_worker_lock_path(db)
    lock.symlink_to(tmp_path / "other")
    with pytest.raises(TicketWorkerOwnershipError, match="LOCK_UNAVAILABLE"):
        with exclusive_ticket_worker_owner(db):
            pass
    lock.unlink()
    lock.write_text("untrusted")
    lock.chmod(0o644)
    with pytest.raises(TicketWorkerOwnershipError, match="LOCK_FILE_UNTRUSTED"):
        with exclusive_ticket_worker_owner(db):
            pass
    with pytest.raises(TicketWorkerOwnershipError, match="DB_PATH_UNTRUSTED"):
        ticket_worker_lock_path(Path("relative.sqlite3"))


def test_http_parent_never_claims_dispatch_lock(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        main_module, "_run_hosted_runtime",
        lambda s: calls.append(("run", s.ticket_worker_hosting)),
    )
    embedded = _settings(monkeypatch, tmp_path)
    monkeypatch.setattr(main_module.RuntimeSettings, "from_env", lambda: embedded)
    main_module.main()
    assert calls == [("run", "embedded")]
    # Kernel flock ownership is inside the actual ticket child. No parent
    # lock may disappear while an orphaned child is still dispatching.
    assert not ticket_worker_lock_path(embedded.autonomy_worker_db).exists()

    calls.clear()
    external = replace(embedded, ticket_worker_hosting="external")
    monkeypatch.setattr(main_module.RuntimeSettings, "from_env", lambda: external)
    main_module.main()
    assert calls == [("run", "external")]




def test_dispatch_child_keeps_ownership_after_original_parent_exits(tmp_path):
    """Synthetic orphan regression: no split-brain if HTTP supervisor dies.

    A parent starts the ticket dispatch child then exits via os._exit(0).
    The child acquires the *same* kernel owner inode inside the real
    run_autonomy_maintenance_process entrypoint. Another would-be owner
    must fail closed until the child finishes its synthetic maintenance.
    """
    import signal
    import time

    db = tmp_path / "orphaned-worker-work.sqlite3"
    ready = tmp_path / "child-ready"
    stop = tmp_path / "child-stop"
    child_pid = tmp_path / "child-pid"
    script = r'''
import os, sys, time
from pathlib import Path
from types import SimpleNamespace
from jason_runtime import maintenance_process as service
db, ready, stop, child_pid = map(Path, sys.argv[1:])
parent_pid = os.fork()
if parent_pid:
    os._exit(0)
child_pid.write_text(str(os.getpid()))

def build_app(settings, *, maintenance_profile):
    assert maintenance_profile == "ticket_worker"
    assert (db.with_name(db.name + ".owner.lock")).is_file()
    ready.write_text("running")
    def tick():
        if stop.exists():
            raise SystemExit(0)
    return SimpleNamespace(maintenance=SimpleNamespace(tick=tick))
service.build_runtime_application = build_app
service.run_autonomy_maintenance_process(
    SimpleNamespace(autonomy_worker_db=db),
    maintenance_profile="ticket_worker", idle_sleep_seconds=0.05,
)
'''
    pythonpath = os.pathsep.join((
        str(Path(__file__).parents[1] / "src"),
        str(Path(__file__).parents[2]),
        str(Path(__file__).parents[2] / "cap-007/src"),
        str(Path(__file__).parents[2] / "connectors/openclaw/src"),
    ))
    parent = subprocess.Popen(
        [sys.executable, "-c", script, str(db), str(ready), str(stop),
         str(child_pid)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )
    orphan_pid = None
    try:
        assert parent.wait(timeout=6) == 0
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "synthetic dispatch child did not enter runtime"
        orphan_pid = int(child_pid.read_text())
        os.kill(orphan_pid, 0)
        assert parent.pid != orphan_pid
        with pytest.raises(TicketWorkerOwnershipError, match="ALREADY_OWNED"):
            with exclusive_ticket_worker_owner(db):
                pytest.fail("competing dispatch process obtained orphan lock")
        stop.touch()
        released = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with exclusive_ticket_worker_owner(db):
                    released = True
                    break
            except TicketWorkerOwnershipError:
                time.sleep(0.05)
        assert released, "dispatch owner was not safely released on child exit"
        assert ticket_worker_lock_path(db).is_file()
    finally:
        stop.touch(exist_ok=True)
        if orphan_pid is not None:
            try:
                os.kill(orphan_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_external_http_lifecycle_never_spawns_ticket_worker(monkeypatch, tmp_path):
    settings = _settings(monkeypatch, tmp_path, hosting="external")
    processes = []

    class FakeProcess:
        def __init__(self, *, name, **_kwargs):
            self.name = name
            processes.append(name)
        def start(self): pass
        def is_alive(self): return False
    monkeypatch.setattr(main_module, "get_context", lambda mode: SimpleNamespace(Process=FakeProcess))
    monkeypatch.setattr(main_module, "TicketWorkerSupervisor", lambda **kw: pytest.fail("HTTP started ticket supervisor"))
    monkeypatch.setattr(main_module, "build_runtime_application", lambda *a, **kw: "mock-app")
    monkeypatch.setattr(main_module, "serve", lambda app, **kwargs: None)
    main_module._run_hosted_runtime(settings)
    assert processes == ["jason-autonomy-auxiliary"]


def test_standalone_requires_explicit_external_mode_and_ticket_enabled(monkeypatch, tmp_path):
    for hosting, enabled in (("embedded", True), ("external", False)):
        settings = _settings(monkeypatch, tmp_path, hosting=hosting, enabled=enabled)
        with pytest.raises(RuntimeError, match="EXTERNAL_MODE_NOT_AUTHORIZED"):
            standalone.standalone_ticket_worker(settings)


def test_standalone_supervises_only_one_ticket_process_without_http(monkeypatch, tmp_path):
    settings = _settings(monkeypatch, tmp_path, hosting="external")
    spawned = []
    lifecycle = []
    class FakeProcess:
        def __init__(self, *, name, target, kwargs, **_unused):
            spawned.append((name, target.__name__, kwargs))
    class FakeSupervisor:
        def __init__(self, **_kwargs):
            lifecycle.append("supervisor_init")
        def start(self): lifecycle.append("start")
        def monitor_forever(self, stop): lifecycle.append("monitor")
        def stop(self): lifecycle.append("stop")
    monkeypatch.setattr(standalone, "get_context", lambda name: SimpleNamespace(Process=FakeProcess))
    monkeypatch.setattr(standalone, "TicketWorkerSupervisor", FakeSupervisor)
    monkeypatch.setattr(standalone, "read_worker_heartbeat", lambda path: None)
    standalone.standalone_ticket_worker(settings, stop=Event())
    assert lifecycle == ["supervisor_init", "start", "monitor", "stop"]
    # Factory is configured by the supervisor but no HTTP/server or PM starts.
    assert spawned == []
    # The fake supervisor never starts its child; therefore no ownership
    # lock is spuriously acquired by this external service parent.
    assert not (tmp_path / "ticket-work.sqlite3.owner.lock").exists()


def test_real_ticket_dispatch_child_keeps_exclusive_lock_across_entire_tick(
    monkeypatch, tmp_path,
):
    from jason_runtime import maintenance_process as maintenance
    settings = _settings(monkeypatch, tmp_path)
    checked = []

    class ExitWorker(BaseException):
        pass

    def tick():
        with pytest.raises(TicketWorkerOwnershipError, match="ALREADY_OWNED"):
            with exclusive_ticket_worker_owner(settings.autonomy_worker_db):
                pytest.fail("secondary dispatcher was admitted")
        checked.append("lock_held_during_provider_tick")
        raise ExitWorker

    monkeypatch.setattr(
        maintenance, "build_runtime_application",
        lambda *args, **kwargs: SimpleNamespace(
            maintenance=SimpleNamespace(tick=tick),
        ),
    )
    with pytest.raises(ExitWorker):
        maintenance.run_autonomy_maintenance_process(
            settings, maintenance_profile="ticket_worker",
        )
    assert checked == ["lock_held_during_provider_tick"]
    # Only process exit releases flock; its inode persists across takeover.
    lock_path = ticket_worker_lock_path(settings.autonomy_worker_db)
    assert lock_path.is_file()
    with exclusive_ticket_worker_owner(settings.autonomy_worker_db):
        assert lock_path.exists()


def test_second_child_rejected_before_runtime_construction(
    monkeypatch, tmp_path,
):
    from jason_runtime import maintenance_process as maintenance
    settings = _settings(monkeypatch, tmp_path)
    called = []
    monkeypatch.setattr(
        maintenance, "build_runtime_application",
        lambda *args, **kwargs: called.append("unexpected") or None,
    )
    with exclusive_ticket_worker_owner(settings.autonomy_worker_db):
        with pytest.raises(TicketWorkerOwnershipError, match="ALREADY_OWNED"):
            maintenance.run_autonomy_maintenance_process(
                settings, maintenance_profile="ticket_worker",
            )
    assert called == []
