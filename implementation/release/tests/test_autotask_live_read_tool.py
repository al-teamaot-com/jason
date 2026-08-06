from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "autotask_live_read.py"
REPOSITORY_ROOT = MODULE_PATH.parents[1]
SPEC = importlib.util.spec_from_file_location("autotask_live_read_tool", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_args(tmp_path: Path, *mode: str):
    record = tmp_path / "deployment.md"
    record.write_text("# deployment\n", encoding="utf-8")
    return MODULE.build_parser().parse_args(
        [
            "--ticket-number",
            "T20260805.0001",
            "--scope",
            "pilot",
            "--allowed-scope",
            "pilot",
            "--principal-id",
            "operator-al",
            "--organization-id",
            "team-aot",
            "--correlation-id",
            "cap001-live-1",
            "--evidence-output",
            str(tmp_path / "evidence.json"),
            "--deployment-record",
            str(record),
            *mode,
        ]
    )


def test_direct_command_loads_without_pythonpath() -> None:
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "autotask.readonly" in result.stdout
    assert "--company-id" not in result.stdout
    assert "--username-reference" not in result.stdout
    assert "--secret-command" not in result.stdout


def test_check_only_does_not_build_connector_or_contact_provider(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        MODULE,
        "build_autotask_connector",
        lambda: pytest.fail("connector must not be built"),
    )
    monkeypatch.setattr(
        MODULE,
        "require_deployment_ready",
        lambda path: pytest.fail("deployment gate must not run"),
    )

    assert MODULE.run(make_args(tmp_path, "--check-only")) is None
    assert not (tmp_path / "evidence.json").exists()


def test_scope_mismatch_fails_before_connector_binding(tmp_path: Path) -> None:
    args = make_args(tmp_path, "--check-only")
    args.allowed_scope = "different"
    with pytest.raises(PermissionError, match="authorized scope"):
        MODULE.run(args)


def test_live_read_requires_explicit_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="--live-read"):
        MODULE.run(make_args(tmp_path))


def test_check_only_and_live_read_cannot_be_combined(tmp_path: Path) -> None:
    with pytest.raises(PermissionError, match="cannot be requested together"):
        MODULE.run(make_args(tmp_path, "--check-only", "--live-read"))


def test_live_read_uses_canonical_service_and_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured = {}

    class FakeService:
        def __init__(self, connector) -> None:
            captured["connector"] = connector

        def validate(self, request, *, output_path, repository_root):
            captured["request"] = request
            captured["output_path"] = output_path
            captured["repository_root"] = repository_root
            output_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(MODULE, "require_deployment_ready", lambda path: None)
    monkeypatch.setattr(MODULE, "build_autotask_connector", lambda: "canonical")
    monkeypatch.setattr(MODULE, "GovernedAutotaskLiveRead", FakeService)

    args = make_args(tmp_path, "--live-read")
    output = MODULE.run(args)

    assert captured["connector"] == "canonical"
    assert captured["request"].ticket_number == "T20260805.0001"
    assert not hasattr(captured["request"], "company_id")
    assert captured["request"].principal_id == "operator-al"
    assert captured["request"].organization_id == "team-aot"
    assert captured["request"].correlation_id == "cap001-live-1"
    assert captured["request"].live_read_acknowledged is True
    assert captured["repository_root"] == REPOSITORY_ROOT
    assert output == (tmp_path / "evidence.json").resolve()


def test_existing_evidence_is_denied(tmp_path: Path) -> None:
    args = make_args(tmp_path, "--check-only")
    args.evidence_output.write_text("existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="overwrite is denied"):
        MODULE.run(args)
