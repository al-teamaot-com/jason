from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "production_readiness_closeout.py"
SPEC = importlib.util.spec_from_file_location("production_readiness_closeout", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_args(tmp_path: Path):
    secret_command = tmp_path / "jason-secret"
    secret_command.write_text("#!/bin/sh\n", encoding="utf-8")
    record = tmp_path / "deployment.md"
    record.write_text("# deployment\n", encoding="utf-8")
    return MODULE.build_parser().parse_args(
        [
            "--ticket-number",
            "T20260805.0001",
            "--company-id",
            "123",
            "--scope",
            "pilot",
            "--allowed-scope",
            "pilot",
            "--secret-command",
            str(secret_command),
            "--deployment-record",
            str(record),
            "--contract-evidence",
            str(tmp_path / "contract.json"),
            "--autotask-evidence",
            str(tmp_path / "autotask.json"),
            "--check-only",
        ]
    )


def test_check_only_is_no_network_and_no_secret_resolution(tmp_path: Path) -> None:
    result = MODULE.execute(make_args(tmp_path))
    assert result == {
        "status": "approved",
        "mode": "check-only",
        "secret_resolved": False,
        "openbao_contacted": False,
        "autotask_contacted": False,
    }


def test_scope_mismatch_is_denied(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.allowed_scope = "different"
    with pytest.raises(PermissionError, match="authorized scope"):
        MODULE.validate(args)


def test_existing_evidence_is_denied(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.contract_evidence.write_text("existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        MODULE.validate(args)


def test_missing_secret_command_is_denied(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.secret_command.unlink()
    with pytest.raises(FileNotFoundError, match="secret command"):
        MODULE.validate(args)
