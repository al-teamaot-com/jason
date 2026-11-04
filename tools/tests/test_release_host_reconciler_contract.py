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
    assert "HOST_RECONCILE_TIMEOUT_SECONDS = 4200" in text
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
    assert 'HOST_RECONCILE_TIMEOUT_SECONDS = 4200' in text
    assert 'TimeoutStartSec=4500' in unit
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
    # The native Release Manager and root systemd unit remain finitely bounded
    # above the root worker's recovery-proof window.
    manager = (ROOT / "tools" / "release_manager_host_runner.py").read_text()
    systemd = (ROOT / "infrastructure/openclaw-operations/systemd/jason-release-host-reconcile.service").read_text()
    assert "timeout_seconds: float = 4440.0" in manager
    assert "TimeoutStartSec=4500" in systemd



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
    policy.write_bytes(raw)
    # A staged or malformed receipt is not a committed authority grant.
    receipt["phase"] = "staged"
    active.write_text(json.dumps(receipt))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)
    receipt["phase"] = "applied"
    active.write_text(json.dumps(receipt))
    state["circuit_breaker"]["state"] = "unknown"
    control.write_text(json.dumps(state))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
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



def test_applied_root_policy_survives_exact_owner_approved_forward_recovery(
        tmp_path, monkeypatch):
    import hashlib
    import importlib.util
    import json
    import pytest
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "jason_root_forward_recovery",
        ROOT / "tools" / "release_host_reconcile_worker.py",
    )
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    old, migrated, lkg, candidate = ("a"*40, "b"*40, "c"*40, "d"*40)
    active = tmp_path / "active.json"
    policy = tmp_path / "policy.json"
    control = tmp_path / "production-control-state.json"
    records = tmp_path / "records"
    records.mkdir()

    root_policy = {
        "schema_version": "1.0",
        "required_system_units": ["jason-known.timer"],
        "allowed_system_units": [],
        "required_user_units": [],
        "allowed_user_units": [],
    }
    raw = (json.dumps(root_policy, sort_keys=True) + "\n").encode()
    policy.write_bytes(raw)
    active.write_text(json.dumps({
        "schema_version": "1.0",
        "candidate_sha": migrated,
        "rollback_sha": old,
        "phase": "applied",
        "applied_sha256": hashlib.sha256(raw).hexdigest(),
    }))
    control.write_text(json.dumps({
        "schema_version": "1.0",
        "circuit_breaker": {
            "state": "open",
            "source": "production_drift_watchdog",
        },
        "last_known_good": {
            "manifest": {"revision": lkg, "complete": True}
        },
    }))
    release_path = records / ("release-" + candidate[:16] + ".json")
    release_path.write_text(json.dumps({
        "release_id": "release-" + candidate[:16],
        "state": "production",
        "risk_profile": "production_control_core",
        "rollback_sha": lkg,
        "release_candidate": {"candidate_sha": candidate},
        "release_manifest": {
            "candidate_sha": candidate,
            "rollback_sha": lkg,
        },
        "owner_approval": {
            "approved": True,
            "candidate_sha": candidate,
            "source": "authenticated_mobile_teams_owner:relapproval-test123",
        },
        "one_transaction_freeze_exception": {
            "required_recovery_profile_id":
                "provider_identity_and_authority_recovery",
            "rollback_sha": lkg,
            "standing_authority": False,
            "signed_teams_release_approval_required": True,
            "restore_freeze_after_transaction": True,
        },
    }))
    release_path.chmod(0o600)
    helper = SimpleNamespace(
        ROOT=tmp_path,
        ACTIVE=active,
        POLICY=policy,
        _json=lambda data: json.loads(data),
        _root_only=lambda path: path.read_bytes(),
        digest=lambda data: hashlib.sha256(data).hexdigest(),
        prepare_rollback=lambda sha: (_ for _ in ()).throw(
            AssertionError("forward recovery must not rewrite root policy")
        ),
    )
    monkeypatch.setattr(worker, "RELEASE_STATE", tmp_path)
    monkeypatch.setattr(worker, "_trusted_root_policy_helper", lambda: helper)
    monkeypatch.setattr(worker, "_protected_root_drift_policy",
                        lambda: root_policy)
    ancestry = {
        (migrated, lkg),
        (migrated, candidate),
        (lkg, candidate),
    }
    monkeypatch.setattr(
        worker, "_verified_migration_ancestor",
        lambda ancestor, descendant: (ancestor, descendant) in ancestry,
    )
    monkeypatch.setattr(
        worker.subprocess, "check_output",
        lambda *args, **kwargs: json.dumps(root_policy),
    )

    monkeypatch.setattr(
        worker, "_host_operator_uid",
        lambda: release_path.lstat().st_uid,
    )
    meta = release_path.lstat()
    assert meta.st_mode & 0o022 == 0
    release_check = json.loads(release_path.read_text())
    assert release_check["state"] == "production"
    assert release_check["risk_profile"] == "production_control_core"
    assert release_check["rollback_sha"] == lkg
    assert release_check["release_candidate"]["candidate_sha"] == candidate
    assert release_check["release_manifest"]["candidate_sha"] == candidate
    assert release_check["release_manifest"]["rollback_sha"] == lkg
    assert release_check["owner_approval"]["approved"] is True
    assert release_check["owner_approval"]["candidate_sha"] == candidate
    assert release_check["owner_approval"]["source"].startswith(
        "authenticated_mobile_teams_owner:relapproval-"
    )
    assert release_check["one_transaction_freeze_exception"][
        "required_recovery_profile_id"
    ] == "provider_identity_and_authority_recovery"
    assert worker._verified_migration_ancestor(lkg, candidate)
    assert worker._forward_recovery_release_authorized(
        candidate, lkg, {"state": "open", "source": "production_drift_watchdog"}
    ) is True
    assert (
        worker._restore_root_policy_for_target(candidate)
        == "PREVIOUS_MIGRATION_FORWARD_DESCENDANT_VERIFIED"
    )
    assert policy.read_bytes() == raw

    release = json.loads(release_path.read_text())
    release["owner_approval"]["approved"] = False
    release_path.write_text(json.dumps(release))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)

    release["owner_approval"]["approved"] = True
    release["state"] = "production_eligible"
    release_path.write_text(json.dumps(release))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)

    release["state"] = "production"
    release_path.write_text(json.dumps(release))
    monkeypatch.setattr(
        worker.subprocess, "check_output",
        lambda *args, **kwargs: json.dumps({
            **root_policy,
            "allowed_system_units": ["jason-unreviewed.service"],
        }),
    )
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)

    monkeypatch.setattr(
        worker.subprocess, "check_output",
        lambda *args, **kwargs: json.dumps(root_policy),
    )
    ancestry.remove((lkg, candidate))
    with pytest.raises(worker.HostReconcileError, match="does not belong"):
        worker._restore_root_policy_for_target(candidate)


