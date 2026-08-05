from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

import pytest

from jason_cap_001.autotask_live_read_command import (
    CommandSecretBroker,
    CommandSecretBrokerError,
    build_parser,
    run,
)


def parse(tmp_path: Path, *extra: str) -> argparse.Namespace:
    command = tmp_path / "secret-command"
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    output = tmp_path / "evidence.json"
    argv = [
        "--ticket-number",
        "T20260805.0001",
        "--company-id",
        "1001",
        "--scope",
        "aot-validation",
        "--allowed-scope",
        "aot-validation",
        "--evidence-output",
        str(output),
        "--username-reference",
        "secret/autotask/username",
        "--secret-reference",
        "secret/autotask/secret",
        "--integration-code-reference",
        "secret/autotask/integration-code",
        "--secret-command",
        str(command),
        *extra,
    ]
    return build_parser().parse_args(argv)


def test_check_only_performs_no_secret_or_network_work(tmp_path: Path) -> None:
    args = parse(tmp_path, "--check-only")

    assert run(args) is None
    assert not args.evidence_output.exists()


def test_live_read_requires_explicit_acknowledgement(tmp_path: Path) -> None:
    args = parse(tmp_path)

    with pytest.raises(PermissionError, match="--live-read"):
        run(args)


def test_rejects_scope_mismatch_before_live_binding(tmp_path: Path) -> None:
    args = parse(tmp_path, "--check-only")
    args.scope = "client-production"

    with pytest.raises(PermissionError, match="authorized scope"):
        run(args)


def test_refuses_existing_evidence_output(tmp_path: Path) -> None:
    args = parse(tmp_path, "--check-only")
    args.evidence_output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="overwrite"):
        run(args)


def test_command_secret_broker_passes_reference_without_shell(tmp_path: Path) -> None:
    executable = tmp_path / "broker"
    executable.write_text("placeholder", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="resolved-value\n", stderr="")

    broker = CommandSecretBroker(executable=executable, runner=runner)

    assert broker.get_secret("secret/autotask/username") == "resolved-value"
    assert calls[0][0] == [str(executable.resolve()), "secret/autotask/username"]
    assert calls[0][1]["capture_output"] is True
    assert "shell" not in calls[0][1]


def test_command_secret_broker_redacts_failure_output(tmp_path: Path) -> None:
    executable = tmp_path / "broker"
    executable.write_text("placeholder", encoding="utf-8")

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="super-secret-value",
            stderr="provider details",
        )

    broker = CommandSecretBroker(executable=executable, runner=runner)

    with pytest.raises(CommandSecretBrokerError) as captured:
        broker.get_secret("secret/autotask/secret")

    message = str(captured.value)
    assert "super-secret-value" not in message
    assert "provider details" not in message
