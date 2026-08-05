from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.documentation_readiness import DocumentationReadinessError
from tools.release_evidence import ReleaseEvidenceError
from tools.release_pipeline import ReleasePipeline, ReleasePipelineError
from tools.release_validation import ReleaseValidationError, ValidationStepResult
from tools.recovery_package import RecoveryPackageError
from tools.restore_verification import RestoreVerificationError


COMMIT = "a" * 40


class DocumentationGate:
    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.fail = fail

    def verify(self, version: str, *, release_name: str):
        if self.fail:
            raise DocumentationReadinessError("documentation missing")
        normalized = version if version.startswith("v") else f"v{version}"
        return SimpleNamespace(
            version=normalized,
            release_name=release_name,
            status="Complete",
            record_path=Path("10-Milestones/M-TEST.md"),
        )


class Validator:
    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.fail = fail

    def validate(self):
        result = ValidationStepResult(
            step_id="test",
            description="Test validation",
            command=("true",),
            return_code=1 if self.fail else 0,
            output="failed" if self.fail else "",
        )
        if self.fail:
            raise ReleaseValidationError(result)
        return (result,)


class Builder:
    def __init__(self, root: Path, destination: Path, *, fail: bool = False) -> None:
        self.destination = destination
        self.fail = fail

    def build(self, version: str, *, release_name: str, ref: str):
        if self.fail:
            raise RecoveryPackageError("package failed")
        normalized = version if version.startswith("v") else f"v{version}"
        return SimpleNamespace(
            version=normalized,
            commit=COMMIT,
            destination=self.destination / normalized,
        )


class Verifier:
    def __init__(
        self,
        root: Path,
        *,
        fail: bool = False,
        commit: str = COMMIT,
    ) -> None:
        self.fail = fail
        self.commit = commit

    def verify(self, package_directory: Path):
        if self.fail:
            raise RestoreVerificationError("restore failed")
        return SimpleNamespace(
            version=package_directory.name,
            commit=self.commit,
            bundle=package_directory / "bundle",
            restored_repository=package_directory / "restored",
            validation_output="approved",
        )


class EvidenceWriter:
    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.fail = fail

    def write(self, **values):
        if self.fail:
            raise ReleaseEvidenceError("evidence failed")
        package_directory = values["package_directory"]
        return SimpleNamespace(
            report_path=package_directory / "release-report.json",
            summary_path=package_directory / "release-summary.md",
            checksums_path=package_directory / "SHA256SUMS.txt",
        )


def pipeline(
    tmp_path: Path,
    *,
    documentation_fail: bool = False,
    validation_fail: bool = False,
    package_fail: bool = False,
    restore_fail: bool = False,
    evidence_fail: bool = False,
    restored_commit: str = COMMIT,
) -> ReleasePipeline:
    return ReleasePipeline(
        tmp_path,
        tmp_path / "recovery",
        documentation_gate_factory=lambda root: DocumentationGate(
            root, fail=documentation_fail
        ),
        validator_factory=lambda root: Validator(root, fail=validation_fail),
        package_builder_factory=lambda root, destination: Builder(
            root, destination, fail=package_fail
        ),
        restore_verifier_factory=lambda root: Verifier(
            root, fail=restore_fail, commit=restored_commit
        ),
        evidence_writer_factory=lambda root: EvidenceWriter(
            root, fail=evidence_fail
        ),
    )


def test_release_pipeline_approves_complete_release(tmp_path: Path) -> None:
    result = pipeline(tmp_path).run(
        "0.1.2", release_name="Release Orchestrator"
    )

    assert result.version == "v0.1.2"
    assert result.commit == COMMIT
    assert result.release_name == "Release Orchestrator"
    assert result.documentation_result.status == "Complete"
    assert result.evidence_result.report_path.name == "release-report.json"


def test_documentation_failure_stops_pipeline(tmp_path: Path) -> None:
    with pytest.raises(ReleasePipelineError, match="documentation-readiness"):
        pipeline(tmp_path, documentation_fail=True).run(
            "v0.1.2", release_name="Release Orchestrator"
        )


def test_validation_failure_stops_pipeline(tmp_path: Path) -> None:
    with pytest.raises(ReleasePipelineError, match="validation"):
        pipeline(tmp_path, validation_fail=True).run(
            "v0.1.2", release_name="Release Orchestrator"
        )


def test_package_failure_stops_pipeline(tmp_path: Path) -> None:
    with pytest.raises(ReleasePipelineError, match="recovery-package"):
        pipeline(tmp_path, package_fail=True).run(
            "v0.1.2", release_name="Release Orchestrator"
        )


def test_restore_failure_stops_pipeline(tmp_path: Path) -> None:
    with pytest.raises(ReleasePipelineError, match="restore-verification"):
        pipeline(tmp_path, restore_fail=True).run(
            "v0.1.2", release_name="Release Orchestrator"
        )


def test_restored_commit_must_match_package_commit(tmp_path: Path) -> None:
    with pytest.raises(ReleasePipelineError, match="does not match"):
        pipeline(tmp_path, restored_commit="b" * 40).run(
            "v0.1.2", release_name="Release Orchestrator"
        )


def test_evidence_failure_denies_release(tmp_path: Path) -> None:
    with pytest.raises(ReleasePipelineError, match="release-evidence"):
        pipeline(tmp_path, evidence_fail=True).run(
            "v0.1.2", release_name="Release Orchestrator"
        )
