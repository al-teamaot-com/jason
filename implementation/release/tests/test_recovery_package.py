from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from tools.recovery_package import (
    RecoveryPackageBuilder,
    RecoveryPackageError,
    file_sha256,
    normalize_version,
)


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def run(command: tuple[str, ...], cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert completed.returncode == 0, completed.stdout


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "jason"
    root.mkdir()
    run(("git", "init", "-q"), root)
    run(("git", "config", "user.name", "Jason Test"), root)
    run(("git", "config", "user.email", "jason@example.test"), root)
    (root / "README.md").write_text("Jason\n", encoding="utf-8")
    (root / ".venv-test" / "bin").mkdir(parents=True)
    (root / ".venv-test" / "bin" / "python").write_text(
        "ignored\n",
        encoding="utf-8",
    )
    run(("git", "add", "README.md"), root)
    run(("git", "commit", "-q", "-m", "Initial"), root)
    return root


def test_normalize_version() -> None:
    assert normalize_version("0.2.0") == "v0.2.0"
    assert normalize_version(" v0.2.0 ") == "v0.2.0"


@pytest.mark.parametrize("version", ["", " ", "v0/2/0", "v0\\2\\0"])
def test_rejects_unsafe_versions(version: str) -> None:
    with pytest.raises(ValueError):
        normalize_version(version)


def test_builds_verified_recovery_package(tmp_path: Path) -> None:
    root = repository(tmp_path)
    destination = tmp_path / "recovery"

    result = RecoveryPackageBuilder(
        root,
        destination,
        clock=lambda: NOW,
    ).build(
        "0.2.0",
        release_name="Recovery Foundation",
    )

    assert result.version == "v0.2.0"
    assert result.destination == destination / "v0.2.0"
    assert result.destination.is_dir()

    names = {artifact.name for artifact in result.artifacts}
    assert names == {
        "Jason-v0.2.0.bundle",
        "Jason-v0.2.0-source.tar.gz",
        "environment-v0.2.0.txt",
        "release-manifest.json",
        "SHA256SUMS.txt",
    }

    checksums = (
        result.destination / "SHA256SUMS.txt"
    ).read_text(encoding="utf-8")
    assert "Jason-v0.2.0.bundle" in checksums
    assert "release-manifest.json" in checksums

    environment = (
        result.destination / "environment-v0.2.0.txt"
    ).read_text(encoding="utf-8")
    assert ".venv-test: python is not executable" in environment
    assert ".venv-docs: not present" in environment

    for artifact in result.artifacts:
        assert artifact.path.is_file()
        assert artifact.sha256 == file_sha256(artifact.path)


def test_source_archive_excludes_repository_and_venv_metadata(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path)
    result = RecoveryPackageBuilder(
        root,
        tmp_path / "recovery",
        clock=lambda: NOW,
    ).build("v0.2.0", release_name="Recovery Foundation")

    archive = result.destination / "Jason-v0.2.0-source.tar.gz"
    completed = subprocess.run(
        ("tar", "-tzf", str(archive)),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert completed.returncode == 0
    assert "/.git/" not in completed.stdout
    assert "/.venv-test/" not in completed.stdout
    assert "jason/README.md" in completed.stdout


def test_existing_release_directory_fails_closed(tmp_path: Path) -> None:
    root = repository(tmp_path)
    destination = tmp_path / "recovery"
    (destination / "v0.2.0").mkdir(parents=True)

    with pytest.raises(RecoveryPackageError, match="already exists"):
        RecoveryPackageBuilder(
            root,
            destination,
            clock=lambda: NOW,
        ).build("v0.2.0", release_name="Recovery Foundation")
