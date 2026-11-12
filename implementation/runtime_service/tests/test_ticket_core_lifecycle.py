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


def test_main_owns_embedded_lock_but_external_never_claims(monkeypatch, tmp_path):
    calls = []
    @contextmanager
    def owner(path):
        calls.append(("claim", str(path)))
        yield
        calls.append(("release", str(path)))

    monkeypatch.setattr(main_module, "exclusive_ticket_worker_owner", owner)
    monkeypatch.setattr(main_module, "_run_hosted_runtime", lambda s: calls.append(("run", s.ticket_worker_hosting)))
    embedded = _settings(monkeypatch, tmp_path)
    monkeypatch.setattr(main_module.RuntimeSettings, "from_env", lambda: embedded)
    main_module.main()
    assert [row[0] for row in calls] == ["claim", "run", "release"]

    calls.clear()
    external = replace(embedded, ticket_worker_hosting="external")
    monkeypatch.setattr(main_module.RuntimeSettings, "from_env", lambda: external)
    main_module.main()
    assert calls == [("run", "external")]


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
    assert (tmp_path / "ticket-work.sqlite3.owner.lock").exists()
