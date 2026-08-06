from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "stateful_recovery_readiness.py"
SPEC = importlib.util.spec_from_file_location("stateful_recovery_readiness", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


REQUIRED_ROWS = {
    "Component": "OpenBao pilot",
    "Initialization status": "Initialized",
    "Seal or recovery method": "Manual Shamir unseal",
    "Share count": "5",
    "Recovery threshold": "3",
    "Custody assignments": "Five approved custodians",
    "Protected custody reference": "AOT secure custody register CR-001",
    "Bootstrap credential disposition": "Initial root token revoked",
    "Operational owner": "AOT Infrastructure Owner",
    "Escalation contact": "AOT Security Escalation",
    "Last successful recovery test": "2026-08-06",
    "Recovery evidence reference": "evidence/recovery-test-20260806.json",
}


def write_record(path: Path, overrides: dict[str, tuple[str, str]] | None = None) -> None:
    overrides = overrides or {}
    lines = ["| Field | Value | Status |", "|---|---|---|"]
    for field, value in REQUIRED_ROWS.items():
        row_value, status = overrides.get(field, (value, "Verified"))
        lines.append(f"| {field} | {row_value} | {status} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_verified_recovery_record_is_ready(tmp_path: Path) -> None:
    record = tmp_path / "recovery.md"
    write_record(record)
    result = MODULE.evaluate_recovery_record(record)
    assert result.ready is True
    assert result.blocking_fields == ()


def test_unverified_custody_denies_readiness(tmp_path: Path) -> None:
    record = tmp_path / "recovery.md"
    write_record(record, {"Custody assignments": ("UNVERIFIED", "Blocking")})
    result = MODULE.evaluate_recovery_record(record)
    assert result.ready is False
    assert "Custody assignments" in result.blocking_fields


def test_missing_required_field_denies_readiness(tmp_path: Path) -> None:
    record = tmp_path / "recovery.md"
    write_record(record)
    text = record.read_text(encoding="utf-8")
    record.write_text(
        "\n".join(
            line for line in text.splitlines() if "Recovery evidence reference" not in line
        )
        + "\n",
        encoding="utf-8",
    )
    result = MODULE.evaluate_recovery_record(record)
    assert result.ready is False
    assert "Recovery evidence reference" in result.blocking_fields


def test_require_recovery_ready_reports_all_blockers(tmp_path: Path) -> None:
    record = tmp_path / "recovery.md"
    write_record(
        record,
        {
            "Last successful recovery test": ("NOT TESTED", "Blocking"),
            "Recovery evidence reference": ("MISSING", "Blocking"),
        },
    )
    with pytest.raises(MODULE.RecoveryReadinessError, match="recovery is not ready"):
        MODULE.require_recovery_ready(record)
