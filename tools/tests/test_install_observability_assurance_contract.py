from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "tools" / "install_observability_assurance.sh"


def test_observability_installer_uses_managed_source_and_safe_git_boundary() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'REPO_ROOT="${JASON_REPO_ROOT:-/home/al/.local/lib/jason/engineering-source-repo}"' in text
    assert 'git -c "safe.directory=$REPO_ROOT" -C "$REPO_ROOT"' in text
    assert 'observability install may not depend on a developer checkout' in text
    assert 'git_repo archive "$SOURCE_REVISION"' in text


def test_observability_installer_fails_closed_without_root() -> None:
    result = subprocess.run(
        ["bash", str(INSTALLER), "0" * 40],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 77
    assert "root privileges are required" in result.stderr
