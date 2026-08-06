from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "production_readiness_closeout.py"
REPOSITORY_ROOT = MODULE_PATH.parents[1]
SPEC = importlib.util.spec_from_file_location("production_readiness_closeout", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_ready_recovery_record(path: Path) -> None:
    path.write_text(
        """| Field | Value | Status |
|---|---|---|
| Component | OpenBao pilot | Verified |
| Initialization status | Initialized | Verified |
| Seal or recovery method | Manual Shamir unseal | Verified |
| Share count | 5 | Verified |
| Recovery threshold | 3 | Verified |
| Custody assignments | Five approved custodians | Verified |
| Protected custody reference | Secure custody register | Verified |
| Bootstrap credential disposition | Initial root token revoked | Verified |
| Operational owner | AOT Infrastructure Owner | Verified |
| Escalation contact | AOT Security Escalation | Verified |
| Last successful recovery test | 2026-08-06 | Verified |
| Recovery evidence reference | evidence/recovery.json | Verified |
""",
        encoding="utf-8",
    )


def make_args(tmp_path: Path):
    secret_command = tmp_path / "jason-secret"
    secret_command.write_text("#!/bin/sh\n", encoding="utf-8")
    record = tmp_path / "deployment.md"
    record.write_text("# deployment\n", encoding="utf-8")
    recovery_record = tmp_path / "recovery.md"
    write_ready_recovery_record(recovery_record)
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
            "--recovery-record",
            str(recovery_record),
            "--bootstrap-token-file",
            str(tmp_path / "openbao-bootstrap.token"),
            "--contract-evidence",
            str(tmp_path / "contract.json"),
            "--autotask-evidence",
            str(tmp_path / "autotask.json"),
            "--check-only",
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
    assert "--bootstrap-token-file" in result.stdout


def test_check_only_is_no_network_and_no_secret_resolution(tmp_path: Path) -> None:
    result = MODULE.execute(make_args(tmp_path))
    assert result == {
        "status": "approved",
        "mode": "check-only",
        "secret_resolved": False,
        "openbao_contacted": False,
        "autotask_contacted": False,
        "recovery_gate_bypassed": False,
        "bootstrap_gate_bypassed": False,
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


def test_live_execution_is_denied_when_recovery_is_unverified(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.check_only = False
    args.recovery_record.write_text(
        "| Field | Value | Status |\n"
        "|---|---|---|\n"
        "| Component | OpenBao pilot | Verified |\n"
        "| Custody assignments | UNVERIFIED | Blocking |\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="recovery is not ready"):
        MODULE.validate(args)


def test_bootstrap_credential_blocks_readiness(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.bootstrap_token_file.write_text("protected\n", encoding="utf-8")
    with pytest.raises(PermissionError, match="bootstrap credential exists"):
        MODULE.validate(args)


def test_commissioning_override_is_check_only_and_reported(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.bootstrap_token_file.write_text("protected\n", encoding="utf-8")
    args.commissioning = True
    result = MODULE.execute(args)
    assert result["bootstrap_gate_bypassed"] is True
    assert result["openbao_contacted"] is False
    assert result["autotask_contacted"] is False


def test_commissioning_override_cannot_run_live(tmp_path: Path) -> None:
    args = make_args(tmp_path)
    args.bootstrap_token_file.write_text("protected\n", encoding="utf-8")
    args.commissioning = True
    args.check_only = False
    with pytest.raises(PermissionError, match="only with check-only"):
        MODULE.validate(args)
