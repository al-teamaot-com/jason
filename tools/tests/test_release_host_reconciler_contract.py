from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_worker_is_bounded_to_exact_sha_and_live_mcp():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(
        encoding="utf-8"
    )
    assert 'r"^[0-9a-f]{40}$"' in text
    assert "live MCP revision does not match requested host release" in text
    assert 'Path("/opt/jason/current")' in text
    assert '_candidate_reconcile_script(source_revision)' in text
    assert 'git' in text and 'show' in text
    assert 'candidate host reconciliation script depends on developer checkout' in text
    assert "reconcile_production_host_services.sh" in text
    assert "safe.directory={REPO}" in text
    assert '"fetch", "--no-tags", "origin", "main"' not in text
    assert "Network/source freshness belongs to the unprivileged Release Manager" in text
    assert "merge-base" in text
    assert "--is-ancestor" in text


def test_root_installer_owns_privileged_boundary_and_path_unit():
    installer = (
        ROOT / "tools" / "install_release_host_reconciler.py"
    ).read_text(encoding="utf-8")
    service = (
        ROOT
        / "infrastructure"
        / "openclaw-operations"
        / "systemd"
        / "jason-release-host-reconcile.service"
    ).read_text(encoding="utf-8")
    path = (
        ROOT
        / "infrastructure"
        / "openclaw-operations"
        / "systemd"
        / "jason-release-host-reconcile.path"
    ).read_text(encoding="utf-8")

    assert "root privileges are required" in installer
    assert "/usr/local/lib/jason" in installer
    assert "enable" in installer and "--now" in installer
    assert "User=root" in service
    assert "release_host_reconcile_worker.py" in service
    assert "DirectoryNotEmpty=" in path
    assert "host-reconcile/requests" in path