def test_current_lkg_recovery_materializes_only_pinned_health_code(tmp_path, monkeypatch):
    import hashlib
    import importlib.util
    import os
    source = ROOT / "tools" / "release_host_reconcile_worker.py"
    spec = importlib.util.spec_from_file_location("jason_current_lkg_recovery_materialize", source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    wrapper_body = "SOURCE_HEALTH_TIMEOUT_SECONDS = 1800\nprint('wrapper')\n"
    tool_body = "print('tool')\n"
    monkeypatch.setattr(worker, "CURRENT_LKG_HEALTH_WRAPPER_SHA256", hashlib.sha256(wrapper_body.encode()).hexdigest())
    monkeypatch.setattr(worker, "CURRENT_LKG_HEALTH_TOOL_SHA256", hashlib.sha256(tool_body.encode()).hexdigest())
    monkeypatch.setattr(worker, "CURRENT_LKG_EXEC_ROOT", tmp_path / "root-controlled-health")
    monkeypatch.setattr(worker, "_current_lkg_recovery_authorized", lambda _: True)
    monkeypatch.setattr(worker, "_trusted_current_lkg_archive_tmp", lambda: None)
    monkeypatch.setattr(worker.os, "chown", lambda *args: None)
    # The production helper checks real root ownership; this unit test has no
    # root privilege and supplies only an isolated, owner-trusted temp fixture.
    monkeypatch.setattr(worker, "_trusted_current_lkg_execution_dir",
                        lambda: (tmp_path, os.getgid()))

    def fake_show(command, **kwargs):
        ref = command[-1]
        if ref.endswith("openclaw_authority_health_snapshot.py"):
            return wrapper_body
        if ref.endswith("openclaw_authority_operational_health.py"):
            return tool_body
        raise AssertionError(ref)

    monkeypatch.setattr(worker.subprocess, "check_output", fake_show)
    wrapper = worker._materialize_current_lkg_health_recovery(worker.CURRENT_LKG_RECOVERY_SHA)
    assert wrapper.read_text() == "SOURCE_HEALTH_TIMEOUT_SECONDS = 3600\nprint('wrapper')\n"
    assert (wrapper.parent / "openclaw_authority_operational_health.py").read_text() == tool_body
    assert wrapper.parent.stat().st_mode & 0o777 == 0o700
    assert wrapper.stat().st_mode & 0o777 == 0o640
    assert (wrapper.parent / "openclaw_authority_operational_health.py").stat().st_mode & 0o777 == 0o640


def test_current_lkg_exec_dir_rejects_untrusted_or_symlinked_paths(tmp_path, monkeypatch):
    import importlib.util
    import pytest
    import os
    import stat
    from types import SimpleNamespace
    source = ROOT / "tools" / "release_host_reconcile_worker.py"
    spec = importlib.util.spec_from_file_location("jason_lkg_exec_dir_trust_test", source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    parent = tmp_path / "root-managed"
    parent.mkdir(mode=0o755)
    root = parent / "lkg-health-test"
    monkeypatch.setattr(worker, "CURRENT_LKG_EXEC_ROOT", root)
    monkeypatch.setattr(worker.grp, "getgrnam", lambda _: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(worker.os, "chown", lambda *args: None)
    real_lstat = type(parent).lstat

    def root_owned_lstat(path):
        info = real_lstat(path)
        if path in {parent, root}:
            return SimpleNamespace(st_uid=0, st_mode=info.st_mode)
        return info

    monkeypatch.setattr(type(parent), "lstat", root_owned_lstat)
    observed, group = worker._trusted_current_lkg_execution_dir()
    assert observed == root
    assert group == os.getgid()
    assert stat.S_IMODE(root.stat().st_mode) == 0o750

    # A malicious symlink inside a trusted parent is never followed.
    root.rmdir()
    target = tmp_path / "unsafe-target"
    target.mkdir()
    root.symlink_to(target, target_is_directory=True)
    with pytest.raises(worker.HostReconcileError, match="untrusted"):
        worker._trusted_current_lkg_execution_dir()

    # No re-permissioning of a writable or non-root-owned existing directory.
    root.unlink()
    root.mkdir(mode=0o770)
    root.chmod(0o770)
    with pytest.raises(worker.HostReconcileError, match="untrusted"):
        worker._trusted_current_lkg_execution_dir()


def test_current_lkg_recovery_requires_real_pass_and_controlled_tmpdir(tmp_path, monkeypatch):
    import importlib.util
    import json
    import os
    from types import SimpleNamespace
    source = ROOT / "tools" / "release_host_reconcile_worker.py"
    spec = importlib.util.spec_from_file_location("jason_current_lkg_recovery_run", source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)

    wrapper = tmp_path / "openclaw_authority_health_snapshot.py"
    wrapper.write_text("print('unused')\n")
    evidence = tmp_path / "operational-full-health.json"
    archive = tmp_path / "archive"
    archive.mkdir()
    monkeypatch.setattr(worker, "CURRENT_LKG_FULL_EVIDENCE", evidence)
    monkeypatch.setattr(worker, "CURRENT_LKG_ARCHIVE_TMP", archive)
    monkeypatch.setattr(worker, "_materialize_current_lkg_health_recovery", lambda _: wrapper)
    monkeypatch.setattr(worker.pwd, "getpwnam", lambda _: SimpleNamespace(pw_uid=os.getuid()))
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["env"] = kwargs["env"]
        evidence.write_text(json.dumps({
            "status": "pass", "snapshot_source_exit_code": 0,
            "provider_contacted": False, "provider_credentials_used": False,
            "failures": [],
        }))
        os.chmod(evidence, 0o600)
        return SimpleNamespace(returncode=0, stdout="PASS")

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    assert worker._run_current_lkg_health_recovery(worker.CURRENT_LKG_RECOVERY_SHA) == "CURRENT_LKG_FULL_INTEGRITY_RECOVERY=PASS"
    assert observed["env"]["TMPDIR"] == str(archive)
    command_has = observed["command"]
    assert command_has[:4] == ["/usr/sbin/runuser", "-u", "al", "--"]


def test_current_lkg_recovery_time_budget_is_bounded_below_root_worker_ceiling():
    import importlib.util
    source = ROOT / "tools" / "release_host_reconcile_worker.py"
    spec = importlib.util.spec_from_file_location("jason_current_lkg_recovery_budget", source)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    assert worker._host_reconcile_timeout(worker.CURRENT_LKG_RECOVERY_SHA) == 500
    assert worker.CURRENT_LKG_HEALTH_RECOVERY_TIMEOUT_SECONDS + 500 < 4500
    assert worker._host_reconcile_timeout(worker.LEGACY_LKG_SHA) == 410


def test_distinct_exact_owner_unfreeze_receipt_allows_only_locked_lkg_rollback(
    tmp_path, monkeypatch
):
    import fcntl
    import hashlib
    import importlib.util
    import json
    import os

    src = ROOT / "tools/release_host_reconcile_worker.py"
    spec = importlib.util.spec_from_file_location("jason_owner_unfreeze_lkg_test", src)
    worker = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(worker)
    old = worker.CURRENT_LKG_RECOVERY_SHA
    candidate = "a" * 40
    approval_source = "authenticated_mobile_teams_owner:relapproval-" + "9" * 32
    state = tmp_path / "release-state"
    (state / "records").mkdir(parents=True)
    receipts = state / "owner-explicit-unfreeze-receipts"
    receipts.mkdir()
    lock = state / "production-transaction.lock"
    lock.touch(mode=0o600)
    backup = state / "production-deployment-freeze.pmv3-one-release-backup"
    backup.write_bytes(b"frozen-exact-owner-marker")
    backup.chmod(0o600)
    scope = "b" * 64
    record = {
        "state": "production",
        "risk_profile": "production_control_core",
        "release_candidate": {"candidate_sha": candidate},
        "rollback_sha": old,
        "release_manifest": {"candidate_sha": candidate, "rollback_sha": old},
        "owner_approval": {"approved": True, "candidate_sha": candidate,
                           "source": approval_source},
        "manual_scope_review": {"scope_sha256": scope},
        "last_known_good_manifest": {"revision": old, "complete": True},
        "pre_mutation_health": {"revision": old, "passed": True},
    }
    record_path = state / "records" / ("release-" + candidate[:16] + ".json")
    record_path.write_text(json.dumps(record))
    record_path.chmod(0o600)
    receipt = {
        "schema_version": "1.0",
        "authorization": "explicit_exact_sha_owner_unfreeze",
        "status": "authorized_pending",
        "release_id": "release-" + candidate[:16],
        "candidate_sha": candidate, "rollback_sha": old,
        "scope_sha256": scope,
        "prior_release_approval_source": approval_source,
        "owner_approval_source": "explicit_owner_instruction",
        "separate_exact_owner_unfreeze": True,
        "freeze_remains_active": True,
        "restore_freeze_after_transaction": True,
        "standing_authority": False, "automatic_publish_authority": False,
        "freeze_sha256_before": hashlib.sha256(backup.read_bytes()).hexdigest(),
    }
    receipt_path = receipts / ("release-" + candidate[:16] + ".json")
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o600)
    hosts = tmp_path / "hosts"
    hosts.mkdir()
    (hosts / candidate).mkdir()
    current = tmp_path / "current"
    current.symlink_to(hosts / candidate)
    monkeypatch.setattr(worker, "RELEASE_STATE", state)
    monkeypatch.setattr(worker, "CURRENT", current)
    monkeypatch.setattr(worker, "_host_operator_uid", lambda: os.getuid())
    monkeypatch.setattr(worker.subprocess, "check_output", lambda *a, **k: candidate)
    monkeypatch.setattr(worker, "_authenticated_rollback_evidence", lambda *a: True)
    lkg = {"complete": True, "revision": old}
    breaker = {"state": "closed"}
    assert not worker._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
    with lock.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert worker._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
            for field, tampered in [
                ("status", "consumed"), ("rollback_sha", "c" * 40),
                ("scope_sha256", "d" * 64),
                ("prior_release_approval_source", "forged"),
                ("freeze_sha256_before", "0" * 64),
                ("standing_authority", True),
                ("restore_freeze_after_transaction", False),
            ]:
                changed = dict(receipt, **{field: tampered})
                receipt_path.write_text(json.dumps(changed))
                assert not worker._exact_signed_inflight_lkg_rollback_authorized(
                    old, lkg, breaker
                ), field
            receipt_path.write_text(json.dumps(receipt))
            receipt_path.chmod(0o644)
            assert not worker._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
            receipt_path.chmod(0o600)
            (state / "production-deployment-freeze").write_text("active")
            assert not worker._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_current_lkg_rollback_during_signed_inflight_release_is_exact_and_bounded(
    tmp_path, monkeypatch
):
    """A signed release may restore its protected LKG BEFORE the breaker opens.

    The root reconciler must reject arbitrary source, missing lock, missing
    one-time freeze backup, absent approval, and stale/failed release records.
    """
    import fcntl
    import importlib.util
    import json
    import sqlite3
    import hashlib
    import os
    from pathlib import Path
    from types import SimpleNamespace

    src = ROOT / 'tools' / 'release_host_reconcile_worker.py'
    spec = importlib.util.spec_from_file_location('jason_exact_inflight_rollback_test', src)
    w = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(w)
    old = w.CURRENT_LKG_RECOVERY_SHA
    candidate = 'a' * 40
    approval_id = 'relapproval-' + '9' * 32
    state = tmp_path / 'state'
    (state / 'records').mkdir(parents=True)
    lock = state / 'production-transaction.lock'
    lock.touch(mode=0o600)
    backup = state / 'production-deployment-freeze.pmv3-one-release-backup'
    backup.write_text('preserved frozen owner marker\n')
    backup.chmod(0o600)
    release = state / 'records' / ('release-' + candidate[:16] + '.json')
    manifest = {
        'candidate_sha': candidate,
        'rollback_sha': old,
        'one_transaction_freeze_exception': {
            'rollback_sha': old,
            'required_recovery_profile_id': 'provider_identity_and_authority_recovery',
            'standing_authority': False,
            'signed_teams_release_approval_required': True,
            'restore_freeze_after_transaction': True,
        },
    }
    record = {
        'state': 'production',
        'risk_profile': 'production_control_core',
        'release_candidate': {'candidate_sha': candidate},
        'rollback_sha': old,
        'release_manifest': manifest,
        'one_transaction_freeze_exception': manifest['one_transaction_freeze_exception'],
        'owner_approval': {
            'approved': True, 'candidate_sha': candidate,
            'source': 'authenticated_mobile_teams_owner:' + approval_id,
        },
        'last_known_good_manifest': {'revision': old, 'complete': True},
        'pre_mutation_health': {'revision': old, 'passed': True},
    }
    release.write_text(json.dumps(record))
    release.chmod(0o600)
    digest = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    ).encode()).hexdigest()
    approval_db = tmp_path / 'mobile-release-approvals.sqlite3'
    con = sqlite3.connect(approval_db)
    con.execute('CREATE TABLE approval_requests (approval_id TEXT, payload TEXT)')
    approved_receipt = {'status': 'approved', 'metadata': {
        'candidate_sha': candidate, 'rollback_sha': old,
        'release_id': 'release-' + candidate[:16], 'manifest_sha256': digest
    }}
    con.execute('INSERT INTO approval_requests VALUES (?, ?)',
                (approval_id, json.dumps(approved_receipt)))
    con.commit()
    con.close()
    approval_db.chmod(0o600)
    ccc = tmp_path / 'ccc'
    ccc.mkdir()
    review = ccc / ('material-review-' + candidate[:16] + '.json')
    review.write_text(json.dumps({
        'status':'approved', 'source_revision':candidate,
        'mobile_approval_id':approval_id, 'release_manifest_sha256':digest,
    }))
    review.chmod(0o600)
    monkeypatch.setattr(w, 'MOBILE_APPROVAL_LEDGER', approval_db)
    monkeypatch.setattr(w, 'CCC_MATERIAL_REVIEW_ROOT', ccc)
    hosts = tmp_path / 'hosts'
    hosts.mkdir()
    (hosts / candidate).mkdir()
    live = tmp_path / 'current'
    live.symlink_to(hosts / candidate)
    monkeypatch.setattr(w, 'CURRENT', live)
    monkeypatch.setattr(w, 'RELEASE_STATE', state)
    monkeypatch.setattr(w, '_host_operator_uid', lambda: os.getuid())
    monkeypatch.setattr(w.subprocess, 'check_output', lambda *args, **kwargs: candidate)
    lkg = {'revision': old, 'complete': True}
    breaker = {'state': 'closed'}
    # Without a held transaction, an approved record is insufficient.
    assert not w._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
    with lock.open('rb') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert w._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
            assert not w._exact_signed_inflight_lkg_rollback_authorized('b' * 40, lkg, breaker)
            assert not w._exact_signed_inflight_lkg_rollback_authorized(old, lkg, {'state':'open'})
            assert not w._exact_signed_inflight_lkg_rollback_authorized(old, {'revision':old,'complete':False}, breaker)
            for field, value in [('state', 'failed'), ('risk_profile','normal')]:
                altered = dict(record);altered[field] = value
                release.write_text(json.dumps(altered))
                assert not w._exact_signed_inflight_lkg_rollback_authorized(old, lkg, breaker)
            altered = dict(record)
            altered['owner_approval'] = dict(record['owner_approval'], approved=False)
            release.write_text(json.dumps(altered))
            assert not w._exact_signed_inflight_lkg_rollback_authorized(old,lkg,breaker)
            release.write_text(json.dumps(record))
            # Receipt or CCC drift cannot be explained away by a mutable
            # release record: both are required to match the exact manifest.
            review.write_text(json.dumps({
                'status':'approved', 'source_revision':candidate,
                'mobile_approval_id':approval_id,
                'release_manifest_sha256':'0' * 64,
            }))
            assert not w._exact_signed_inflight_lkg_rollback_authorized(old,lkg,breaker)
            review.write_text(json.dumps({
                'status':'approved', 'source_revision':candidate,
                'mobile_approval_id':approval_id,
                'release_manifest_sha256':digest,
            }))
            con = sqlite3.connect(approval_db)
            con.execute('UPDATE approval_requests SET payload=? WHERE approval_id=?',
                        (json.dumps(dict(approved_receipt, status='denied')), approval_id))
            con.commit()
            con.close()
            assert not w._exact_signed_inflight_lkg_rollback_authorized(old,lkg,breaker)
            con = sqlite3.connect(approval_db)
            con.execute('UPDATE approval_requests SET payload=? WHERE approval_id=?',
                        (json.dumps(approved_receipt), approval_id))
            con.commit()
            con.close()
            backup.unlink()
            assert not w._exact_signed_inflight_lkg_rollback_authorized(old,lkg,breaker)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_current_lkg_root_recovery_retains_open_breaker_path_without_transaction(
    tmp_path, monkeypatch
):
    import importlib.util
    import json
    from types import SimpleNamespace
    source = ROOT / 'tools' / 'release_host_reconcile_worker.py'
    spec = importlib.util.spec_from_file_location('jason_rollback_open_breaker_test', source)
    w = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(w)
    root = tmp_path / 'root'
    root.mkdir()
    control = root / 'production-control-state.json'
    sha = w.CURRENT_LKG_RECOVERY_SHA
    control.write_text(json.dumps({
        'last_known_good': {'manifest': {'revision':sha, 'complete':True}},
        'circuit_breaker': {'state':'open'}
    }))
    helper = SimpleNamespace(ROOT=root, _root_only=lambda p: p, _json=lambda p: json.loads(p.read_text()))
    monkeypatch.setattr(w, '_trusted_root_policy_helper',lambda: helper)
    assert w._current_lkg_recovery_authorized(sha)
    assert not w._current_lkg_recovery_authorized('c'*40)
    control.write_text(json.dumps({
        'last_known_good': {'manifest': {'revision': 'd'*40, 'complete':True}},
        'circuit_breaker': {'state':'open'}
    }))
    assert not w._current_lkg_recovery_authorized(sha)


def test_host_reconciler_requires_installed_worker_gate_alignment():
    shell = (ROOT / 'tools/reconcile_production_host_services.sh').read_text()
    assert '  pmv3_worker_release_gate.py \
' in shell
    assert 'installed worker differs from production source' in shell
    assert shell.index('step_start protected_root_policy_stage') < shell.index('step_start user_worker_reconciliation')
