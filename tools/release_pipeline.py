from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools.documentation_readiness import (
    DocumentationReadinessError,
    DocumentationReadinessGate,
    DocumentationReadinessResult,
)
from tools.recovery_package import (
    RecoveryPackageBuilder,
    RecoveryPackageError,
    RecoveryPackageResult,
)
from tools.release_validation import (
    ReleaseValidationError,
    ReleaseValidator,
    ValidationStepResult,
)
from tools.restore_verification import (
    RecoveryRestoreVerifier,
    RestoreVerificationError,
    RestoreVerificationResult,
)


class ReleasePipelineError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"Release pipeline failed at {stage}: {message}")
        self.stage = stage


@dataclass(frozen=True, slots=True)
class ReleasePipelineResult:
    version: str
    release_name: str
    commit: str
    package_directory: Path
    documentation_result: DocumentationReadinessResult
    validation_results: tuple[ValidationStepResult, ...]
    package_result: RecoveryPackageResult
    restore_result: RestoreVerificationResult


class ReleasePipeline:
    """Coordinate documentation, validation, recovery, and restore verification."""

    def __init__(
        self,
        repository_root: Path,
        destination_root: Path,
        *,
        documentation_gate_factory: Callable[
            [Path], DocumentationReadinessGate
        ] = DocumentationReadinessGate,
        validator_factory: Callable[[Path], ReleaseValidator] = ReleaseValidator,
        package_builder_factory: Callable[
            [Path, Path], RecoveryPackageBuilder
        ] = RecoveryPackageBuilder,
        restore_verifier_factory: Callable[
            [Path], RecoveryRestoreVerifier
        ] = RecoveryRestoreVerifier,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._destination_root = destination_root.expanduser().resolve()
        self._documentation_gate_factory = documentation_gate_factory
        self._validator_factory = validator_factory
        self._package_builder_factory = package_builder_factory
        self._restore_verifier_factory = restore_verifier_factory

    def run(
        self,
        version: str,
        *,
        release_name: str,
        ref: str = "HEAD",
    ) -> ReleasePipelineResult:
        try:
            documentation_result = self._documentation_gate_factory(
                self._repository_root
            ).verify(
                version,
                release_name=release_name,
            )
        except DocumentationReadinessError as error:
            raise ReleasePipelineError(
                "documentation-readiness",
                str(error),
            ) from error

        try:
            validation_results = self._validator_factory(
                self._repository_root
            ).validate()
        except ReleaseValidationError as error:
            raise ReleasePipelineError(
                "validation",
                str(error),
            ) from error

        try:
            package_result = self._package_builder_factory(
                self._repository_root,
                self._destination_root,
            ).build(
                version,
                release_name=release_name,
                ref=ref,
            )
        except (RecoveryPackageError, ValueError) as error:
            raise ReleasePipelineError(
                "recovery-package",
                str(error),
            ) from error

        try:
            restore_result = self._restore_verifier_factory(
                self._repository_root
            ).verify(package_result.destination)
        except RestoreVerificationError as error:
            raise ReleasePipelineError(
                "restore-verification",
                str(error),
            ) from error

        if restore_result.commit != package_result.commit:
            raise ReleasePipelineError(
                "restore-verification",
                "Restored commit does not match the recovery package commit.",
            )

        return ReleasePipelineResult(
            version=package_result.version,
            release_name=release_name.strip(),
            commit=package_result.commit,
            package_directory=package_result.destination,
            documentation_result=documentation_result,
            validation_results=validation_results,
            package_result=package_result,
            restore_result=restore_result,
        )
