from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_worker_is_bounded_to_exact_sha_and_live_mcp():
    text = (ROOT / "tools" / "release_host_reconcile_worker.py").read_text(
        encoding="utf-8"
    )
    assert 'r"^[0-9a-f]{40}$"' in text
    assert "live MCP revision does not match requested host release" in text
    assert 'Path("/opt/jason/current")' in text
    assert '"reconcile_production_host_services.sh"' in text
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
