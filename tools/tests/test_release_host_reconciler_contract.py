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
