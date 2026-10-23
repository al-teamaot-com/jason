"""P0 #1974: installed root recovery files and policy stage before systemd.

These tests use isolated temporary files, never real systemd or root policy.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
INSTALLER_PATH = ROOT / "tools" / "install_release_host_reconciler.py"
OLD_SHA = "aca94fdc0bfa551162f6ea99d7ddded311786414"
NEW_SHA = "e8caace9791659adfd383a7ff148253c2ac5f424"
NEW_TIMER = "jason-openclaw-authority-full-integrity.timer"


def load_installer():
    spec = importlib.util.spec_from_file_location("tested_root_stage_installer", INSTALLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_only_installs_exact_rollback_files_before_reviewed_policy(
    monkeypatch, tmp_path,
):
    installer = load_installer()
    source = tmp_path / "releases" / NEW_SHA
    tools = source / "tools"
    tools.mkdir(parents=True)
    (tools / "protected_root_policy_migration.py").write_text("trusted migration helper")
    (tools / "release_host_reconcile_worker.py").write_text("trusted root worker")
    dest = tmp_path / "local-lib"
    spool = tmp_path / "host-reconcile"
    config = tmp_path / "root-control"
    config.mkdir()
    calls = []
    control = {
        "schema_version": "1.0",
        "last_known_good": {"manifest": {"revision": OLD_SHA}},
    }
    def stage(candidate, previous):
        assert (dest / "protected_root_policy_migration.py").read_text() == "trusted migration helper"
        assert (dest / "release_host_reconcile_worker.py").read_text() == "trusted root worker"
        calls.append((candidate, previous))
        return "STAGED_ALLOWED_ONLY"

    fake_migration = SimpleNamespace(
        ROOT=config,
        SHA=re.compile(r"[0-9a-f]{40}\Z"),
        _json=lambda data: json.loads(data),
        _root_only=lambda p: json.dumps(control).encode(),
        _source_policy=lambda sha: {
            "required_system_units": [NEW_TIMER] if sha == NEW_SHA else [],
        },
        stage_for_candidate=stage,
    )
    monkeypatch.setitem(sys.modules, "protected_root_policy_migration", fake_migration)
    monkeypatch.setattr(installer, "ROOT", source)
    monkeypatch.setattr(installer, "LIB", dest)
    monkeypatch.setattr(installer, "SPOOL", spool)
    monkeypatch.setattr(installer, "SYSTEMD", tmp_path / "systemd")
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(installer.os, "fchown", lambda *args: None)
    monkeypatch.setattr(installer.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(installer.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    def prohibit_systemd(*args, **kwargs):
        raise AssertionError("stage-only must not activate systemd or watchers")
    monkeypatch.setattr(installer.subprocess, "run", prohibit_systemd)
    monkeypatch.setattr(installer.subprocess, "check_output", prohibit_systemd)

    assert installer.main(stage_only=True) == 0
    assert calls == [(NEW_SHA, OLD_SHA)]
    assert not list(dest.glob(".jason-root-install-*"))
    assert not (tmp_path / "systemd").exists()


def test_stage_only_does_not_mutate_root_policy_for_no_new_required_timer(
    monkeypatch, tmp_path,
):
    installer = load_installer()
    candidate = tmp_path / "releases" / NEW_SHA
    (candidate / "tools").mkdir(parents=True)
    (candidate / "tools" / "protected_root_policy_migration.py").write_text("fixed helper")
    (candidate / "tools" / "release_host_reconcile_worker.py").write_text("fixed worker")
    checks = []
    fake = SimpleNamespace(
        ROOT=tmp_path,
        SHA=re.compile(r"[0-9a-f]{40}\Z"),
        _json=json.loads,
        _root_only=lambda p: json.dumps({
            "schema_version": "1.0",
            "last_known_good": {"manifest": {"revision": OLD_SHA}},
        }).encode(),
        _source_policy=lambda sha: {"required_system_units": []},
        stage_for_candidate=lambda *args: checks.append(args),
    )
    monkeypatch.setitem(sys.modules, "protected_root_policy_migration", fake)
    monkeypatch.setattr(installer, "ROOT", candidate)
    monkeypatch.setattr(installer, "LIB", tmp_path / "lib")
    monkeypatch.setattr(installer, "SPOOL", tmp_path / "spool")
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(installer.os, "fchown", lambda *args: None)
    monkeypatch.setattr(installer.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(installer.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(installer.subprocess, "run", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("systemd must not run")))
    assert installer.main(stage_only=True) == 0
    assert checks == []


def test_script_stage_precedes_any_candidate_specific_unit_write():
    script = (ROOT / "tools" / "reconcile_production_host_services.sh").read_text()
    assert script.index("install_release_host_reconciler.py\" --stage-only") < script.index(
        "step_start release_owned_unit_delta")
    assert script.index("install_release_host_reconciler.py\" --stage-only") < script.index(
        "step_start system_service_activation")
    assert script.index("step_start system_service_activation") < script.index(
        "step_start root_release_transition_install")
    src = (ROOT / "tools" / "protected_root_policy_migration.py").read_text()
    assert "STAGED_DELTA" in src and "stage_for_candidate" in src
    assert "prepare_rollback" in src and "complete_rollback" in src
