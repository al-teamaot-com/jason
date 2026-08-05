from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable, Iterable

from tools.recovery_package import file_sha256


class ReleaseEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseEvidenceResult:
    report_path: Path
    summary_path: Path
    checksums_path: Path


class ReleaseEvidenceWriter:
    """Write machine-readable and human-readable release evidence."""

    def __init__(
        self,
        repository_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def write(
        self,
        *,
        version: str,
        release_name: str,
        commit: str,
        package_directory: Path,
        documentation_path: Path,
        validation_step_ids: Iterable[str],
        restored_commit: str,
    ) -> ReleaseEvidenceResult:
        package_directory = package_directory.expanduser().resolve()
        if restored_commit != commit:
            raise ReleaseEvidenceError(
                "Restored commit does not match the release commit."
            )
        if not package_directory.is_dir():
            raise ReleaseEvidenceError(
                f"Recovery package directory is missing: {package_directory}"
            )

        report_path = package_directory / "release-report.json"
        summary_path = package_directory / "release-summary.md"
        checksums_path = package_directory / "SHA256SUMS.txt"
        if report_path.exists() or summary_path.exists():
            raise ReleaseEvidenceError("Release evidence already exists.")

        created_at = self._clock().astimezone(timezone.utc).isoformat()
        artifact_entries = []
        for path in sorted(package_directory.iterdir()):
            if not path.is_file() or path.name in {
                "SHA256SUMS.txt",
                "release-report.json",
                "release-summary.md",
            }:
                continue
            artifact_entries.append(
                {
                    "name": path.name,
                    "sha256": file_sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )

        report = {
            "schema_version": "0.1",
            "version": version,
            "release_name": release_name,
            "commit": commit,
            "created_at": created_at,
            "documentation": {
                "path": documentation_path.as_posix(),
                "status": "approved",
            },
            "validation": {
                "status": "approved",
                "steps": list(validation_step_ids),
            },
            "recovery_package": {
                "path": str(package_directory),
                "artifacts": artifact_entries,
            },
            "restore_verification": {
                "status": "approved",
                "commit": restored_commit,
            },
            "overall_status": "approved",
        }
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        summary_path.write_text(
            "\n".join(
                (
                    f"# Jason Release {version}",
                    "",
                    f"**Release:** {release_name}",
                    f"**Commit:** `{commit}`",
                    "**Overall status:** APPROVED",
                    "",
                    "## Governed stages",
                    "",
                    "- Documentation readiness: PASS",
                    "- Release validation: PASS",
                    "- Recovery package creation: PASS",
                    "- Restore verification: PASS",
                    "- Commit alignment: PASS",
                    "",
                    f"**Documentation record:** `{documentation_path.as_posix()}`",
                    f"**Recovery location:** `{package_directory}`",
                    "",
                )
            ),
            encoding="utf-8",
        )

        checksum_lines = []
        for path in sorted(package_directory.iterdir()):
            if path.is_file() and path.name != "SHA256SUMS.txt":
                checksum_lines.append(f"{file_sha256(path)}  {path.name}\n")
        checksums_path.write_text("".join(checksum_lines), encoding="utf-8")

        for line in checksums_path.read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", maxsplit=1)
            if file_sha256(package_directory / name) != expected:
                raise ReleaseEvidenceError(
                    f"Evidence checksum verification failed: {name}"
                )

        return ReleaseEvidenceResult(
            report_path=report_path,
            summary_path=summary_path,
            checksums_path=checksums_path,
        )
