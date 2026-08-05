from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Callable, Sequence


CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class ValidationStep:
    step_id: str
    description: str
    command: tuple[str, ...]
    working_directory: Path


@dataclass(frozen=True, slots=True)
class ValidationStepResult:
    step_id: str
    description: str
    command: tuple[str, ...]
    return_code: int
    output: str

    @property
    def passed(self) -> bool:
        return self.return_code == 0


class ReleaseValidationError(RuntimeError):
    def __init__(self, result: ValidationStepResult) -> None:
        super().__init__(
            f"Release validation failed at {result.step_id}: "
            f"{result.description}"
        )
        self.result = result


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


def discover_python(repository_root: Path, environment: str) -> str:
    candidate = repository_root / environment / "bin" / "python"
    if candidate.is_file():
        return str(candidate)
    return "python3"


def build_validation_steps(repository_root: Path) -> tuple[ValidationStep, ...]:
    test_python = discover_python(repository_root, ".venv-test")
    docs_python = discover_python(repository_root, ".venv-docs")

    return (
        ValidationStep(
            step_id="git-worktree",
            description="Confirm repository worktree",
            command=("git", "rev-parse", "--is-inside-work-tree"),
            working_directory=repository_root,
        ),
        ValidationStep(
            step_id="git-clean",
            description="Confirm working tree is clean",
            command=("git", "status", "--porcelain"),
            working_directory=repository_root,
        ),
        ValidationStep(
            step_id="kernel-tests",
            description="Run Kernel tests",
            command=(
                test_python,
                "-m",
                "pytest",
                "kernel/tests",
                "-q",
            ),
            working_directory=repository_root / "implementation",
        ),
        ValidationStep(
            step_id="cap-001-tests",
            description="Run CAP-001 tests",
            command=(
                test_python,
                "-m",
                "pytest",
                "tests",
                "-q",
            ),
            working_directory=repository_root / "implementation" / "cap-001",
        ),
        ValidationStep(
            step_id="assemble-docs",
            description="Assemble documentation workspace",
            command=(
                docs_python,
                str(repository_root / "tools" / "assemble_docs.py"),
            ),
            working_directory=repository_root,
        ),
        ValidationStep(
            step_id="strict-docs",
            description="Build documentation in strict mode",
            command=(docs_python, "-m", "mkdocs", "build", "--strict"),
            working_directory=repository_root,
        ),
        ValidationStep(
            step_id="whitespace",
            description="Check Git whitespace",
            command=("git", "diff", "--check"),
            working_directory=repository_root,
        ),
    )


class ReleaseValidator:
    def __init__(
        self,
        repository_root: Path,
        *,
        runner: CommandRunner = default_runner,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._runner = runner

    def validate(self) -> tuple[ValidationStepResult, ...]:
        results: list[ValidationStepResult] = []

        for step in build_validation_steps(self._repository_root):
            completed = self._runner(step.command, step.working_directory)
            output = completed.stdout or ""

            if step.step_id == "git-clean" and output.strip():
                completed = subprocess.CompletedProcess(
                    args=completed.args,
                    returncode=1,
                    stdout=output,
                )

            result = ValidationStepResult(
                step_id=step.step_id,
                description=step.description,
                command=step.command,
                return_code=completed.returncode,
                output=output,
            )
            results.append(result)

            if not result.passed:
                raise ReleaseValidationError(result)

        return tuple(results)
