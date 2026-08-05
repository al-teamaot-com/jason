from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tools.restore_verification import (
    RecoveryRestoreVerifier,
    RestoreVerificationError,
)


def completed(
    command: tuple[str, ...],
    *,
    return_code: int = 0,
    output: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=command,
        returncode=return_code,
        stdout=output,
    )


def package(tmp_path: Path) -> Path:
    package_directory = tmp_path / "package"
    package_directory.mkdir()
    (package_directory / "release-manifest.json").write_text(
        json.dumps(
            {
                "version": "v0.2.0",
                "commit": "abc123",
            }
        ),
        encoding="utf-8",
    )
    (package_directory / "Jason-v0.2.0.bundle").write_text(
        "bundle",
        encoding="utf-8",
    )
    return package_directory


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RestoreVerificationError, match="manifest"):
        RecoveryRestoreVerifier(tmp_path).verify(tmp_path / "missing")


def test_existing_workspace_fails_closed(tmp_path: Path) -> None:
    existing = tmp_path / "workspace"
    existing.mkdir()

    with pytest.raises(RestoreVerificationError, match="already exists"):
        RecoveryRestoreVerifier(tmp_path).verify(
            package(tmp_path),
            workspace_root=existing,
        )


def test_restore_runs_clone_checkout_commit_and_validation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    calls: list[tuple[tuple[str, ...], Path]] = []

    def runner(command, working_directory):
        normalized = tuple(str(item) for item in command)
        calls.append((normalized, working_directory))
        if normalized[:3] == ("git", "clone", "--quiet"):
            restored = Path(normalized[-1])
            (restored / ".git" / "info").mkdir(parents=True)
            (restored / "tools").mkdir()
            (restored / "tools" / "validate_release.py").write_text(
                "pass\n",
                encoding="utf-8",
            )
            return completed(normalized)
        if normalized == ("git", "rev-parse", "HEAD"):
            return completed(normalized, output="abc123\n")
        if normalized[-1].endswith("validate_release.py"):
            return completed(
                normalized,
                output="Release validation status: APPROVED\n",
            )
        return completed(normalized)

    workspace = tmp_path / "restore"
    result = RecoveryRestoreVerifier(source, runner=runner).verify(
        package(tmp_path),
        workspace_root=workspace,
        retain_workspace=True,
    )

    assert result.version == "v0.2.0"
    assert result.commit == "abc123"
    assert "APPROVED" in result.validation_output
    assert calls[0][0][:3] == ("git", "clone", "--quiet")
    assert calls[1][0] == ("git", "checkout", "--quiet", "abc123")
    assert calls[2][0] == ("git", "rev-parse", "HEAD")
    assert calls[3][0][-1].endswith("validate_release.py")


def test_command_failure_is_reported(tmp_path: Path) -> None:
    def runner(command, working_directory):
        del working_directory
        normalized = tuple(str(item) for item in command)
        return completed(normalized, return_code=1, output="clone failed")

    with pytest.raises(RestoreVerificationError, match="clone failed"):
        RecoveryRestoreVerifier(tmp_path, runner=runner).verify(
            package(tmp_path),
            workspace_root=tmp_path / "restore",
        )
