from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from typing import Callable

from tools.recovery_package import RecoveryPackageBuilder
from tools.restore_verification import RecoveryRestoreVerifier


REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


class CCCCheckpointError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CCCCheckpointResult:
    checkpoint_id: str
    checkpoint_directory: Path
    recovery_directory: Path
    source_revision: str
    runtime_revision: str
    pointer_path: Path


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CCCCheckpointError(f"Unable to read JSON evidence: {path}") from error
    if not isinstance(value, dict):
        raise CCCCheckpointError(f"JSON evidence must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_revision(value: object, field: str) -> str:
    revision = str(value or "").strip().lower()
    if not REVISION_RE.fullmatch(revision):
        raise CCCCheckpointError(f"{field} must be a full 40-character Git revision")
    return revision


class LastKnownCompliantPromoter:
    """Create and atomically promote a restore-verified CCC recovery point."""

    def __init__(
        self,
        repository_root: Path,
        recovery_root: Path,
        checkpoint_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        package_builder_factory=RecoveryPackageBuilder,
        restore_verifier_factory=RecoveryRestoreVerifier,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.recovery_root = recovery_root.expanduser().resolve()
        self.checkpoint_root = checkpoint_root.expanduser().resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.package_builder_factory = package_builder_factory
        self.restore_verifier_factory = restore_verifier_factory

    def promote(self, ccc_report_path: Path, runtime_manifest_path: Path) -> CCCCheckpointResult:
        ccc_report_path = ccc_report_path.expanduser().resolve()
        runtime_manifest_path = runtime_manifest_path.expanduser().resolve()
        report = _load_json(ccc_report_path)
        runtime = _load_json(runtime_manifest_path)

        status = str(report.get("status", "")).strip().upper()
        if status != "PASS":
            raise CCCCheckpointError(
                f"CCC status must be PASS before promotion; received {status or 'MISSING'}"
            )

        source_revision = _require_revision(report.get("source_revision"), "source_revision")
        runtime_revision = _require_revision(report.get("runtime_revision"), "runtime_revision")
        runtime_source_revision = _require_revision(
            runtime.get("runtime_revision"), "runtime_manifest.runtime_revision"
        )
        if runtime_source_revision != runtime_revision:
            raise CCCCheckpointError("CCC report/runtime manifest revision mismatch")

        head = self._git_output("rev-parse", "HEAD")
        if head != source_revision:
            raise CCCCheckpointError(
                f"Repository HEAD {head} does not match certified source revision {source_revision}"
            )
        if self._git_output("status", "--porcelain"):
            raise CCCCheckpointError("Repository must be clean before creating a compliant snapshot")

        now = self.clock().astimezone(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        checkpoint_id = f"ccc-{stamp}-{source_revision[:12]}"
        version = f"v{checkpoint_id}"
        checkpoint_directory = self.checkpoint_root / checkpoint_id
        if checkpoint_directory.exists():
            raise CCCCheckpointError(f"CCC checkpoint already exists: {checkpoint_directory}")

        builder = self.package_builder_factory(self.repository_root, self.recovery_root)
        package = builder.build(version, release_name="CCC Last Known Compliant", ref="HEAD")
        verifier = self.restore_verifier_factory(self.repository_root)
        restored = verifier.verify(package.destination)
        if restored.commit != source_revision or package.commit != source_revision:
            raise CCCCheckpointError("Restore verification did not reproduce the certified source revision")

        staging = self.checkpoint_root / f".{checkpoint_id}.staging-{os.getpid()}"
        self.checkpoint_root.mkdir(parents=True, exist_ok=True)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        try:
            report_copy = staging / "ccc-report.json"
            runtime_copy = staging / "runtime-manifest.json"
            shutil.copy2(ccc_report_path, report_copy)
            shutil.copy2(runtime_manifest_path, runtime_copy)
            manifest = {
                "schema_version": "1.0",
                "checkpoint_id": checkpoint_id,
                "status": "PASS",
                "created_at": now.isoformat(),
                "source_revision": source_revision,
                "runtime_revision": runtime_revision,
                "recovery_directory": str(package.destination),
                "restore_verified": True,
                "evidence": {
                    "ccc_report": {"path": report_copy.name, "sha256": _sha256(report_copy)},
                    "runtime_manifest": {"path": runtime_copy.name, "sha256": _sha256(runtime_copy)},
                    "recovery_manifest": str(package.destination / "release-manifest.json"),
                    "recovery_checksums": str(package.destination / "SHA256SUMS.txt"),
                },
            }
            (staging / "checkpoint-manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            staging.rename(checkpoint_directory)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        pointer = {
            "schema_version": "1.0",
            "status": "PASS",
            "checkpoint_id": checkpoint_id,
            "checkpoint_directory": str(checkpoint_directory),
            "recovery_directory": str(package.destination),
            "source_revision": source_revision,
            "runtime_revision": runtime_revision,
            "restore_verified": True,
            "promoted_at": now.isoformat(),
        }
        pointer_path = self.checkpoint_root / "last-known-compliant.json"
        temporary_pointer = self.checkpoint_root / f".last-known-compliant-{os.getpid()}.tmp"
        temporary_pointer.write_text(
            json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_pointer.replace(pointer_path)

        return CCCCheckpointResult(
            checkpoint_id=checkpoint_id,
            checkpoint_directory=checkpoint_directory,
            recovery_directory=package.destination,
            source_revision=source_revision,
            runtime_revision=runtime_revision,
            pointer_path=pointer_path,
        )

    def _git_output(self, *args: str) -> str:
        import subprocess

        completed = subprocess.run(
            ("git", *args),
            cwd=self.repository_root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode != 0:
            raise CCCCheckpointError(
                f"Git command failed: git {' '.join(args)}\n{completed.stdout or ''}"
            )
        return (completed.stdout or "").strip()