def test_privileged_boundary_contains_no_sudo_or_docker_privilege_escalation():
    files = [
        ROOT / "tools" / "release_host_reconcile_worker.py",
        ROOT / "tools" / "install_release_host_reconciler.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "sudo " not in combined
    assert "--privileged" not in combined
    assert "/var/run/docker.sock" not in combined


def test_root_worker_scopes_git_safe_directory_to_reconcile_subprocess():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(
        encoding="utf-8"
    )
    assert '"GIT_CONFIG_COUNT": "1"' in text
    assert '"GIT_CONFIG_KEY_0": "safe.directory"' in text
    assert '"GIT_CONFIG_VALUE_0": str(REPO)' in text
    assert "env=script_env" in text
    assert "git config --system" not in text
    assert "git config --global" not in text


def test_root_worker_normalizes_immutable_release_traversal_without_global_umask_change():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(
        encoding="utf-8"
    )
    assert 'Path("/opt/jason/releases") / source_revision' in text
    assert "os.chmod(release_dir, 0o755)" in text
    assert "previous_umask = os.umask(0o022)" in text
    assert "os.umask(previous_umask)" in text
    assert "immutable release directory is not safely traversable" in text


def test_host_reconcile_script_explicitly_sets_release_root_mode():
    text = (
        ROOT / "tools" / "reconcile_production_host_services.sh"
    ).read_text(encoding="utf-8")
    assert 'chown root:root "$RELEASE_DIR"' in text
    assert 'chmod 0755 "$RELEASE_DIR"' in text


def test_root_reconciler_uses_managed_engineering_source_not_developer_checkout() -> None:
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(encoding="utf-8")
    assert 'REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")' in text
    assert '/home/al/projects/jason' not in text


def test_root_worker_materializes_candidate_reconcile_script_and_requires_contract_markers():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(encoding="utf-8")
    assert 'CANDIDATE_SCRIPTS = SPOOL / "candidate-scripts"' in text
    assert 'DEVELOPER_CHECKOUT_DEPENDENCY=ABSENT' in text
    assert 'HOST_RECONCILIATION_SCRIPT_SOURCE_REVISION=' in text
    assert 'candidate host reconciliation contract is incomplete' in text


def test_root_worker_has_bounded_outer_timeout_and_preserves_timeout_evidence():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(encoding="utf-8")
    assert "HOST_RECONCILE_TIMEOUT_SECONDS = 360" in text
    assert "except subprocess.TimeoutExpired as exc" in text
    assert "candidate host reconciliation script exceeded" in text
    assert "detail[-3000:]" in text


def test_root_worker_tolerates_only_historical_post_success_documentation_failure():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(encoding="utf-8")
    assert "_historical_post_success_documentation_failure" in text
    assert "JASON_USER_WORKER_RECONCILIATION=PASS" in text
    assert "JASON_ROOT_HOST_RECONCILER_RECONCILIATION=PASS" in text
    assert "JASON_HOST_SERVICE_RECONCILIATION=PASS" in text
    assert "ERROR: production succeeded but documentation reconciliation publication failed" in text
    assert "HISTORICAL_POST_SUCCESS_DOCUMENTATION_FAILURE=DEFERRED_TO_RELEASE_MANAGER" in text


def test_root_worker_unit_timeout_exceeds_script_deadline_and_processes_one_request():
    import importlib.util
    from unittest.mock import patch
    worker = ROOT / 'tools' / 'release_host_reconcile_worker.py'
    text = worker.read_text(encoding='utf-8')
    unit = (ROOT / 'infrastructure/openclaw-operations/systemd/jason-release-host-reconcile.service').read_text(encoding='utf-8')
    path = (ROOT / 'infrastructure/openclaw-operations/systemd/jason-release-host-reconcile.path').read_text(encoding='utf-8')
    assert 'MAX_REQUESTS_PER_RUN = 1' in text
    assert 'HOST_RECONCILE_TIMEOUT_SECONDS = 360' in text
    assert 'TimeoutStartSec=480' in unit
    assert 'DirectoryNotEmpty=' in path


def test_root_worker_leaves_remaining_requests_for_next_path_activation(tmp_path):
    import importlib.util
    from unittest.mock import patch
    source = ROOT / 'tools' / 'release_host_reconcile_worker.py'
    spec = importlib.util.spec_from_file_location('host_reconcile_timeout_contract',source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    requests=tmp_path/'requests';results=tmp_path/'results'
    requests.mkdir()
    for name in ('first.json','second.json'):
        (requests/name).write_text('{}')
    processed=[]
    def process_one(path):
        processed.append(path.name)
        path.unlink()
    with patch.object(worker,'REQUESTS',requests), patch.object(worker,'RESULTS',results), patch.object(worker,'_process',process_one), patch.object(worker.os,'geteuid',return_value=0):
        assert worker.main()==0
        assert len(processed)==1
        assert len(list(requests.glob('*.json')))==1
        assert worker.main()==0
        assert len(processed)==2
        assert list(requests.glob('*.json'))==[]



def test_root_installer_stages_helper_and_worker_atomically(tmp_path, monkeypatch):
    import importlib.util
    import os
    source = ROOT / "tools" / "install_release_host_reconciler.py"
    spec = importlib.util.spec_from_file_location("jason_root_installer_atomic", source)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    orig = tmp_path / "staged.py"
    orig.write_text("new helper")
    target = tmp_path / "root.py"
    target.write_text("old helper")
    monkeypatch.setattr(installer.os, "fchown", lambda *args: None)
    installer.install(orig, target, 0o755)
    assert target.read_text() == "new helper"
    assert (target.stat().st_mode & 0o777) == 0o755
    assert not list(tmp_path.glob(".jason-root-install-*"))
    code = source.read_text()
    assert "os.replace(temporary, destination)" in code
    assert code.index('ROOT / "tools" / "protected_root_policy_migration.py"') < code.index(
        'ROOT / "tools" / "release_host_reconcile_worker.py"')



def test_pinned_legacy_health_timeout_does_not_skip_mandatory_health_verification():
    """A single pinned line change; this must not become general script rewriting."""
    from pathlib import Path
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text()
    assert 'LEGACY_LKG_SHA = "aca94fdc0bfa551162f6ea99d7ddded311786414"' in text
    assert 'LEGACY_HOST_SCRIPT_SHA256 = "d8bf41dfe824b8eb01ae192386907a6657f09c245aa246306597a1162c7d1707"' in text
    assert 'LEGACY_HEALTH_FROM = ' in text and '240s systemctl start' in text
    assert 'LEGACY_HEALTH_TO = ' in text and '300s systemctl start' in text
    assert "hashlib.sha256(body.encode(\"utf-8\")).hexdigest()" in text
    assert "body.count(LEGACY_HEALTH_FROM) != 1" in text
    assert "body = body.replace(LEGACY_HEALTH_FROM, LEGACY_HEALTH_TO)" in text
    assert "HOST_RECONCILE_LEGACY_ROLLBACK_TIMEOUT_SECONDS = 410" in text
    assert "if source_revision == LEGACY_LKG_SHA" in text
    # The native Release Manager's independent 420-second absolute deadline
    # and root systemd unit's 480-second deadline must still bound the work.
    manager = (ROOT / "tools" / "release_manager_host_runner.py").read_text()
    systemd = (ROOT / "infrastructure/openclaw-operations/systemd/jason-release-host-reconcile.service").read_text()
    assert "timeout_seconds: float = 420.0" in manager
    assert "TimeoutStartSec=480" in systemd



def test_committed_root_policy_remains_authoritative_for_subsequent_releases(tmp_path, monkeypatch):
    import importlib.util
    import hashlib
    import json
    from types import SimpleNamespace
    worker_source = ROOT / "tools" / "release_host_reconcile_worker.py"
    spec = importlib.util.spec_from_file_location("jason_root_ledger_reader", worker_source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    old = "a" * 40
    committed = "b" * 40
    next_revision = "c" * 40
    active = tmp_path / "active.json"
    policy = tmp_path / "policy.json"
    control = tmp_path / "production-control-state.json"
    raw = b'{"schema_version":"1.0","required_system_units":["jason-known.timer"]}\n'
    policy.write_bytes(raw)
    receipt = {
        "schema_version": "1.0", "candidate_sha": committed,
        "rollback_sha": old, "phase": "applied",
        "applied_sha256": hashlib.sha256(raw).hexdigest(),
    }
    active.write_text(json.dumps(receipt))
    state = {
        "schema_version": "1.0",
        "circuit_breaker": {"state": "closed"},
        "last_known_good": {"manifest": {"revision": committed, "complete": True}},
    }
    control.write_text(json.dumps(state))
    helper = SimpleNamespace(
        ROOT=tmp_path, ACTIVE=active, POLICY=policy,
        _json=lambda b: json.loads(b),
        _root_only=lambda p: p.read_bytes(),
        digest=lambda b: hashlib.sha256(b).hexdigest(),
        restore_for_baseline=lambda _: (_ for _ in ()).throw(AssertionError("unexpected rollback")),
    )
    monkeypatch.setattr(worker, "_trusted_root_policy_helper", lambda: helper)
    monkeypatch.setattr(worker, "_verified_migration_ancestor",
                        lambda ancestor, desc: ancestor == committed and
                        desc in (committed, next_revision))
    assert worker._restore_root_policy_for_target(next_revision) == "PREVIOUS_MIGRATION_LKG_VERIFIED"
    # Keep root policy unchanged: this is proof of an already-committed
    # migration, NOT implicit authorization for a new policy write.
    assert policy.read_bytes() == raw
    policy.write_bytes(b"unauthorized addition\n")
    try:
        worker._restore_root_policy_for_target(next_revision)
    except worker.HostReconcileError as exc:
        assert "committed root policy differs" in str(exc)
    else:
        raise AssertionError("tampered committed policy must fail closed")
    policy.write_bytes(raw)
    state["circuit_breaker"]["state"] = "open"
    control.write_text(json.dumps(state))
    try:
        worker._restore_root_policy_for_target(next_revision)
    except worker.HostReconcileError:
        pass
    else:
        raise AssertionError("open breaker cannot authorize committed receipt reuse")



def test_applied_migration_survives_descendant_lkg_and_open_breaker_rollback(
        tmp_path, monkeypatch):
    import importlib.util
    import hashlib
    import json
    import pytest
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location(
        "jason_root_migration_descendant", ROOT / "tools" / "release_host_reconcile_worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    old, migrated, lkg, candidate = ("a"*40, "b"*40, "c"*40, "d"*40)
    active, policy, control = (tmp_path / name for name in
                               ("active.json", "policy.json", "production-control-state.json"))
    raw = b'{"schema_version":"1.0","allowed_system_units":[]}\n'
    policy.write_bytes(raw)
    receipt = {"schema_version": "1.0", "candidate_sha": migrated,
               "rollback_sha": old, "phase": "applied",
               "applied_sha256": hashlib.sha256(raw).hexdigest()}
    active.write_text(json.dumps(receipt))
    state = {"schema_version": "1.0", "circuit_breaker": {"state": "closed"},
             "last_known_good": {"manifest": {"revision": lkg, "complete": True}}}
    control.write_text(json.dumps(state))
    helper = SimpleNamespace(
        ROOT=tmp_path, ACTIVE=active, POLICY=policy,
        _json=lambda data: json.loads(data),
        _root_only=lambda path: path.read_bytes(),
        digest=lambda data: hashlib.sha256(data).hexdigest(),
        prepare_rollback=lambda sha: (_ for _ in ()).throw(AssertionError(
            "committed root policy must never be restored to an ancestor")),
    )
    monkeypatch.setattr(worker, "_trusted_root_policy_helper", lambda: helper)
    ancestry = {(migrated, lkg), (migrated, candidate)}
    monkeypatch.setattr(worker, "_verified_migration_ancestor",
                        lambda ancestor, desc: (ancestor, desc) in ancestry)
    assert worker._restore_root_policy_for_target(candidate) == "PREVIOUS_MIGRATION_LKG_VERIFIED"
    assert policy.read_bytes() == raw
    state["circuit_breaker"]["state"] = "open"
    control.write_text(json.dumps(state))
    assert worker._restore_root_policy_for_target(lkg) == "PREVIOUS_MIGRATION_LKG_VERIFIED"
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)
    state["circuit_breaker"]["state"] = "closed"
    control.write_text(json.dumps(state))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target("e"*40)
    ancestry.clear()
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)
    ancestry.update({(migrated, lkg), (migrated, candidate)})
    state["last_known_good"]["manifest"]["complete"] = False
    control.write_text(json.dumps(state))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)
    state["last_known_good"]["manifest"]["complete"] = True
    control.write_text(json.dumps(state))
    policy.write_bytes(b"changed")
    with pytest.raises(worker.HostReconcileError, match="committed root policy differs"):
        worker._restore_root_policy_for_target(candidate)


def test_migration_lineage_is_exact_and_fails_closed(monkeypatch):
    import importlib.util
    import subprocess
    import pytest
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location(
        "jason_root_lineage_test", ROOT / "tools" / "release_host_reconcile_worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    ancestor, descendant = "b"*40, "c"*40
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(worker.subprocess, "run", run)
    assert worker._verified_migration_ancestor(ancestor, descendant)
    assert calls[0][0][-4:] == ["merge-base", "--is-ancestor", ancestor, descendant]
    assert calls[0][1]["timeout"] == 15
    with pytest.raises(worker.HostReconcileError, match="exact revisions"):
        worker._verified_migration_ancestor("invalid", descendant)
    monkeypatch.setattr(worker.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1))
    assert not worker._verified_migration_ancestor(ancestor, descendant)
    monkeypatch.setattr(worker.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=128))
    with pytest.raises(worker.HostReconcileError, match="verification failed"):
        worker._verified_migration_ancestor(ancestor, descendant)
    monkeypatch.setattr(worker.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            subprocess.TimeoutExpired("git", 15)))
    with pytest.raises(worker.HostReconcileError, match="unavailable"):
        worker._verified_migration_ancestor(ancestor, descendant)
