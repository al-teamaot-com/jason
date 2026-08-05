from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
from typing import Callable, Sequence


CommandRunner = Callable[
    [Sequence[str], Path],
    subprocess.CompletedProcess[str],
]


class RecoveryPackageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RecoveryArtifact:
    name: str
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class RecoveryPackageResult:
    version: str
    commit: str
    destination: Path
    artifacts: tuple[RecoveryArtifact, ...]


def default_runner(
    command: Sequence[str],
    working_directory: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=working_directory,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def normalize_version(version: str) -> str:
    normalized = version.strip()
    if not normalized:
        raise ValueError("version must be non-empty")
    if not normalized.startswith("v"):
        normalized = f"v{normalized}"
    if any(character in normalized for character in "/\\\0"):
        raise ValueError("version contains an unsafe path character")
    return normalized


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exclude_from_source(relative_path: Path) -> bool:
    excluded_names = {
        ".git",
        ".build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "site",
        "__pycache__",
    }
    if any(part in excluded_names for part in relative_path.parts):
        return True
    if any(part.startswith(".venv") for part in relative_path.parts):
        return True
    return relative_path.suffix in {".pyc", ".pyo"}


class RecoveryPackageBuilder:
    def __init__(
        self,
        repository_root: Path,
        destination_root: Path,
        *,
        runner: CommandRunner = default_runner,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._destination_root = destination_root.expanduser().resolve()
        self._runner = runner
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build(
        self,
        version: str,
        *,
        release_name: str,
        ref: str = "HEAD",
    ) -> RecoveryPackageResult:
        normalized_version = normalize_version(version)
        if not release_name.strip():
            raise ValueError("release_name must be non-empty")

        final_destination = self._destination_root / normalized_version
        staging_destination = self._destination_root / (
            f".{normalized_version}.staging-{os.getpid()}"
        )

        if final_destination.exists():
            raise RecoveryPackageError(
                f"Recovery package already exists: {final_destination}"
            )

        self._destination_root.mkdir(parents=True, exist_ok=True)
        if staging_destination.exists():
            shutil.rmtree(staging_destination)
        staging_destination.mkdir(parents=False)

        try:
            commit = self._git_output(
                ("git", "rev-parse", f"{ref}^{{commit}}")
            ).strip()
            self._assert_ref_is_reachable(ref)

            bundle_path = staging_destination / (
                f"Jason-{normalized_version}.bundle"
            )
            source_path = staging_destination / (
                f"Jason-{normalized_version}-source.tar.gz"
            )
            environment_path = staging_destination / (
                f"environment-{normalized_version}.txt"
            )
            manifest_path = staging_destination / "release-manifest.json"
            checksums_path = staging_destination / "SHA256SUMS.txt"

            self._run_required(
                (
                    "git",
                    "bundle",
                    "create",
                    str(bundle_path),
                    "--all",
                )
            )
            self._run_required(
                (
                    "git",
                    "bundle",
                    "verify",
                    str(bundle_path),
                )
            )

            self._create_source_archive(source_path)
            self._write_environment(environment_path, commit)

            initial_artifacts = (
                self._artifact(bundle_path),
                self._artifact(source_path),
                self._artifact(environment_path),
            )
            self._write_manifest(
                manifest_path,
                version=normalized_version,
                release_name=release_name.strip(),
                commit=commit,
                ref=ref,
                artifacts=initial_artifacts,
            )

            checksum_artifacts = initial_artifacts + (
                self._artifact(manifest_path),
            )
            self._write_checksums(checksums_path, checksum_artifacts)
            self._verify_checksums(
                staging_destination,
                checksums_path,
            )

            artifacts = checksum_artifacts + (
                self._artifact(checksums_path),
            )
            staging_destination.rename(final_destination)
            return RecoveryPackageResult(
                version=normalized_version,
                commit=commit,
                destination=final_destination,
                artifacts=tuple(
                    RecoveryArtifact(
                        name=artifact.name,
                        path=final_destination / artifact.name,
                        sha256=artifact.sha256,
                        size_bytes=artifact.size_bytes,
                    )
                    for artifact in artifacts
                ),
            )
        except Exception:
            shutil.rmtree(staging_destination, ignore_errors=True)
            raise

    def _assert_ref_is_reachable(self, ref: str) -> None:
        self._run_required(
            ("git", "merge-base", "--is-ancestor", ref, "HEAD")
        )

    def _git_output(self, command: Sequence[str]) -> str:
        return self._run_required(command).stdout or ""

    def _run_required(
        self,
        command: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        completed = self._runner(command, self._repository_root)
        if completed.returncode != 0:
            raise RecoveryPackageError(
                "Command failed: "
                + " ".join(command)
                + "\n"
                + (completed.stdout or "")
            )
        return completed

    def _create_source_archive(self, destination: Path) -> None:
        repository_name = self._repository_root.name
        with tarfile.open(destination, "w:gz") as archive:
            for path in sorted(self._repository_root.rglob("*")):
                relative_path = path.relative_to(self._repository_root)
                if _exclude_from_source(relative_path):
                    continue
                archive.add(
                    path,
                    arcname=Path(repository_name) / relative_path,
                    recursive=False,
                )

    def _write_environment(self, destination: Path, commit: str) -> None:
        lines = [
            "Jason Recovery Package",
            f"Created: {self._clock().astimezone(timezone.utc).isoformat()}",
            f"Commit: {commit}",
            f"Platform: {platform.platform()}",
            f"Python: {platform.python_version()}",
            self._git_output(("git", "--version")).strip(),
            "",
            "Test environment:",
            self._python_freeze(".venv-test"),
            "",
            "Documentation environment:",
            self._python_freeze(".venv-docs"),
        ]
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _python_freeze(self, environment_name: str) -> str:
        python_path = (
            self._repository_root / environment_name / "bin" / "python"
        )
        if not python_path.is_file():
            return f"{environment_name}: not present"
        if not os.access(python_path, os.X_OK):
            return f"{environment_name}: python is not executable"
        completed = self._runner(
            (str(python_path), "-m", "pip", "freeze"),
            self._repository_root,
        )
        if completed.returncode != 0:
            raise RecoveryPackageError(
                f"Unable to capture {environment_name} environment\n"
                + (completed.stdout or "")
            )
        return completed.stdout or ""

    def _write_manifest(
        self,
        destination: Path,
        *,
        version: str,
        release_name: str,
        commit: str,
        ref: str,
        artifacts: tuple[RecoveryArtifact, ...],
    ) -> None:
        manifest = {
            "schema_version": "0.1",
            "version": version,
            "release_name": release_name,
            "commit": commit,
            "source_ref": ref,
            "created_at": self._clock().astimezone(timezone.utc).isoformat(),
            "status": "recovery_package_created",
            "artifacts": [
                {
                    "name": artifact.name,
                    "sha256": artifact.sha256,
                    "size_bytes": artifact.size_bytes,
                }
                for artifact in artifacts
            ],
        }
        destination.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _artifact(path: Path) -> RecoveryArtifact:
        return RecoveryArtifact(
            name=path.name,
            path=path,
            sha256=file_sha256(path),
            size_bytes=path.stat().st_size,
        )

    @staticmethod
    def _write_checksums(
        destination: Path,
        artifacts: tuple[RecoveryArtifact, ...],
    ) -> None:
        destination.write_text(
            "".join(
                f"{artifact.sha256}  {artifact.name}\n"
                for artifact in artifacts
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _verify_checksums(
        package_directory: Path,
        checksums_path: Path,
    ) -> None:
        for line in checksums_path.read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", maxsplit=1)
            actual = file_sha256(package_directory / name)
            if actual != expected:
                raise RecoveryPackageError(
                    f"Checksum verification failed: {name}"
                )
