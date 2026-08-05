from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from tools.release_validation import (
    ReleaseValidationError,
    ReleaseValidator,
    build_validation_steps,
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


def test_validation_step_order_is_deterministic(tmp_path: Path) -> None:
    step_ids = tuple(
        step.step_id for step in build_validation_steps(tmp_path)
    )

    assert step_ids == (
        "git-worktree",
        "git-clean",
        "kernel-tests",
        "cap-001-tests",
        "assemble-docs",
        "strict-docs",
        "whitespace",
    )


def test_successful_validation_returns_all_results(tmp_path: Path) -> None:
    calls: list[tuple[tuple[str, ...], Path]] = []

    def runner(command, working_directory):
        normalized = tuple(command)
        calls.append((normalized, working_directory))
        return completed(normalized)

    results = ReleaseValidator(tmp_path, runner=runner).validate()

    assert len(results) == 7
    assert all(result.passed for result in results)
    assert [result.step_id for result in results] == [
        "git-worktree",
        "git-clean",
        "kernel-tests",
        "cap-001-tests",
        "assemble-docs",
        "strict-docs",
        "whitespace",
    ]
    assert len(calls) == 7


def test_command_failure_stops_validation(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner(command, working_directory):
        del working_directory
        step_command = tuple(command)
        calls.append(step_command[0])
        if len(calls) == 3:
            return completed(
                step_command,
                return_code=1,
                output="kernel failure",
            )
        return completed(step_command)

    with pytest.raises(ReleaseValidationError) as raised:
        ReleaseValidator(tmp_path, runner=runner).validate()

    assert raised.value.result.step_id == "kernel-tests"
    assert raised.value.result.output == "kernel failure"
    assert len(calls) == 3


def test_dirty_worktree_fails_closed(tmp_path: Path) -> None:
    def runner(command, working_directory):
        del working_directory
        step_command = tuple(command)
        if step_command[:2] == ("git", "status"):
            return completed(step_command, output=" M README.md\n")
        return completed(step_command, output="true\n")

    with pytest.raises(ReleaseValidationError) as raised:
        ReleaseValidator(tmp_path, runner=runner).validate()

    assert raised.value.result.step_id == "git-clean"
    assert "README.md" in raised.value.result.output
